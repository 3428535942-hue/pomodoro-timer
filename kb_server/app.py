"""FastAPI application for knowledge base web interface."""

import os
import re
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

import uuid

from fastapi import File, UploadFile

from kb_server.scanner import KBScanner, WIKILINK_RE
from kb_server.search import SearchEngine
from kb_server.graph import GraphBuilder
from kb_server.video_pipeline import process_video, VIDEO_DIR

# Init
KB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kb")
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

scanner = KBScanner(KB_ROOT)
search_engine = SearchEngine()
graph_builder = GraphBuilder()
md = MarkdownIt("commonmark", {"breaks": True, "html": True}).enable(["table", "strikethrough"])

jinja = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
)

app = FastAPI(title="KB Server", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def preprocess_wikilinks(text: str, current_dir: str = "") -> str:
    """Convert [[target]] to clickable Markdown links."""
    def replacer(match):
        target = match.group(1)
        anchor = target
        if "#" in target:
            target, _ = target.split("#", 1)
        target = target.strip()
        resolved = scanner._resolve_link(target, current_dir) if current_dir else scanner.name_index.get(target)
        if resolved:
            return f'[{anchor}](/page/{resolved})'
        return f'[{anchor}](#)'
    return WIKILINK_RE.sub(replacer, text)


def render_markdown(text: str, current_dir: str = "") -> str:
    """Render markdown to HTML with wikilinks resolved."""
    text = preprocess_wikilinks(text, current_dir)
    return md.render(text)


def template(tpl_name: str, **ctx) -> str:
    """Render a Jinja2 template."""
    tpl = jinja.get_template(tpl_name)
    return tpl.render(kb_title="个人知识库", **ctx)


@app.on_event("startup")
async def startup():
    pages = scanner.scan()
    search_engine.index(pages)
    print(f"[kb-server] Indexed {len(pages)} pages from {KB_ROOT}")


@app.get("/", response_class=HTMLResponse)
async def home():
    # Group pages by directory
    groups: dict[str, list] = {}
    for path, info in sorted(scanner.pages.items()):
        d = info.dir_name or "(root)"
        groups.setdefault(d, []).append(info)

    return template("browse.html", groups=groups, page_count=len(scanner.pages))


@app.get("/page/{path:path}", response_class=HTMLResponse)
async def view_page(path: str):
    # Normalize path: handle URL encoding + Windows backslash
    from pathlib import Path as FSPath
    try:
        clean = FSPath(path).as_posix()
    except Exception:
        clean = path.replace("\\", "/")
    # Also try the raw path as-is
    info = scanner.get_page(clean)
    if not info:
        info = scanner.get_page(path)
    if not info:
        # Try matching by filename only (last component)
        filename = clean.split("/")[-1]
        for p, pi in scanner.pages.items():
            if p.endswith(filename):
                info = pi
                break
    if not info:
        return HTMLResponse(template("404.html", path=clean), status_code=404)

    html = render_markdown(info.content, os.path.dirname(info.rel_path))
    return template("page.html", page=info, html=html)


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    q = request.query_params.get("q", "").strip()
    results = search_engine.search(q) if q else []
    return template("search.html", query=q, results=results)


@app.get("/graph", response_class=HTMLResponse)
async def graph_page():
    return template("graph.html")


@app.get("/upload", response_class=HTMLResponse)
async def upload_page():
    return template("upload.html")


# --- API endpoints ---

@app.get("/api/search")
async def api_search(q: str = Query(""), limit: int = Query(20)):
    results = search_engine.search(q, limit)
    return JSONResponse([dict(r._asdict()) for r in results])


@app.get("/api/graph")
async def api_graph():
    data = graph_builder.build(scanner.pages)
    return JSONResponse(data)


@app.get("/api/pages")
async def api_pages():
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


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse({"error": "No file"}, status_code=400)

    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in video_exts:
        return JSONResponse({"error": f"Unsupported format: {ext}"}, status_code=400)

    video_id = str(uuid.uuid4())[:8]
    safe_name = f"{video_id}{ext}"
    filepath = os.path.join(VIDEO_DIR, safe_name)

    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)

    result = process_video(filepath, video_id)
    return JSONResponse(result)


def main():
    import uvicorn
    uvicorn.run("kb_server.app:app", host="127.0.0.1", port=8787, reload=False)
