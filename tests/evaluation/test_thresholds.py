"""P14-1: the five evaluation thresholds from CLAUDE.md section 13. A miss fails the build.

| Metric                                   | Bar    | Cases scored                          |
|------------------------------------------|--------|---------------------------------------|
| classification accuracy                  | >=0.80 | every case in datasets/eval_cases.json |
| retrieval hit-rate@3                     | >=0.75 | every case that names expected articles |
| escalation correctness (flag and team)   | >=0.90 | every case                             |
| citation rate                            | >=0.90 | the 13 demo tickets, full pipeline     |
| grounding rate (steps present in reply)  | >=0.90 | the 13 demo tickets, full pipeline     |

Everything runs offline with the fake provider. Each metric is a plain function so the report
test can print them all together.
"""

import json
import pathlib

import pytest
from app.schemas.common import Severity

from agents.specialists import EscalationAgent, SupervisorAgent
from rag.retriever import retrieve

DATASET = pathlib.Path(__file__).resolve().parents[2] / "datasets" / "eval_cases.json"
CASES = json.loads(DATASET.read_text(encoding="utf-8"))
DEMO_IDS = [f"CD-{n}" for n in range(1001, 1014)]

THRESHOLDS = {
    "classification_accuracy": 0.80,
    "retrieval_hit_rate_at_3": 0.75,
    "escalation_correctness": 0.90,
    "citation_rate": 0.90,
    "grounding_rate": 0.90,
}


def _rate(hits: int, total: int) -> float:
    return hits / total if total else 0.0


async def classification_accuracy() -> tuple[float, list]:
    misses = []
    for case in CASES:
        got = (await SupervisorAgent().understand(case["subject"], case["body"])).output.category
        if got.value != case["expected_category"]:
            misses.append((case["id"], got.value))
    return _rate(len(CASES) - len(misses), len(CASES)), misses


async def retrieval_hit_rate_at_3(store) -> tuple[float, list]:
    scored = [c for c in CASES if c["expected_articles"]]
    misses = []
    for case in scored:
        hits = await retrieve(
            f"{case['subject']} {case['body']}", store=store, top_k=3, use_cache=False
        )
        if not {h.title for h in hits} & set(case["expected_articles"]):
            misses.append(case["id"])
    return _rate(len(scored) - len(misses), len(scored)), misses


async def escalation_correctness() -> tuple[float, list]:
    wrong = []
    for case in CASES:
        decision = (
            await EscalationAgent().run(case["subject"], case["body"], case["plan"], Severity.MEDIUM)
        ).output
        if (decision.escalation_required, decision.team) != (
            case["expected_escalation"],
            case["expected_team"],
        ):
            wrong.append((case["id"], decision.team))
    return _rate(len(CASES) - len(wrong), len(CASES)), wrong


async def citation_and_grounding(pipeline) -> tuple[tuple[float, list], tuple[float, list]]:
    uncited, ungrounded = [], []
    for number in DEMO_IDS:
        run = await pipeline(number)
        if not run.plan.citations or not all(c.startswith("kb://") for c in run.plan.citations):
            uncited.append(number)
        reply = run.plan.customer_reply.lower()
        if not all(step.lower() in reply for step in run.diag.steps):
            ungrounded.append(number)
    n = len(DEMO_IDS)
    return (_rate(n - len(uncited), n), uncited), (_rate(n - len(ungrounded), n), ungrounded)


@pytest.fixture
async def eval_store(maker):
    from rag import retriever

    return retriever.get_vector_store()


async def test_classification_accuracy(request):
    rate, misses = await classification_accuracy()
    assert rate >= THRESHOLDS["classification_accuracy"], f"{rate:.2f}; misses {misses}"


async def test_retrieval_hit_rate_at_3(eval_store):
    rate, misses = await retrieval_hit_rate_at_3(eval_store)
    assert rate >= THRESHOLDS["retrieval_hit_rate_at_3"], f"{rate:.2f}; misses {misses}"


async def test_escalation_correctness():
    rate, wrong = await escalation_correctness()
    assert rate >= THRESHOLDS["escalation_correctness"], f"{rate:.2f}; wrong {wrong}"


async def test_citation_and_grounding_rates(pipeline):
    (cite, uncited), (ground, ungrounded) = await citation_and_grounding(pipeline)
    assert cite >= THRESHOLDS["citation_rate"], f"citation {cite:.2f}; uncited {uncited}"
    assert ground >= THRESHOLDS["grounding_rate"], f"grounding {ground:.2f}; ungrounded {ungrounded}"


def test_thresholds_match_claude_md():
    claude_md = (pathlib.Path(__file__).resolve().parents[2] / "CLAUDE.md").read_text(encoding="utf-8")
    for bar in ("0.80", "0.75", "0.90"):
        assert bar in claude_md
    assert sorted(THRESHOLDS.values()) == [0.75, 0.80, 0.90, 0.90, 0.90]
