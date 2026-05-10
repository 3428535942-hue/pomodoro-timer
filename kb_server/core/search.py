"""SearchEngine — 基于二元分词（Bigram）的中文全文搜索引擎。

采用倒排索引 + TF 评分算法：
    - 中文文本按相邻两字切分为 bigram（如"知识库"→"知识""识库"）
    - ASCII/英文单词保留空格分隔
    - 查询时对每个 bigram 查倒排索引，按词频累加评分
    - 标题命中获得 3 倍加权
    - 文档长度归一化（防止长文档霸占排名）

为什么用 Bigram 而非专业分词库：
    对小型个人知识库（< 1000 页），Bigram 速度快、无依赖、
    对中文覆盖好，且无需加载大型分词模型。
"""

import re
from collections import defaultdict

from kb_server.config import SNIPPET_CONTEXT, SEARCH_LIMIT, TITLE_MATCH_BONUS
from kb_server.models import SearchResult


# ------------------------------------------------------------------
# 公开 API
# ------------------------------------------------------------------


class SearchEngine:
    """内存搜索引擎 —— 倒排索引 + Bigram 分词。

    用法：
        engine = SearchEngine()
        engine.index(pages)          # 扫描后建立索引
        results = engine.search("关键词")  # 搜索
    """

    def __init__(self):
        # term -> {页面路径集合} 的倒排索引
        self.inverted_index: dict[str, set[str]] = defaultdict(set)
        # 页面路径 -> bigram 列表（用于 TF 计算）
        self.doc_bigrams: dict[str, list[str]] = {}
        # 页面路径 -> 标题
        self.doc_titles: dict[str, str] = {}
        # 页面路径 -> 原始内容（用于生成摘要片段）
        self.doc_contents: dict[str, str] = {}
        # 页面路径 -> bigram 总数（用于长度归一化）
        self.doc_count: dict[str, int] = {}

    def index(self, pages: dict) -> None:
        """根据扫描器产出的 pages 字典构建搜索索引。

        参数：
            pages: {rel_path: PageInfo} 字典
        """
        self.inverted_index.clear()
        self.doc_bigrams.clear()
        self.doc_titles.clear()
        self.doc_contents.clear()
        self.doc_count.clear()

        for path, info in pages.items():
            # 将标题和内容合并索引（标题可被搜索到）
            text = info.title + " " + info.content
            bigrams = _extract_bigrams(text)

            self.doc_bigrams[path] = bigrams
            self.doc_titles[path] = info.title
            self.doc_contents[path] = info.content
            self.doc_count[path] = len(bigrams)

            # 对每个 bigram 建立倒排记录
            for bg in bigrams:
                self.inverted_index[bg].add(path)

    def search(self, query: str, limit: int = SEARCH_LIMIT) -> list[SearchResult]:
        """执行搜索并返回按相关度降序的结果列表。

        评分策略：
            1. 基础分 = 各 bigram 在文档中的出现次数之和
            2. 标题命中加权 × TITLE_MATCH_BONUS
            3. 文档长度归一化 / (doc_len ** 0.3)

        参数：
            query: 用户输入的搜索关键词
            limit: 返回结果数量上限
        """
        if not query or not query.strip():
            return []

        # 查询词也做 bigram 切分
        query_terms = _extract_bigrams(query)

        # 累加每个 bigram 的 TF 得分
        scores: dict[str, float] = defaultdict(float)
        for term in query_terms:
            for path in self.inverted_index.get(term, set()):
                term_count = self.doc_bigrams[path].count(term)
                scores[path] += term_count

        # 标题命中加权：完整查询词出现在标题中 → 分数 × 3
        query_lower = query.lower()
        for path in list(scores.keys()):
            title = self.doc_titles.get(path, "").lower()
            if query_lower in title:
                scores[path] *= TITLE_MATCH_BONUS

        # 文档长度归一化：防止长文档因 bigram 多而霸榜
        for path in list(scores.keys()):
            doc_len = self.doc_count.get(path, 1)
            scores[path] = scores[path] / (doc_len ** 0.3)

        # 按得分降序排列，取前 limit 条
        ranked = sorted(
            scores.items(), key=lambda x: x[1], reverse=True
        )[:limit]

        # 构建结果：生成带高亮的摘要片段
        results = []
        for path, score in ranked:
            snippet = _make_snippet(
                self.doc_contents[path], [query], SNIPPET_CONTEXT
            )
            results.append(SearchResult(
                path=path,
                title=self.doc_titles[path],
                snippet=snippet,
                score=round(score, 2),
            ))

        return results


# ------------------------------------------------------------------
# 内部函数
# ------------------------------------------------------------------


def _extract_bigrams(text: str) -> list[str]:
    """从文本中提取字符 bigram。

    中文：字符对 → 相邻两个字为一组
    英文/数字：空格分隔的 token 直接保留

    参数：
        text: 输入文本

    返回：
        bigram 字符串列表
    """
    result = []
    chars = list(text)
    for i in range(len(chars) - 1):
        c1, c2 = chars[i], chars[i + 1]
        # 跳过含空白字符的 bigram
        if c1.strip() and c2.strip():
            result.append(c1 + c2)
    return result


def _make_snippet(
    content: str, query_terms: list[str], context: int = SNIPPET_CONTEXT
) -> str:
    """从文档内容中提取最相关的摘要片段，并高亮命中关键词。

    参数：
        content: 文档全文
        query_terms: 查询词列表
        context: 命中的前后各保留多少字符

    返回：
        带 <mark> 高亮标签的 HTML 片段（已转义安全）
    """
    content_lower = content.lower()

    # 找到第一个匹配位置（优先级先到先得）
    best_pos = -1
    for term in query_terms:
        pos = content_lower.find(term.lower())
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    # 无匹配 → 截取文档开头
    if best_pos == -1:
        if len(content) > context * 2:
            return content[:context * 2] + "..."
        return content

    # 截取匹配位置前后的上下文
    start = max(0, best_pos - context)
    end = min(len(content), best_pos + len(query_terms[0]) + context)
    snippet = content[start:end]

    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    # 用 <mark> 标签高亮所有匹配的关键词
    for term in query_terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        snippet = pattern.sub(
            lambda m: f"<mark>{m.group()}</mark>", snippet
        )

    return snippet
