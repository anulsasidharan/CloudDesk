"""P9-8: the eval case dataset is valid, and the specialists score on it.

The formal build-failing thresholds arrive with Phase 14. These are the early measurements for the
two metrics that need no database: classification accuracy and escalation correctness.
"""

import json
import pathlib

import pytest
from app.schemas.common import Category, Severity

from agents.specialists import EscalationAgent, SupervisorAgent

DATASET = pathlib.Path(__file__).resolve().parents[2] / "datasets" / "eval_cases.json"
CASES = json.loads(DATASET.read_text(encoding="utf-8"))
REQUIRED = {
    "id", "subject", "body", "plan", "expected_category",
    "expected_escalation", "expected_team", "expected_articles",
}  # fmt: skip


def test_dataset_is_well_formed():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids)) and len(CASES) >= 25
    valid = {c.value for c in Category}
    for case in CASES:
        assert REQUIRED <= case.keys(), case["id"]
        assert case["expected_category"] in valid, case["id"]
        assert case["plan"] in {"free", "pro", "business", "enterprise"}
        assert (case["expected_team"] is not None) == case["expected_escalation"], case["id"]


def test_dataset_covers_all_thirteen_demo_tickets_and_both_outcomes():
    ids = {c["id"] for c in CASES}
    assert {f"CD-{n}" for n in range(1001, 1014)} <= ids
    assert any(c["expected_escalation"] for c in CASES) and not all(
        c["expected_escalation"] for c in CASES
    )


async def test_classification_accuracy_meets_the_bar():
    hits = 0
    misses = []
    for case in CASES:
        result = await SupervisorAgent().understand(case["subject"], case["body"])
        if result.output.category.value == case["expected_category"]:
            hits += 1
        else:
            misses.append((case["id"], result.output.category.value))
    assert hits / len(CASES) >= 0.80, misses


async def test_escalation_correctness_meets_the_bar():
    right = 0
    wrong = []
    for case in CASES:
        decision = (
            await EscalationAgent().run(case["subject"], case["body"], case["plan"], Severity.MEDIUM)
        ).output
        if (
            decision.escalation_required == case["expected_escalation"]
            and decision.team == case["expected_team"]
        ):
            right += 1
        else:
            wrong.append((case["id"], decision.team))
    assert right / len(CASES) >= 0.90, wrong


@pytest.mark.parametrize("number", ["CD-1005", "CD-1006", "CD-1009", "CD-1011"])
def test_the_four_policy_tickets_expect_escalation(number):
    case = next(c for c in CASES if c["id"] == number)
    assert case["expected_escalation"] is True
