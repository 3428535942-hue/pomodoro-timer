"""KBScanner — walks kb/ directory, parses wikilinks, builds page index."""

import os
import re
from dataclasses import dataclass, field

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
SUMMARY_RE = re.compile(r"^>\s*(.+)$", re.MULTILINE)


@dataclass
class PageInfo:
    rel_path: str           # e.g. "wiki/topics/some-topic.md"
    title: str              # page title (from filename or first heading)
    summary: str            # first > line, or ""
    content: str            # raw markdown content
    wikilinks: list[str] = field(default_factory=list)         # raw [[targets]]
    resolved_links: list[tuple[str, str]] = field(default_factory=list)  # (target, resolved_path)
    backlinks: list[str] = field(default_factory=list)         # paths that link TO this page
    page_type: str = "other"  # topic, atom, raw, other

    @property
    def url_path(self) -> str:
        return self.rel_path.replace("\\", "/")

    @property
    def dir_name(self) -> str:
        parts = self.rel_path.replace("\\", "/").split("/")
        if len(parts) > 1:
            return parts[0]
        return ""

    @property
    def type_label(self) -> str:
        _map = {"topic": "主题", "atom": "概念", "raw": "原始", "other": "其他"}
        return _map.get(self.page_type, self.page_type)


class KBScanner:
    def __init__(self, kb_root: str = "kb"):
        self.kb_root = os.path.abspath(kb_root)
        self.pages: dict[str, PageInfo] = {}       # rel_path -> PageInfo
        self.name_index: dict[str, str] = {}        # page_name -> rel_path

    def scan(self) -> dict[str, PageInfo]:
        """Full scan of kb/ directory. Returns {rel_path: PageInfo}."""
        self.pages.clear()
        self.name_index.clear()

        # First pass: discover all .md files, parse content
        for root, dirs, files in os.walk(self.kb_root):
            # Skip hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, self.kb_root).replace("\\", "/")

                info = self._parse_file(full_path, rel_path)
                self.pages[rel_path] = info

                # Register name -> path
                name = os.path.splitext(fname)[0]
                self.name_index[name] = rel_path
                # Also register with path prefix for disambiguation
                if "/" in rel_path:
                    self.name_index[name] = rel_path

        # Second pass: resolve wikilinks and compute backlinks
        for rel_path, info in self.pages.items():
            current_dir = os.path.dirname(rel_path)
            for target in info.wikilinks:
                resolved = self._resolve_link(target, current_dir)
                if resolved:
                    info.resolved_links.append((target, resolved))
                    # Register backlink on target page
                    if resolved in self.pages:
                        self.pages[resolved].backlinks.append(rel_path)

        return self.pages

    def _parse_file(self, full_path: str, rel_path: str) -> PageInfo:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract wikilinks
        wikilinks = WIKILINK_RE.findall(content)

        # Extract summary (first > line)
        summary = ""
        m = SUMMARY_RE.search(content)
        if m:
            summary = m.group(1).strip()

        # Determine title
        title = os.path.splitext(os.path.basename(rel_path))[0]

        # Determine page type
        page_type = "other"
        if rel_path.startswith("wiki/topics/"):
            page_type = "topic"
        elif rel_path.startswith("wiki/atoms/"):
            page_type = "atom"
        elif rel_path.startswith("raw/"):
            page_type = "raw"

        return PageInfo(
            rel_path=rel_path,
            title=title,
            summary=summary,
            content=content,
            wikilinks=wikilinks,
            page_type=page_type,
        )

    def _resolve_link(self, target: str, current_dir: str) -> str | None:
        """Resolve a [[link target]] to a relative path, or None if unresolved."""
        # Remove anchor/alias if present
        if "#" in target:
            target = target.split("#")[0]
        target = target.strip()

        if not target:
            return None

        # Relative path link: [[../atoms/concept]]
        if target.startswith("."):
            resolved = os.path.normpath(os.path.join(current_dir, target))
            if not resolved.endswith(".md"):
                resolved += ".md"
            resolved = resolved.replace("\\", "/")
            if resolved in self.pages:
                return resolved
            return None

        # Bare name link: [[concept name]]
        if target in self.name_index:
            return self.name_index[target]

        # Try case-insensitive
        target_lower = target.lower()
        for name, path in self.name_index.items():
            if name.lower() == target_lower:
                return path

        return None

    def get_page(self, rel_path: str) -> PageInfo | None:
        """Get a single page by relative path, with fuzzy matching."""
        # Normalize path separators
        clean = rel_path.replace("\\", "/")
        if clean in self.pages:
            return self.pages[clean]
        # Try case-insensitive match
        clean_lower = clean.lower()
        for p, info in self.pages.items():
            if p.lower() == clean_lower:
                return info
        # Try filename-only match
        filename = clean.split("/")[-1]
        for p, info in self.pages.items():
            if p.lower().endswith("/" + filename.lower()):
                return info
        return None

    def reload(self) -> dict[str, PageInfo]:
        """Rescan and return updated pages."""
        return self.scan()
