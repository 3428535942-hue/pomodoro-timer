"""In-memory search engine with bigram tokenization for Chinese text."""

import re
from collections import defaultdict
from typing import NamedTuple


class SearchResult(NamedTuple):
    path: str
    title: str
    snippet: str
    score: float


def _bigrams(text: str) -> list[str]:
    """Extract character bigrams for Chinese + word tokens for ASCII."""
    result = []
    # Chinese: character bigrams
    chars = list(text)
    for i in range(len(chars) - 1):
        c1, c2 = chars[i], chars[i + 1]
        # Skip space bigrams
        if c1.strip() and c2.strip():
            result.append(c1 + c2)
    return result


def _make_snippet(content: str, query_terms: list[str], context: int = 30) -> str:
    """Extract a snippet around the first matching term."""
    content_lower = content.lower()
    best_pos = -1
    for term in query_terms:
        pos = content_lower.find(term.lower())
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        return content[:context * 2] + ("..." if len(content) > context * 2 else "")

    start = max(0, best_pos - context)
    end = min(len(content), best_pos + len(query_terms[0]) + context)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    # Highlight matching terms
    for term in query_terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        snippet = pattern.sub(lambda m: f"<mark>{m.group()}</mark>", snippet)

    return snippet


class SearchEngine:
    def __init__(self):
        self.inverted_index: dict[str, set[str]] = defaultdict(set)  # term -> {paths}
        self.doc_bigrams: dict[str, list[str]] = {}   # path -> bigram list
        self.doc_titles: dict[str, str] = {}           # path -> title
        self.doc_contents: dict[str, str] = {}         # path -> content
        self.doc_count: dict[str, int] = {}            # path -> total bigram count

    def index(self, pages: dict) -> None:
        """Build inverted index from scanner pages."""
        self.inverted_index.clear()
        self.doc_bigrams.clear()
        self.doc_titles.clear()
        self.doc_contents.clear()
        self.doc_count.clear()

        for path, info in pages.items():
            title = info.title
            content = info.content
            text = title + " " + content
            bigrams = _bigrams(text)
            self.doc_bigrams[path] = bigrams
            self.doc_titles[path] = title
            self.doc_contents[path] = content
            self.doc_count[path] = len(bigrams)

            for bg in bigrams:
                self.inverted_index[bg].add(path)

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """Search and return ranked results."""
        if not query or not query.strip():
            return []

        query_terms = _bigrams(query)

        # Score each document
        scores: dict[str, float] = defaultdict(float)
        for term in query_terms:
            for path in self.inverted_index.get(term, set()):
                # TF scoring
                term_count = self.doc_bigrams[path].count(term)
                scores[path] += term_count

        # Title match bonus
        query_lower = query.lower()
        for path in scores:
            title = self.doc_titles.get(path, "").lower()
            if query_lower in title:
                scores[path] *= 3.0

        # Normalize by doc length (avoid huge docs dominating)
        for path in list(scores.keys()):
            doc_len = self.doc_count.get(path, 1)
            scores[path] = scores[path] / (doc_len ** 0.3)

        # Sort by score desc
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

        # Build results with snippets
        results = []
        for path, score in ranked:
            snippet = _make_snippet(self.doc_contents[path], [query])
            results.append(SearchResult(
                path=path,
                title=self.doc_titles[path],
                snippet=snippet,
                score=round(score, 2),
            ))

        return results
