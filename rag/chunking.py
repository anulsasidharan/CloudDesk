"""P5-1: turn a knowledge article into retrievable chunks.

Rule (CLAUDE.md section 8): split on headings, then cut long sections into 900-character
windows that overlap by 150 characters. Every chunk's text is prefixed with
``"{title} - {heading}"`` so a short chunk such as "Wait 30 minutes" still carries its topic.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class Chunk:
    """One retrievable piece of an article. ``text`` is what gets embedded and keyword-indexed."""

    id: str
    article_id: str
    slug: str
    title: str
    category: str
    heading: str
    content: str
    ordinal: int

    @property
    def text(self) -> str:
        return f"{self.title} - {self.heading}\n{self.content}"

    @property
    def source(self) -> str:
        """Citation id, e.g. ``kb://mfa-recovery#why-accounts-lock``."""
        return f"kb://{self.slug}#{slugify(self.heading)}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "article_id": self.article_id,
            "slug": self.slug,
            "title": self.title,
            "category": self.category,
            "heading": self.heading,
            "content": self.content,
            "ordinal": self.ordinal,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "Chunk":
        return cls(
            id=payload["id"],
            article_id=payload["article_id"],
            slug=payload["slug"],
            title=payload["title"],
            category=payload["category"],
            heading=payload["heading"],
            content=payload["content"],
            ordinal=int(payload["ordinal"]),
        )


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def split_sections(body: str, default_heading: str) -> list[tuple[str, str]]:
    """Split markdown into ``(heading, text)`` pairs. Text before the first heading uses the title.

    A heading with no text under it (the article's own ``# Title`` line) produces no section.
    """
    sections: list[tuple[str, list[str]]] = [(default_heading, [])]
    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            sections.append((match.group(2), []))
        else:
            sections[-1][1].append(line)
    result = []
    for heading, lines in sections:
        text = "\n".join(lines).strip()
        if text:
            result.append((heading, text))
    return result


def window(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Cut ``text`` into windows of at most ``size`` characters, each starting ``overlap`` before
    the previous one ended. Cuts prefer a whitespace boundary so words are not split."""
    if size <= overlap:
        raise ValueError("size must be larger than overlap")
    if len(text) <= size:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + overlap + 1, end)
            if space > start:
                end = space
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [piece for piece in pieces if piece]


def chunk_article(article: Mapping[str, Any]) -> list[Chunk]:
    """Chunk one article record (``id, slug, title, category, body``)."""
    chunks: list[Chunk] = []
    for heading, text in split_sections(article["body"], article["title"]):
        for piece in window(text):
            ordinal = len(chunks)
            chunks.append(
                Chunk(
                    id=f"{article['slug']}:{ordinal}",
                    article_id=article["id"],
                    slug=article["slug"],
                    title=article["title"],
                    category=article["category"],
                    heading=heading,
                    content=piece,
                    ordinal=ordinal,
                )
            )
    return chunks
