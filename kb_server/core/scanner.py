"""KBScanner — 知识库文件扫描器。

遍历 kb/ 目录下的所有 Markdown 文件，解析 wikilink 语法（[[目标]]），
建立页面名称索引、正向链接和反向链接关系。

核心职责：
    - 扫描 kb/ 下所有 .md 文件
    - 提取页面元数据（标题、摘要、类型）
    - 用正则匹配 [[wikilink]] 语法
    - 解析链接目标为实际文件路径
    - 计算反向链接图（谁链接到了我）
"""

import os
import re
from pathlib import Path

from kb_server.config import KB_ROOT
from kb_server.models import PageInfo

# 匹配 [[页面名]] 或 [[页面名#锚点]] 的正则表达式
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# 匹配 Markdown 中第一个 > 开头的摘要行
SUMMARY_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)


class KBScanner:
    """知识库文件扫描器 —— 遍历、解析、建立链接索引。

    用法：
        scanner = KBScanner()
        pages = scanner.scan()  # 返回 {rel_path: PageInfo}
    """

    def __init__(self, kb_root: str | None = None):
        """初始化扫描器。

        参数：
            kb_root: 知识库根目录路径，默认使用 config.KB_ROOT
        """
        self.kb_root: str = os.path.abspath(kb_root or KB_ROOT)
        # 页面存储：相对路径 → PageInfo
        self.pages: dict[str, PageInfo] = {}
        # 名称索引：文件名（不含扩展名）→ 相对路径（用于 wikilink 解析）
        self.name_index: dict[str, str] = {}

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def scan(self) -> dict[str, PageInfo]:
        """执行全量扫描，返回 {相对路径: PageInfo} 字典。

        分为两趟：
            第一趟 — 发现所有 .md 文件，解析内容和 wikilink 目标
            第二趟 — 解析 wikilink 目标为实际文件路径，建立反向链接
        """
        self.pages.clear()
        self.name_index.clear()

        # 第一趟：发现和解析
        self._first_pass()

        # 第二趟：链接解析和反向链接
        self._second_pass()

        return self.pages

    def get_page(self, rel_path: str) -> PageInfo | None:
        """根据相对路径获取单个页面信息，支持模糊匹配。

        匹配策略（按优先级）：
            1. 精确路径匹配
            2. 大小写不敏感匹配
            3. 仅文件名匹配
        """
        # 统一路径分隔符
        clean = rel_path.replace("\\", "/")

        # 精确匹配
        if clean in self.pages:
            return self.pages[clean]

        # 大小写不敏感
        clean_lower = clean.lower()
        for p, info in self.pages.items():
            if p.lower() == clean_lower:
                return info

        # 仅文件名匹配
        filename = clean.split("/")[-1]
        for p, info in self.pages.items():
            if p.lower().endswith("/" + filename.lower()):
                return info

        return None

    def reload(self) -> dict[str, PageInfo]:
        """重新扫描知识库（当文件有变更时调用）。"""
        return self.scan()

    # ------------------------------------------------------------------
    # 内部方法：扫描过程
    # ------------------------------------------------------------------

    def _first_pass(self) -> None:
        """第一趟扫描：遍历文件、解析内容、注册名称索引。"""
        for root, dirs, files in os.walk(self.kb_root):
            # 跳过隐藏目录（如 .git、.claude）
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for fname in files:
                if not fname.endswith(".md"):
                    continue

                full_path = os.path.join(root, fname)
                rel_path = (
                    os.path.relpath(full_path, self.kb_root).replace("\\", "/")
                )

                # 解析文件内容
                info = self._parse_file(full_path, rel_path)
                self.pages[rel_path] = info

                # 注册文件名 → 路径（用于 [[页面名]] 解析）
                name = os.path.splitext(fname)[0]
                self.name_index[name] = rel_path

    def _second_pass(self) -> None:
        """第二趟扫描：解析 [] 链接并建立反向链接。"""
        for rel_path, info in self.pages.items():
            # 当前页面所在目录（用于解析相对链接如 [[../atoms/概念]]）
            current_dir = os.path.dirname(rel_path)

            for target in info.wikilinks:
                resolved = self._resolve_link(target, current_dir)
                if resolved:
                    info.resolved_links.append((target, resolved))
                    # 在目标页面上记录反向链接
                    if resolved in self.pages:
                        self.pages[resolved].backlinks.append(rel_path)

    # ------------------------------------------------------------------
    # 内部方法：文件解析
    # ------------------------------------------------------------------

    def _parse_file(self, full_path: str, rel_path: str) -> PageInfo:
        """解析单个 Markdown 文件，提取元数据和内容。

        参数：
            full_path: 文件绝对路径
            rel_path: 相对于 kb/ 根目录的路径

        返回：
            填充了 title/summary/content/wikilinks/page_type 的 PageInfo
        """
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 提取所有 [[wikilink]] 目标
        wikilinks = WIKILINK_RE.findall(content)

        # 提取摘要（第一个 > 开头的行作为摘要句）
        summary = ""
        m = SUMMARY_RE.search(content)
        if m:
            summary = m.group(1).strip()

        # 从文件名提取标题（去掉 .md 扩展名）
        title = os.path.splitext(os.path.basename(rel_path))[0]

        # 根据目录前缀判断页面类型
        page_type = self._classify_page(rel_path)

        return PageInfo(
            rel_path=rel_path,
            title=title,
            summary=summary,
            content=content,
            wikilinks=wikilinks,
            page_type=page_type,
        )

    @staticmethod
    def _classify_page(rel_path: str) -> str:
        """根据文件路径判断页面类型。

        规则：
            wiki/topics/* → topic（主题页）
            wiki/atoms/*  → atom（概念页）
            raw/*         → raw（原始资料）
            其他          → other
        """
        if rel_path.startswith("wiki/topics/"):
            return "topic"
        if rel_path.startswith("wiki/atoms/"):
            return "atom"
        if rel_path.startswith("raw/"):
            return "raw"
        return "other"

    # ------------------------------------------------------------------
    # 内部方法：链接解析
    # ------------------------------------------------------------------

    def _resolve_link(self, target: str, current_dir: str) -> str | None:
        """将 [[目标]] 中的链接名解析为实际文件路径。

        处理三种链接格式：
            1. 相对路径链接：[[../atoms/概念名]] — 基于当前目录
            2. 裸名称链接：[[概念名]] — 从 name_index 查找
            3. 大小写不敏感兜底

        参数：
            target: wikilink 中的目标文本（可能含 #anchor）
            current_dir: 当前页面所在目录

        返回：
            解析后的相对路径，如果找不到则返回 None
        """
        # 去掉可能存在的 # 锚点或别名
        if "#" in target:
            target = target.split("#")[0]
        target = target.strip()

        if not target:
            return None

        # 情况 1：以 . 或 .. 开头的相对路径
        if target.startswith("."):
            resolved = os.path.normpath(
                os.path.join(current_dir, target)
            )
            if not resolved.endswith(".md"):
                resolved += ".md"
            resolved = resolved.replace("\\", "/")
            if resolved in self.pages:
                return resolved
            return None

        # 情况 2：从名称索引中精确匹配
        if target in self.name_index:
            return self.name_index[target]

        # 情况 3：大小写不敏感兜底
        target_lower = target.lower()
        for name, path in self.name_index.items():
            if name.lower() == target_lower:
                return path

        return None
