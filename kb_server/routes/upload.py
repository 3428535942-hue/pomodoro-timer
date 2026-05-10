"""上传路由 — 视频摄取的上传页面和处理 API。

端点：
    GET /upload         上传页面（拖拽上传界面）
    POST /api/upload    视频上传 + 处理流水线 API
"""

import os
import uuid

from fastapi import File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from kb_server.config import KB_TITLE, VIDEO_EXTENSIONS, VIDEO_DIR
from kb_server.services.video_pipeline import process_video


def register_upload_routes(app, jinja):
    """注册上传相关路由。

    参数：
        app: FastAPI 应用实例
        jinja: Jinja2 Environment 实例
    """

    def _template(tpl_name: str, **ctx) -> str:
        tpl = jinja.get_template(tpl_name)
        return tpl.render(kb_title=KB_TITLE, **ctx)

    @app.get("/upload", response_class=HTMLResponse)
    async def upload_page():
        """上传页面 — 提供拖拽上传视频的交互界面。"""
        return _template("upload.html")

    @app.post("/api/upload")
    async def api_upload(file: UploadFile = File(...)):
        """视频上传 API — 接收视频文件，触发摄取流水线。

        处理流程：
            1. 校验文件格式（仅允许 VIDEO_EXTENSIONS 中指定的格式）
            2. 保存文件到 VIDEO_DIR
            3. 执行视频摄取流水线（音频提取 → 关键帧 → 转录 → AI 摘要）

        返回：
            JSON：{video_id, duration, segments, keyframes_count, processing_time}
        """
        if not file.filename:
            return JSONResponse({"error": "未提供文件"}, status_code=400)

        # 校验文件扩展名
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in VIDEO_EXTENSIONS:
            return JSONResponse(
                {"error": f"不支持的格式: {ext}，支持的类型: {', '.join(sorted(VIDEO_EXTENSIONS))}"},
                status_code=400,
            )

        # 保存上传文件
        video_id = str(uuid.uuid4())[:8]
        safe_name = f"{video_id}{ext}"
        filepath = os.path.join(VIDEO_DIR, safe_name)

        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        # 执行视频处理流水线
        result = process_video(filepath, video_id)
        return JSONResponse(result)
