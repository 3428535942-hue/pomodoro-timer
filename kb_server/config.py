"""集中配置管理 — 所有路径、常量、环境变量统一从此文件获取。

避免在业务代码中硬编码路径和密钥，修改配置只需改这一个文件。
"""

import os


# === 目录路径 ===
# 项目根目录（kb_server 的上一级）
PROJECT_ROOT: str = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# 知识库 Markdown 文件根目录
KB_ROOT: str = os.path.join(PROJECT_ROOT, "kb")

# kb_server 包自身目录
PACKAGE_DIR: str = os.path.dirname(os.path.abspath(__file__))

# 模板目录（Jinja2 HTML 模板）
TEMPLATES_DIR: str = os.path.join(PACKAGE_DIR, "templates")

# 静态资源目录（CSS、JS）
STATIC_DIR: str = os.path.join(PACKAGE_DIR, "static")

# 上传文件存储目录
UPLOAD_DIR: str = os.path.join(KB_ROOT, "uploads")
VIDEO_DIR: str = os.path.join(UPLOAD_DIR, "videos")
FRAME_DIR: str = os.path.join(UPLOAD_DIR, "frames")
AUDIO_DIR: str = os.path.join(UPLOAD_DIR, "audio")

# === FFmpeg 路径 ===
# FFmpeg 二进制文件路径候选列表（Windows 环境）
FFMPEG_CANDIDATES: list[str] = [
    "ffmpeg",
    "ffmpeg.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\ffmpeg\bin\ffmpeg.exe"),
    os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin\ffmpeg.exe"),
    "C:/ffmpeg/bin/ffmpeg.exe",
]

# === AI API 配置（从环境变量读取，避免硬编码密钥） ===
# LLM API 地址
API_BASE: str = os.environ.get(
    "ANTHROPIC_BASE_URL",
    "https://api.deepseek.com/anthropic",
)

# LLM API 密钥（切勿在前端代码或模板中暴露此值）
API_KEY: str = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

# LLM 模型名称
API_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]")

# === 应用配置 ===
# FastAPI 应用标题和版本
APP_TITLE: str = "KB Server"
APP_VERSION: str = "0.2.0"

# 服务监听地址和端口
HOST: str = "127.0.0.1"
PORT: int = 8787

# 知识库界面标题（显示在页面顶部导航栏）
KB_TITLE: str = "个人知识库"

# === 视频处理配置 ===
# 支持的视频文件扩展名
VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv",
}

# 关键帧提取数量
KEYFRAME_COUNT: int = 5

# 场景检测阈值（0.0–1.0，值越大切换越不敏感）
SCENE_THRESHOLD: float = 0.3

# === 搜索配置 ===
# 搜索结果片段上下文长度（字符数）
SNIPPET_CONTEXT: int = 30

# 默认搜索结果数量上限
SEARCH_LIMIT: int = 20

# 标题匹配加权倍数
TITLE_MATCH_BONUS: float = 3.0
