"""视频摄取流水线 — 从视频中提取知识点。

完整流程（5 个步骤）：
    1. 保存上传文件 → 分配唯一 ID
    2. 提取音频轨道 → FFmpeg 转 WAV (16kHz mono)
    3. 捕获关键帧 → 场景检测或均匀采样
    4. 语音转录 → Whisper 模型生成带时间戳的文本片段
    5. AI 摘要 → 每个片段调用 LLM 生成一句话摘要 + 关键词

依赖：
    - FFmpeg（系统级命令行工具，需预先安装）
    - openai-whisper（可选，未安装时使用演示数据）
    - LLM API（通过环境变量 ANTHROPIC_AUTH_TOKEN 配置）
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

from kb_server.config import (
    FFMPEG_CANDIDATES,
    AUDIO_DIR,
    FRAME_DIR,
    VIDEO_DIR,
    KEYFRAME_COUNT,
    SCENE_THRESHOLD,
    API_BASE,
    API_KEY,
    API_MODEL,
)

# 确保存储目录存在
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(FRAME_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)


# ==================================================================
# FFmpeg 工具函数
# ==================================================================


def _find_ffmpeg() -> str:
    """在系统中定位 FFmpeg 可执行文件。

    按 FFMPEG_CANDIDATES 列表依次尝试，
    返回第一个能成功运行 `ffmpeg -version` 的路径。
    找不到时返回 "ffmpeg"（依赖系统 PATH）。
    """
    for path in FFMPEG_CANDIDATES:
        try:
            subprocess.run(
                [path, "-version"], capture_output=True, timeout=5
            )
            return path
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            continue
    return "ffmpeg"


FFMPEG = _find_ffmpeg()


# ==================================================================
# 视频处理核心函数
# ==================================================================


def extract_audio(video_path: str, output_path: str) -> str:
    """从视频文件中提取音频轨道并保存为 WAV 格式。

    参数：
        video_path: 输入视频文件的绝对路径
        output_path: 输出 WAV 文件的绝对路径

    返回：
        输出文件路径

    音频参数：
        PCM 16-bit signed integer
        采样率 16000 Hz（Whisper 推荐）
        单声道
    """
    cmd = [
        FFMPEG, "-y",
        "-i", video_path,
        "-vn",                       # 丢弃视频流
        "-acodec", "pcm_s16le",      # PCM 16-bit
        "-ar", "16000",              # 16kHz 采样率
        "-ac", "1",                  # 单声道
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def extract_keyframes(
    video_path: str, output_dir: str, count: int = KEYFRAME_COUNT
) -> list[str]:
    """从视频中提取代表性关键帧图片。

    优先使用场景检测算法，失败时退化为均匀时间间隔采样。

    参数：
        video_path: 输入视频文件路径
        output_dir: 关键帧输出目录
        count: 最大提取帧数

    返回：
        生成的关键帧文件路径列表
    """
    paths: list[str] = []

    try:
        # 方案 A：场景检测 — 选取画面变化剧烈的时刻
        cmd = [
            FFMPEG, "-y",
            "-i", video_path,
            "-vf", f"select='gt(scene,{SCENE_THRESHOLD})',scale=640:-1",
            "-vsync", "vfr",
            "-frames:v", str(count),
            os.path.join(output_dir, "frame_%03d.jpg"),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
    except subprocess.CalledProcessError:
        # 方案 B：均匀时间间隔采样
        duration = get_duration(video_path)
        interval = max(1, duration / (count + 1))
        for i in range(count):
            t = interval * (i + 1)
            out = os.path.join(output_dir, f"frame_{i:03d}.jpg")
            cmd = [
                FFMPEG, "-y",
                "-ss", str(t),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                out,
            ]
            subprocess.run(cmd, capture_output=True)
            if os.path.exists(out):
                paths.append(out)

    # 收集生成的文件
    if not paths:
        for f in sorted(os.listdir(output_dir)):
            if f.startswith("frame_") and f.endswith(".jpg"):
                paths.append(os.path.join(output_dir, f))

    return paths


def get_duration(video_path: str) -> float:
    """获取视频时长（秒）。

    通过解析 FFmpeg stderr 输出中的 "Duration: HH:MM:SS.ms" 字段实现。
    解析失败时返回 60 秒作为默认值。
    """
    try:
        cmd = [FFMPEG, "-i", video_path, "-f", "null", "-"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        m = re.search(
            r"Duration: (\d+):(\d+):(\d+)\.(\d+)", result.stderr
        )
        if m:
            h, mi, s, ms = (
                int(m.group(1)),
                int(m.group(2)),
                int(m.group(3)),
                int(m.group(4)),
            )
            return h * 3600 + mi * 60 + s + ms / 100
    except Exception:
        pass
    return 60.0


# ==================================================================
# 语音转录
# ==================================================================


def transcribe_audio(audio_path: str) -> list[dict]:
    """使用 Whisper 模型将音频转录为带时间戳的文本片段。

    参数：
        audio_path: WAV 音频文件路径

    返回：
        片段列表，每项为 {"start": 开始秒, "end": 结束秒, "text": 文本}

    依赖：
        openai-whisper（pip install openai-whisper）
        未安装时返回演示数据
    """
    try:
        import whisper

        model = whisper.load_model("base")
        result = model.transcribe(
            audio_path, language="zh", verbose=False
        )
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            })
        return segments
    except ImportError:
        # Whisper 未安装 → 返回演示片段
        return [
            {
                "start": 0,
                "end": 30,
                "text": "[Whisper 未安装，这是演示片段] "
                        "请在终端运行: pip install openai-whisper",
            },
        ]


# ==================================================================
# AI 摘要
# ==================================================================


def _generate_summary(text: str) -> str:
    """为视频片段生成一句话摘要。

    优先使用 LLM API，失败时退化为首句 + 尾句拼接。

    参数：
        text: 片段转录文本

    返回：
        摘要字符串
    """
    if not text or len(text) < 10:
        return ""

    try:
        return _llm_summary(text)
    except Exception:
        # LLM 不可用 → 基于标点符号的简单摘要
        sentences = re.split(r"[。！？!?]", text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        if len(sentences) <= 2:
            return text[:200]
        return sentences[0] + "。" + (
            sentences[-1] if len(sentences[-1]) > 10 else ""
        )


def _llm_summary(text: str) -> str:
    """调用 LLM API 生成结构化摘要。

    需要环境变量 ANTHROPIC_AUTH_TOKEN 已设置。
    返回格式：{摘要}|{kw1,kw2,kw3}

    参数：
        text: 要摘要的文本（最多取前 1000 字符）

    返回：
        LLM 生成的摘要字符串
    """
    import urllib.request

    if not API_KEY:
        raise RuntimeError("未配置 ANTHROPIC_AUTH_TOKEN 环境变量")

    body = json.dumps({
        "model": API_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是视频分析师。用一句话总结以下视频片段的核心观点"
                    "（不超过50字），然后提取3个关键词。"
                    "输出格式：{summary}|{kw1,kw2,kw3}"
                ),
            },
            {"role": "user", "content": text[:1000]},
        ],
        "max_tokens": 200,
    }).encode()

    url = f"{API_BASE}/messages"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    return data["content"][0]["text"].strip()


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取高频关键词（基于 Bigram 频率）。

    参数：
        text: 输入文本

    返回：
        出现频率最高的 5 个字符 bigram 列表
    """
    if not text:
        return []

    seen: dict[str, int] = {}
    for i in range(len(text) - 1):
        bg = text[i] + text[i + 1]
        if bg.strip() and len(bg.strip()) == 2:
            seen[bg] = seen.get(bg, 0) + 1

    top = sorted(seen.items(), key=lambda x: x[1], reverse=True)[:5]
    return [t[0] for t in top]


