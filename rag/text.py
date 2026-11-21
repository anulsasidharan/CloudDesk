"""Shared tokeniser for fake embeddings and keyword search, so both see words the same way."""

import re

_WORD = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "for", "from", "had", "has", "have", "how", "i", "if", "in", "into", "is", "it", "its", "my", "no", "not", "of", "on", "or", "our", "so", "that", "the", "their", "them", "then", "there", "these", "they", "this", "to", "up", "was", "we", "were", "what", "when", "which", "who", "will", "with", "you", "your"]
)


def stem(word: str) -> str:
    """A deliberately crude suffix stripper: ``codes`` and ``code`` meet, ``locked`` and ``lock``."""
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    return [stem(w) for w in _WORD.findall(text.lower()) if w not in STOPWORDS]
