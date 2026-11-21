"""P5-1: heading split, 900/150 windows, title-prefixed chunks (F5)."""

import itertools

from rag.chunking import CHUNK_OVERLAP, CHUNK_SIZE, chunk_article, slugify, split_sections, window

ARTICLE = {
    "id": "a1",
    "slug": "demo",
    "title": "Demo article",
    "category": "other",
    "body": "# Demo article\n\n## First\nOne.\n\n## Second\nTwo.\n",
}


def test_split_on_headings_and_skip_empty_title_section():
    sections = split_sections(ARTICLE["body"], "Demo article")
    assert [h for h, _ in sections] == ["First", "Second"]


def test_text_before_first_heading_uses_the_title():
    assert split_sections("Intro text.\n## A\nBody", "T")[0] == ("T", "Intro text.")


def test_every_chunk_is_prefixed_with_title_and_heading():
    chunks = chunk_article(ARTICLE)
    assert [c.text for c in chunks] == [
        "Demo article - First\nOne.",
        "Demo article - Second\nTwo.",
    ]
    assert chunks[0].source == "kb://demo#first"
    assert [c.id for c in chunks] == ["demo:0", "demo:1"]


def test_long_section_is_windowed_with_overlap():
    text = " ".join(f"word{i}" for i in range(400))  # ~2.7k characters
    pieces = window(text)
    assert len(pieces) > 2
    assert all(len(p) <= CHUNK_SIZE for p in pieces)
    # the tail of one window reappears at the head of the next
    for left, right in itertools.pairwise(pieces):
        assert right.split()[0] in left[-(CHUNK_OVERLAP + 20) :]
    assert " ".join(pieces).count("word399") >= 1


def test_short_text_is_one_window():
    assert window("short") == ["short"]


def test_slugify():
    assert slugify("Why accounts lock!") == "why-accounts-lock"


def test_all_real_articles_chunk(articles):
    assert len(articles) == 15
    for article in articles:
        chunks = chunk_article(article)
        assert chunks, article["slug"]
        assert all(c.text.startswith(f"{article['title']} - ") for c in chunks)
