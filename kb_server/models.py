"""数据模型 — 知识库页面信息、搜索结果等核心数据结构。

将数据类集中在一个文件中，便于跨模块引用和维护类型一致性。
"""

from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass
class PageInfo:
    """知识库页面信息。

    属性：
        rel_path: 相对于 kb/ 根目录的路径，例如 "wiki/topics/some-topic.md"
        title: 页面标题（优先从文件名提取）
        summary: 页面摘要（Markdown 中第一个 > 开头的行）
        content: 原始 Markdown 全文内容
        wikilinks: 页面中所有 [[目标]] 链接的原始目标列表
        resolved_links: 已解析的链接列表，每项为 (目标名, 已解析路径) 元组
        backlinks: 反向链接 — 链接到本页面的其他页面路径列表
        page_type: 页面类型，取值 topic/atom/raw/other
    """

    rel_path: str
    title: str
    summary: str = ""
    content: str = ""
    wikilinks: list[str] = field(default_factory=list)
    resolved_links: list[tuple[str, str]] = field(default_factory=list)
    backlinks: list[str] = field(default_factory=list)
    page_type: str = "other"

    @property
    def url_path(self) -> str:
        """获取 URL 友好的路径表示（统一使用正斜杠）。"""
        return self.rel_path.replace("\\", "/")

    @property
    def dir_name(self) -> str:
        """获取页面所在目录名（如 wiki/topics → topics）。"""
        parts = self.rel_path.replace("\\", "/").split("/")
        if len(parts) > 1:
            return parts[0]
        return ""

    @property
    def type_label(self) -> str:
        """获取页面类型的中文标签。"""
        _map = {
            "topic": "主题",
            "atom": "概念",
            "raw": "原始",
            "other": "其他",
        }
        return _map.get(self.page_type, self.page_type)


class SearchResult(NamedTuple):
    """搜索结果条目。

    属性：
        path: 页面相对路径
        title: 页面标题
        snippet: 匹配片段（含 <mark> 高亮标签）
        score: 相关性得分
    """

    path: str
    title: str
    snippet: str
    score: float
