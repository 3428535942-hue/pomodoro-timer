"""Renderer — Markdown 渲染器。

将知识库的 Markdown 内容转换为 HTML，在此过程中：
    1. 将 [[wikilink]] 语法转换为可点击的 HTML 链接
    2. 使用 markdown-it 库渲染标准 Markdown 语法

包含 wikilink 预处理：
    [[页面名]]          → 通过名称索引解析为页面链接
    [[../atoms/概念]]   → 通过相对路径解析
    [[页面名#anchor]]   → 支持锚点链接
"""

import os
import re

from markdown_it import MarkdownIt

# 匹配 [[...]] wikilink 的正则（与 scanner.py 中的一致）
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# 初始化 markdown-it 实例（CommonMark + 表格 + 删除线 + HTML）
_md_parser = MarkdownIt("commonmark", {"breaks": True, "html": True}).enable(
    ["table", "strikethrough"]
)


def render_markdown(
    text: str,
    name_index: dict[str, str],
    pages: dict,
    current_dir: str = "",
) -> str:
    """将 Markdown 文本渲染为 HTML，wikilink 会转换为可点击链接。

    参数：
        text: 原始 Markdown 文本
        name_index: 文件名 → 路径的名称索引（来自 KBScanner.name_index）
        pages: 已扫描的页面字典（用于验证链接目标是否存在）
        current_dir: 当前页面所在目录（用于解析相对 wikilink）

    返回：
        渲染后的 HTML 字符串
    """
    # 第一步：将 [[wikilink]] 替换为 Markdown 链接 [text](/page/path)
    text_with_links = _preprocess_wikilinks(text, name_index, pages, current_dir)

    # 第二步：标准 Markdown → HTML
    return _md_parser.render(text_with_links)


def _preprocess_wikilinks(
    text: str,
    name_index: dict[str, str],
    pages: dict,
    current_dir: str = "",
) -> str:
    """将 [[目标]] 语法转换为 Markdown [text](/page/resolved_path) 链接。

    未解析的链接渲染为 `[text](#)`（不可点击占位）。
    含 # 锚点的链接保留锚点部分。
    """

    def replacer(match: re.Match) -> str:
        target = match.group(1)
        # 保存锚点部分（如有）
        anchor = target
        target_name = target
        if "#" in target:
            target_name, anchor_fragment = target.split("#", 1)
        else:
            anchor_fragment = ""

        target_name = target_name.strip()
        resolved = _resolve_wikilink_target(target_name, name_index, pages, current_dir)

        if resolved:
            return f"[{anchor}](/page/{resolved})"
        # 未找到目标 → 占位链接
        return f"[{anchor}](#)"

    return WIKILINK_RE.sub(replacer, text)


def _resolve_wikilink_target(
    target: str,
    name_index: dict[str, str],
    pages: dict,
    current_dir: str = "",
) -> str | None:
    """将 wikilink 目标文本解析为实际文件路径。

    支持三种格式：
        1. [[../atoms/概念]] — 相对路径
        2. [[概念名]] — 裸名称
        3. 大小写不敏感兜底

    参数：
        target: wikilink 目标文本（无锚点部分）
        name_index: 名称索引
        pages: 页面字典
        current_dir: 当前页面目录

    返回：
        解析后的相对路径，找不到则返回 None
    """
    if not target or not target.strip():
        return None

    target = target.strip()

    # 相对路径链接
    if target.startswith("."):
        resolved = os.path.normpath(os.path.join(current_dir, target))
        if not resolved.endswith(".md"):
            resolved += ".md"
        resolved = resolved.replace("\\", "/")
        return resolved if resolved in pages else None

    # 裸名称精确匹配
    if target in name_index:
        return name_index[target]

    # 大小写不敏感兜底
    target_lower = target.lower()
    for name, path in name_index.items():
        if name.lower() == target_lower:
            return path

    return None
