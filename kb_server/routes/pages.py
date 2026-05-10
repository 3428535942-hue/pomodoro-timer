"""页面浏览路由 — 知识库首页和文章详情页。

端点：
    GET /            知识库首页（按目录分组的页面列表）
    GET /page/{path} 文章详情页（Markdown 渲染 + 侧边栏导航）
"""

import os

from fastapi import Request
from fastapi.responses import HTMLResponse

from kb_server.config import KB_TITLE
from kb_server.core.renderer import render_markdown


def register_pages_routes(app, scanner, jinja):
    """将页面浏览路由注册到 FastAPI 应用。

    参数：
        app: FastAPI 应用实例
        scanner: KBScanner 实例
        jinja: Jinja2 Environment 实例
    """

    def _template(tpl_name: str, **ctx) -> str:
        """渲染 Jinja2 模板的便捷函数。"""
        tpl = jinja.get_template(tpl_name)
        return tpl.render(kb_title=KB_TITLE, **ctx)

    @app.get("/", response_class=HTMLResponse)
    async def home():
        """知识库首页 — 按目录分组展示所有页面。"""
        # 按目录名分组
        groups: dict[str, list] = {}
        for path, info in sorted(scanner.pages.items()):
            d = info.dir_name or "(root)"
            groups.setdefault(d, []).append(info)

        return _template(
            "browse.html",
            groups=groups,
            page_count=len(scanner.pages),
        )

    @app.get("/page/{path:path}", response_class=HTMLResponse)
    async def view_page(path: str):
        """文章详情页 — 渲染 Markdown 内容并展示页面信息。

        URL 路径中的 {path} 会自动匹配含 / 的完整路径。
        支持多种模糊匹配策略处理路径编码差异。
        """
        from pathlib import Path as FSPath

        # 尝试规范化路径分隔符
        try:
            clean = FSPath(path).as_posix()
        except Exception:
            clean = path.replace("\\", "/")

        # 多级匹配策略
        info = scanner.get_page(clean)
        if not info:
            info = scanner.get_page(path)

        if not info:
            return HTMLResponse(
                _template("404.html", path=clean),
                status_code=404,
            )

        # 渲染 Markdown → HTML（含 wikilink 解析）
        current_dir = os.path.dirname(info.rel_path)
        html = render_markdown(
            info.content,
            scanner.name_index,
            scanner.pages,
            current_dir,
        )

        return _template("page.html", page=info, html=html)
