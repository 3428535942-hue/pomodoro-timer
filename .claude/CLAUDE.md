# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 知识库规则（必读）

处理 `kb/` 目录下的任何知识管理操作前，**必须先读取**：
- `kb/CLAUDE.md` — 渐构世界模型驱动的知识库操作总规则
- `kb/AGENTS.md` — AI 五步流水线操作规范

核心约束：所有资料整理和概念提取必须遵循**概念五组**（对象/属性/关系/操作/情境）+ **抽象层级**（底层/中层/高层）的命名分类体系。

## How to run
```bash
python pomodoro.py
```

## Architecture

Single-file Tkinter desktop app — no build system, no package manager, no tests.

**`PomodoroApp`** is the sole class. It manages three timer modes (pomodoro / short_break / long_break), a circular canvas progress ring, and a per-day session log.

**State files** (auto-created alongside `pomodoro.py`):
- `pomodoro_settings.json` — user-configured durations (in seconds) + completed pomodoro count
- `pomodoro_log.json` — per-day log entries keyed by `"YYYY-MM-DD"`

**Settings dialog** allows adjusting duration for each mode (1–120 minutes), validated on save.

## Platform dependency

`winsound.Beep` is used for completion alerts — Windows only. Porting to other platforms requires replacing this call.

---

## kb_server — 知识库 Web 服务

### 启动
```bash
pip install -e ".[dev]"
python -m kb_server          # http://127.0.0.1:8787
```

### 分层架构
```
kb_server/
├── app.py                  # FastAPI 应用工厂（入口）
├── config.py               # 集中配置（路径/API密钥/常量）
├── models.py               # PageInfo, SearchResult 数据模型
├── core/                   # 业务逻辑（框架无关，可独立测试）
│   ├── scanner.py           # KBScanner — 文件扫描 + wikilink 解析
│   ├── search.py            # SearchEngine — Bigram 倒排索引
│   ├── graph.py             # GraphBuilder — 知识图谱数据
│   └── renderer.py          # Markdown → HTML（wikilink 预处理）
├── routes/                 # 路由层（薄层：参数提取 + 调用 core + 返回响应）
│   ├── pages.py             # GET /, /page/{path}
│   ├── search.py            # GET /search, /api/search
│   ├── graph.py             # GET /graph, /api/graph
│   ├── upload.py            # GET /upload, POST /api/upload
│   └── api.py               # GET /api/pages
├── services/               # 服务层（复杂流程编排）
│   └── video_pipeline.py    # 视频摄取流水线
├── templates/              # Jinja2 HTML 模板
└── static/                 # CSS + JS 静态资源
```

### 测试
```bash
pytest tests/ -v
```
