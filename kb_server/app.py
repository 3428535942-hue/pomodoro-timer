"""FastAPI 应用工厂 — 创建和配置知识库 Web 服务。

这是 kb_server 的核心入口文件。负责：
    1. 初始化 Jinja2 模板引擎
    2. 初始化核心服务（扫描器、搜索引擎、图谱构建器）
    3. 注册所有 HTTP 路由
    4. 挂载静态资源目录
    5. 启动时自动扫描知识库

架构分层：
    routes/     → 路由层（请求/响应处理）
    core/       → 核心层（业务逻辑，框架无关）
    services/   → 服务层（复杂流程编排）
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from kb_server.config import (
    APP_TITLE,
    APP_VERSION,
    KB_ROOT,
    TEMPLATES_DIR,
    STATIC_DIR,
    HOST,
    PORT,
)
from kb_server.core.scanner import KBScanner
from kb_server.core.search import SearchEngine
from kb_server.core.graph import GraphBuilder
from kb_server.routes.pages import register_pages_routes
from kb_server.routes.search import register_search_routes
from kb_server.routes.graph import register_graph_routes
from kb_server.routes.upload import register_upload_routes
from kb_server.routes.api import register_api_routes


# ------------------------------------------------------------------
# 初始化服务实例（模块级单例，应用生命周期内复用）
# ------------------------------------------------------------------

# 知识库扫描器 — 负责读取 kb/ 下所有 .md 文件
scanner = KBScanner(KB_ROOT)

# 全文搜索引擎 — Bigram 倒排索引
search_engine = SearchEngine()

# 知识图谱构建器 — 生成 Cytoscape.js 图数据
graph_builder = GraphBuilder()

# Jinja2 模板引擎 — HTML 页面渲染
jinja = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)

# ------------------------------------------------------------------
# FastAPI 应用创建
# ------------------------------------------------------------------

app = FastAPI(title=APP_TITLE, version=APP_VERSION)

# 挂载静态资源目录（CSS、JS 文件）
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ------------------------------------------------------------------
# 注册路由
# ------------------------------------------------------------------

# 页面浏览：首页 + 文章详情
register_pages_routes(app, scanner, jinja)

# 搜索：搜索页 + 搜索 API
register_search_routes(app, jinja, search_engine)

# 图谱：图谱页 + 图谱数据 API
register_graph_routes(app, jinja, graph_builder, scanner)

# 上传：上传页 + 视频处理 API
register_upload_routes(app, jinja)

# 通用 API：页面列表等
register_api_routes(app, scanner)

# ------------------------------------------------------------------
# 启动事件
# ------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    """应用启动时自动扫描知识库并建立搜索索引。

    扫描 kb/ 目录下所有 Markdown 文件，
    解析 wikilink 关系，建立搜索倒排索引。
    """
    pages = scanner.scan()
    search_engine.index(pages)
    print(f"[kb-server] 已索引 {len(pages)} 个页面 (路径: {KB_ROOT})")


# ------------------------------------------------------------------
# 入口
# ------------------------------------------------------------------


def main():
    """启动知识库 Web 服务。

    运行方式：
        python -m kb_server
        或直接调用 kb_server.app:main()
    """
    import uvicorn

    uvicorn.run(
        "kb_server.app:app",
        host=HOST,
        port=PORT,
        reload=False,
    )
