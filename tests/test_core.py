"""核心模块测试 — 扫描器、搜索引擎、图谱构建器。"""

import os
import sys
import tempfile
import textwrap

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb_server.models import PageInfo
from kb_server.core.scanner import KBScanner
from kb_server.core.search import SearchEngine, _extract_bigrams, _make_snippet
from kb_server.core.graph import GraphBuilder


class TestBigramExtraction:
    """二元分词提取测试。"""

    def test_chinese_bigrams(self):
        """中文文本应拆分为相邻字符对。"""
        bg = _extract_bigrams("知识库")
        assert "知识" in bg
        assert "识库" in bg

    def test_empty_string(self):
        """空字符串应返回空列表。"""
        assert _extract_bigrams("") == []

    def test_short_string(self):
        """单字符应返回空列表（无法形成 bigram）。"""
        assert _extract_bigrams("知") == []


class TestSnippetGeneration:
    """搜索摘要生成测试。"""

    def test_snippet_highlights_match(self):
        """摘要应包含 <mark> 高亮标签。"""
        content = "这是一段测试文本，用于验证搜索高亮功能是否正常工作。"
        snippet = _make_snippet(content, ["高亮"])
        assert "<mark>高亮</mark>" in snippet

    def test_snippet_no_match(self):
        """无匹配时返回内容开头。"""
        content = "简短文本"
        snippet = _make_snippet(content, ["不存在"])
        assert len(snippet) > 0


class TestSearchEngine:
    """搜索引擎测试。"""

    def test_index_and_search(self):
        """索引后应能搜索到页面。"""
        engine = SearchEngine()
        pages = {
            "wiki/atoms/test.md": PageInfo(
                rel_path="wiki/atoms/test.md",
                title="测试概念",
                summary="一个测试概念",
                content="这是一个测试概念页面，包含测试相关知识内容。",
            ),
        }
        engine.index(pages)
        results = engine.search("测试")
        assert len(results) > 0
        assert results[0].title == "测试概念"

    def test_title_match_boost(self):
        """标题命中应获得加权。"""
        engine = SearchEngine()
        pages = {
            "wiki/atoms/ai.md": PageInfo(
                rel_path="wiki/atoms/ai.md",
                title="人工智能",
                content="机器学习是人工智能的一个分支。",
            ),
            "wiki/atoms/ml.md": PageInfo(
                rel_path="wiki/atoms/ml.md",
                title="机器学习",
                content="各种算法相关内容。人工智能是背景。",
            ),
        }
        engine.index(pages)
        results = engine.search("人工智能")
        # 标题完全匹配"人工智能"的页面应排第一
        assert results[0].title == "人工智能"

    def test_empty_query(self):
        """空查询应返回空列表。"""
        engine = SearchEngine()
        engine.index({})
        assert engine.search("") == []
        assert engine.search("   ") == []


class TestScanner:
    """知识库扫描器测试。"""

    def test_scan_creates_index(self):
        """扫描后应建立名称索引。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建最小知识库结构
            wiki_dir = os.path.join(tmpdir, "wiki", "atoms")
            os.makedirs(wiki_dir)
            test_file = os.path.join(wiki_dir, "测试概念.md")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("> 测试摘要\n\n# 标题\n\n内容 [[另一个概念]]")

            scanner = KBScanner(tmpdir)
            pages = scanner.scan()

            assert len(pages) == 1
            page = list(pages.values())[0]
            assert page.page_type == "atom"
            assert page.summary == "测试摘要"
            assert "另一个概念" in page.wikilinks

    def test_page_classification(self):
        """页面类型分类测试。"""
        assert KBScanner._classify_page("wiki/topics/test.md") == "topic"
        assert KBScanner._classify_page("wiki/atoms/test.md") == "atom"
        assert KBScanner._classify_page("raw/test.md") == "raw"
        assert KBScanner._classify_page("somewhere/else/test.md") == "other"


class TestGraphBuilder:
    """图谱构建器测试。"""

    def test_build_minimal_graph(self):
        """最小图谱应包含节点和边。"""
        builder = GraphBuilder()
        pages = {
            "wiki/atoms/a.md": PageInfo(
                rel_path="wiki/atoms/a.md",
                title="概念A",
                content="引用 [[概念B]]",
                wikilinks=["概念B"],
                resolved_links=[("概念B", "wiki/atoms/b.md")],
                page_type="atom",
            ),
            "wiki/atoms/b.md": PageInfo(
                rel_path="wiki/atoms/b.md",
                title="概念B",
                content="被引用",
                backlinks=["wiki/atoms/a.md"],
                page_type="atom",
            ),
        }
        data = builder.build(pages)
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
