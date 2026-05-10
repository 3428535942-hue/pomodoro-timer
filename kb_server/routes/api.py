"""通用 API 路由 — 页面列表等数据接口。

端点：
    GET /api/pages   获取所有页面的列表（含标题、类型、链接关系）
"""

from fastapi.responses import JSONResponse


def register_api_routes(app, scanner):
    """注册通用数据 API 路由。

    参数：
        app: FastAPI 应用实例
        scanner: KBScanner 实例
    """

    @app.get("/api/pages")
    async def api_pages():
        """获取知识库所有页面的结构化列表。

        返回 JSON 数组，每项包含：
            path, title, summary, type, wikilinks, backlinks
        """
        pages = [
            {
                "path": p.rel_path,
                "title": p.title,
                "summary": p.summary,
                "type": p.page_type,
                "wikilinks": p.wikilinks,
                "backlinks": p.backlinks,
            }
            for p in scanner.pages.values()
        ]
        return JSONResponse(pages)
