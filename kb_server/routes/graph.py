"""图谱路由 — 知识网络可视化页面和图谱数据 API。

端点：
    GET /graph       图谱可视化页面（Cytoscape.js 交互图）
    GET /api/graph   图谱数据 API（节点 + 边 JSON）
"""

from fastapi.responses import HTMLResponse, JSONResponse

from kb_server.config import KB_TITLE


def register_graph_routes(app, jinja, graph_builder, scanner):
    """注册图谱相关路由。

    参数：
        app: FastAPI 应用实例
        jinja: Jinja2 Environment 实例
        graph_builder: GraphBuilder 实例
        scanner: KBScanner 实例（提供 pages 数据源）
    """

    def _template(tpl_name: str, **ctx) -> str:
        tpl = jinja.get_template(tpl_name)
        return tpl.render(kb_title=KB_TITLE, **ctx)

    @app.get("/graph", response_class=HTMLResponse)
    async def graph_page():
        """图谱页面 — 展示知识库中所有页面的网络关系图。"""
        return _template("graph.html")

    @app.get("/api/graph")
    async def api_graph():
        """图谱数据 API — 返回 Cytoscape.js 格式的节点和边数据。"""
        data = graph_builder.build(scanner.pages)
        return JSONResponse(data)