# ==================================================================
# 流水线编排
# ==================================================================


def process_video(filepath: str, video_id: str) -> dict:
    """执行完整的视频摄取流水线。

    流程：
        1. 提取音频轨道（FFmpeg）
        2. 捕获关键帧图片（FFmpeg 场景检测）
        3. 语音 → 文本转录（Whisper）
        4. 每个片段生成 AI 摘要 + 关键词

    参数：
        filepath: 已上传视频文件的绝对路径
        video_id: 唯一视频标识符（8 位 UUID）

    返回：
        处理结果字典：
        {
            "video_id": str,
            "duration": float,
            "segments": [{"start", "end", "text", "summary", "keywords"}],
            "keyframes_count": int,
            "processing_time": float,
        }
    """
    start_time = time.time()

    # 检测 FFmpeg 是否可用
    ffmpeg_ok = FFMPEG != "ffmpeg" or _find_ffmpeg() != "ffmpeg"

    # Step 1: 提取音频
    audio_path = os.path.join(AUDIO_DIR, f"{video_id}.wav")
    if ffmpeg_ok:
        try:
            extract_audio(filepath, audio_path)
        except Exception:
            ffmpeg_ok = False

    # Step 2: 提取关键帧
    frame_dir = os.path.join(FRAME_DIR, video_id)
    os.makedirs(frame_dir, exist_ok=True)
    keyframes: list[str] = []
    if ffmpeg_ok:
        try:
            keyframes = extract_keyframes(filepath, frame_dir)
        except Exception:
            pass

    # Step 3: 语音转录
    segments: list[dict] = []
    if ffmpeg_ok and os.path.exists(audio_path):
        segments = transcribe_audio(audio_path)

    # Step 4: AI 摘要和关键词提取
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
