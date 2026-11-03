"""Search and read the FOID docs — the engine behind the /mcp server (routers/mcp.py).

The docs site publishes every page as markdown in {DOCS_SITE_URL}/docs-index.json (generated at build
time, served live by `pnpm dev`). We fetch it, cache it for a few minutes, split pages into sections
by heading, and rank sections with BM25. Read-only; nothing here touches the database.
"""

from __future__ import annotations

import math
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

CACHE_SECONDS = 600
_WORD = re.compile(r"[a-z0-9_]+")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it", "with", "how", "do", "i", "my",
         "what", "can", "be", "by", "as", "at", "this", "that", "you", "your", "are", "from", "use", "does"}


class DocsUnavailable(Exception):
    pass


@dataclass
class Section:
    page_path: str
    page_title: str
    section: str          # top-level docs section ("Developer guides", "SDKs", …)
    heading: str
    url: str              # page URL with #anchor
    text: str
    tokens: list[str]


@dataclass
class Index:
    site: str
    pages: list[dict[str, Any]]
    sections: list[Section]
    df: dict[str, int]
    avg_len: float
    loaded_at: float


_cache: Index | None = None


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


_SPECIAL = re.compile(r"""[\s~`!@#$%^&*()\-_+=\[\]{}|\\;:"'“”‘’<>,.?/]+""")


def _slug(heading: str) -> str:
    """The anchor VitePress gives a heading (same rule as its slugify)."""
    s = unicodedata.normalize("NFKD", heading)
    s = re.sub(r"[\u0300-\u036f]", "", s)
    s = re.sub(r"[\u0000-\u001f]", "", s)
    s = _SPECIAL.sub("-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    s = re.sub(r"^(\d)", r"_\1", s)
    return s.lower()


def _split(page: dict[str, Any]) -> list[Section]:
    out: list[Section] = []
    heading, buf = page["title"], []

    def flush() -> None:
        text = "\n".join(buf).strip()
        if text:
            anchor = "" if heading == page["title"] else f"#{_slug(heading)}"
            body = f"{page['title']} {heading} {heading} {text}"   # headings weigh more
            out.append(Section(page["path"], page["title"], page["section"], heading, page["url"] + anchor, text, tokenize(body)))

    in_code = False
    for line in page["markdown"].splitlines():
        if line.startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{2,3}) (.+)$", line)
        if m:
            flush()
            heading, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    flush()
    return out


def build_index(data: dict[str, Any]) -> Index:
    pages = list(data.get("pages", []))
    sections = [s for p in pages for s in _split(p)]
    df: dict[str, int] = {}
    for s in sections:
        for t in set(s.tokens):
            df[t] = df.get(t, 0) + 1
    avg = sum(len(s.tokens) for s in sections) / max(len(sections), 1)
    return Index(str(data.get("site", "")), pages, sections, df, avg, time.time())


async def fetch_index() -> dict[str, Any]:
    """The docs site's docs-index.json (tests replace this)."""
    s = get_settings()
    url = s.DOCS_INDEX_URL.strip() or f"{s.DOCS_SITE_URL.rstrip('/')}/docs-index.json"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url)
            r.raise_for_status()
            return r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise DocsUnavailable(f"Couldn't load the FOID docs from {url} ({e.__class__.__name__}).") from e


async def index() -> Index:
    global _cache
    if _cache is None or time.time() - _cache.loaded_at > CACHE_SECONDS:
        try:
            _cache = build_index(await fetch_index())
        except DocsUnavailable:
            if _cache is None:
                raise          # nothing cached: report it; otherwise keep serving the stale copy
    return _cache


def search(ix: Index, query: str, limit: int = 5) -> list[dict[str, Any]]:
    q = tokenize(query)
    if not q:
        return []
    n, k1, b = len(ix.sections), 1.4, 0.75
    scored: list[tuple[float, Section]] = []
    for s in ix.sections:
        tf: dict[str, int] = {}
        for t in s.tokens:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t in q:
            f = tf.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n - ix.df[t] + 0.5) / (ix.df[t] + 0.5))
            score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(s.tokens) / ix.avg_len))
        if query.lower().strip() in s.text.lower():
            score *= 1.5                                    # exact phrase
        if score > 0:
            scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [{"title": s.page_title if s.heading == s.page_title else f"{s.page_title} › {s.heading}",
             "section": s.section, "url": s.url, "markdown_url": f"{ix.site}{s.page_path}",
             "path": s.page_path, "excerpt": _excerpt(s.text)} for _, s in scored[:limit]]


def _excerpt(text: str, size: int = 700) -> str:
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    return text if len(text) <= size else text[:size].rsplit(" ", 1)[0] + " …"


def find_page(ix: Index, ref: str) -> dict[str, Any] | None:
    """Accepts '/guide/quickstart', 'guide/quickstart.md', a full docs URL, or '/guide/' (index pages)."""
    ref = ref.strip()
    ref = re.sub(r"^https?://[^/]+", "", ref).split("#")[0].split("?")[0] or "/"
    if not ref.startswith("/"):
        ref = "/" + ref
    candidates = [ref, ref + ".md", ref.rstrip("/") + "/index.md", ref + "index.md"]
    for p in ix.pages:
        if p["path"] in candidates:
            return p
    return None
