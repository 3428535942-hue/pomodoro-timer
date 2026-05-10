"""搜索路由 — 搜索页面和搜索 API。

端点：
    GET /search       搜索页面（HTML 表单 + 结果列表）
    GET /api/search   搜索 API（JSON 格式，用于 AJAX 调用）
"""

from fastapi import Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from kb_server.config import KB_TITLE, SEARCH_LIMIT


def register_search_routes(app, jinja, search_engine):
    """注册搜索相关路由。

    参数：
        app: FastAPI 应用实例
        jinja: Jinja2 Environment 实例
        search_engine: SearchEngine 实例
    """

    def _template(tpl_name: str, **ctx) -> str:
        tpl = jinja.get_template(tpl_name)
        return tpl.render(kb_title=KB_TITLE, **ctx)

    @app.get("/search", response_class=HTMLResponse)
    async def search_page(request: Request):
        """搜索页面 — 支持 GET 表单提交和结果显示。"""
        q = request.query_params.get("q", "").strip()
        results = search_engine.search(q) if q else []
        return _template("search.html", query=q, results=results)

    @app.get("/api/search")
    async def api_search(
        q: str = Query(""),
        limit: int = Query(SEARCH_LIMIT),
    ):
        """搜索 API — 返回 JSON 格式的搜索结果。

        查询参数：
            q: 搜索关键词
            limit: 返回数量上限
        """
        results = search_engine.search(q, limit)
        return JSONResponse([dict(r._asdict()) for r in results])
