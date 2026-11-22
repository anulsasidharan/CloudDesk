"""Knowledge Agent (F5, F6): cited evidence from the knowledge base and similar solved cases."""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

from app.schemas.workflow import EvidenceItem, KnowledgeResult, PreviousCase, ToolCallRecord
from app.services.seed_service import resolve_data_dir
from app.tools import ToolRegistry

from agents.specialists.base import AgentResult, elapsed_ms, run_tool
from rag.text import tokenize

TOP_K_EVIDENCE = 3
TOP_K_CASES = 3
SAME_CATEGORY_BONUS = 0.1
MIN_SIMILARITY = 0.1  # a different-category case needs at least this much word overlap


@lru_cache(maxsize=4)
def _load_cases(path: str) -> tuple[dict, ...]:
    file = Path(path)
    return tuple(json.loads(file.read_text(encoding="utf-8"))) if file.is_file() else ()


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


class KnowledgeAgent:
    async def run(
        self,
        subject: str,
        body: str,
        category: str | None = None,
        registry: ToolRegistry | None = None,
    ) -> AgentResult[KnowledgeResult]:
        started = time.perf_counter()
        calls: list[ToolCallRecord] = []
        query = f"{subject} {body}"
        search = await run_tool(
            registry,
            "search_docs",
            {"query": query, "category": category, "top_k": TOP_K_EVIDENCE},
            calls,
        )
        evidence = (
            [EvidenceItem(**e) for e in (search.data or {}).get("evidence", [])]
            if search.ok
            else []
        )
        result = KnowledgeResult(evidence=evidence, previous_cases=self.similar_cases(query, category))
        return AgentResult(result, duration_ms=elapsed_ms(started), tool_calls=calls)

    def similar_cases(
        self, text: str, category: str | None = None, top_k: int = TOP_K_CASES
    ) -> list[PreviousCase]:
        """Previously resolved cases ranked by word overlap (Jaccard); same category gets a bonus."""
        path = resolve_data_dir() / "previous_resolutions.json"
        query_terms = set(tokenize(text))
        scored: list[PreviousCase] = []
        for case in _load_cases(str(path)):
            overlap = jaccard(query_terms, set(tokenize(f"{case['subject']} {case['resolution']}")))
            same = bool(category) and case["category"] == category
            if not same and overlap < MIN_SIMILARITY:
                continue
            scored.append(
                PreviousCase(
                    key=case["key"],
                    category=case["category"],
                    subject=case["subject"],
                    resolution=case["resolution"],
                    steps=list(case.get("steps", [])),
                    similarity=round(overlap + (SAME_CATEGORY_BONUS if same else 0.0), 4),
                )
            )
        scored.sort(key=lambda c: (-c.similarity, c.key))
        return scored[:top_k]
