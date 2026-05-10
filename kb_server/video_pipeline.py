"""
Video ingestion pipeline — FFmpeg audio extraction, keyframe capture, Whisper transcription.
Supports: Step 2-4 of the knowledge base video processing spec.
"""

import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kb", "uploads")
VIDEO_DIR = os.path.join(UPLOAD_DIR, "videos")
FRAME_DIR = os.path.join(UPLOAD_DIR, "frames")
AUDIO_DIR = os.path.join(UPLOAD_DIR, "audio")

os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(FRAME_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)


def _find_ffmpeg() -> str:
    """Locate ffmpeg binary."""
    for path in [
        "ffmpeg", "ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe"),
        os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe"),
        "C:/ffmpeg/bin/ffmpeg.exe",
    ]:
        try:
            subprocess.run([path, "-version"], capture_output=True, timeout=5)
            return path
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return "ffmpeg"


FFMPEG = _find_ffmpeg()


def extract_audio(video_path: str, output_path: str) -> str:
    """Extract audio track from video using FFmpeg. Returns output path."""
    cmd = [
        FFMPEG, "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def extract_keyframes(video_path: str, output_dir: str, count: int = 5) -> list[str]:
    """Extract representative keyframes using scene detection."""
    paths = []
    try:
        # Try scene detection first
        cmd = [
            FFMPEG, "-y", "-i", video_path,
            "-vf", f"select='gt(scene,0.3)',scale=640:-1",
            "-vsync", "vfr", "-frames:v", str(count),
            os.path.join(output_dir, "frame_%03d.jpg")
        ]
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        # Fallback: evenly spaced frames
        duration = get_duration(video_path)
        interval = max(1, duration / (count + 1))
        for i in range(count):
            t = interval * (i + 1)
            out = os.path.join(output_dir, f"frame_{i:03d}.jpg")
            cmd = [
                FFMPEG, "-y", "-ss", str(t), "-i", video_path,
                "-vframes", "1", "-q:v", "2", out
            ]
            subprocess.run(cmd, capture_output=True)
            if os.path.exists(out):
                paths.append(out)

    # Collect generated frames
    if not paths:
        for f in sorted(os.listdir(output_dir)):
            if f.startswith("frame_") and f.endswith(".jpg"):
                paths.append(os.path.join(output_dir, f))
    return paths


def get_duration(video_path: str) -> float:
    """Get video duration in seconds."""
    try:
        cmd = [
            FFMPEG, "-i", video_path,
            "-f", "null", "-"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        stderr = result.stderr
        m = re.search(r"Duration: (\d+):(\d+):(\d+)\.(\d+)", stderr)
        if m:
            h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return h * 3600 + mi * 60 + s + ms / 100
    except Exception:
        pass
    return 60.0  # default


def transcribe_audio(audio_path: str) -> list[dict]:
    """Transcribe audio using Whisper. Returns segments with timestamps."""
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, language="zh", verbose=False)
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            })
        return segments
    except ImportError:
        # Fallback: return mock segments for demo
        return [
            {"start": 0, "end": 30, "text": "[Whisper 未安装，这是演示片段] 请在终端运行: pip install openai-whisper"},
        ]


def process_video(filepath: str, video_id: str) -> dict:
    """Full video processing pipeline. Returns structured result."""
    start_time = time.time()

    # Step 1: Extract audio
    audio_path = os.path.join(AUDIO_DIR, f"{video_id}.wav")
    ffmpeg_ok = FFMPEG != "ffmpeg" or _find_ffmpeg() != "ffmpeg"

    if ffmpeg_ok:
        try:
            extract_audio(filepath, audio_path)
        except Exception:
            ffmpeg_ok = False

    # Step 2: Extract keyframes
    frame_dir = os.path.join(FRAME_DIR, video_id)
    os.makedirs(frame_dir, exist_ok=True)
    keyframes = []
    if ffmpeg_ok:
        try:
            keyframes = extract_keyframes(filepath, frame_dir)
        except Exception:
            pass

    # Step 3: Transcribe
    segments = []
    if ffmpeg_ok and os.path.exists(audio_path):
        segments = transcribe_audio(audio_path)

    # Step 4: Generate AI summaries for each segment
    for seg in segments:
        seg["summary"] = _generate_summary(seg.get("text", ""))
        seg["keywords"] = _extract_keywords(seg.get("text", ""))

    elapsed = time.time() - start_time

    return {
        "video_id": video_id,
        "duration": get_duration(filepath) if ffmpeg_ok else 0,
        "segments": segments,
        "keyframes_count": len(keyframes),
        "processing_time": round(elapsed, 1),
    }


def _generate_summary(text: str) -> str:
    """Generate a concise summary for a video segment using LLM if available."""
    if not text or len(text) < 10:
        return ""
    try:
        return _llm_summary(text)
    except Exception:
        sentences = re.split(r'[。！？!?]', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        if len(sentences) <= 2:
            return text[:200]
        return sentences[0] + "。" + (sentences[-1] if len(sentences[-1]) > 10 else "")


def _llm_summary(text: str) -> str:
    """Call DeepSeek API for structured summary."""
    import urllib.request
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    api_base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    if not api_key:
        raise RuntimeError("No API key")

    body = json.dumps({
        "model": os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]"),
        "messages": [
            {"role": "system", "content": "你是视频分析师。用一句话总结以下视频片段的核心观点（不超过50字），然后提取3个关键词。输出格式：{summary}|{kw1,kw2,kw3}"},
            {"role": "user", "content": text[:1000]},
        ],
        "max_tokens": 200,
    }).encode()

    url = f"{api_base}/messages"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def _extract_keywords(text: str) -> list[str]:
    """Extract key terms from text."""
    if not text:
        return []
    # Chinese character bigrams for rapid keyword extraction
    seen = {}
    for i in range(len(text) - 1):
        bg = text[i] + text[i + 1]
        if bg.strip() and len(bg.strip()) == 2:
            seen[bg] = seen.get(bg, 0) + 1
    top = sorted(seen.items(), key=lambda x: x[1], reverse=True)[:5]
    return [t[0] for t in top]
