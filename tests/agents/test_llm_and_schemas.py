"""P9-1: workflow schemas and the fake-capable ``call_structured``."""

import pytest
from app.core import llm
from app.schemas.common import Category
from app.schemas.workflow import Classification, Diagnosis, TokenUsage, merge_usage
from pydantic import ValidationError


async def test_fake_provider_returns_validated_output_with_zero_cost():
    result = await llm.call_structured(
        Classification,
        system="sys",
        user="user text " * 20,
        offline=lambda: Classification(category=Category.BILLING, summary="s"),
    )
    assert result.output.category is Category.BILLING
    assert result.usage.calls == 1
    assert result.usage.cost_usd == 0.0
    assert result.usage.total_tokens == result.usage.input_tokens + result.usage.output_tokens > 0
    assert result.duration_ms >= 0


async def test_real_provider_without_a_model_is_a_typed_error(monkeypatch):
    class FakeSettings:
        llm_provider = "openai"
        llm_model = ""

    monkeypatch.setattr(llm, "get_settings", lambda: FakeSettings())
    with pytest.raises(llm.LLMError):
        await llm.call_structured(
            Classification,
            system="s",
            user="u",
            offline=lambda: Classification(category=Category.OTHER, summary="x"),
        )


def test_category_must_be_one_of_the_ten():
    with pytest.raises(ValidationError):
        Classification(category="made_up", summary="x")


def test_diagnosis_needs_causes_and_steps_and_numbers_them():
    with pytest.raises(ValidationError):
        Diagnosis(probable_causes=[], steps=[])
    d = Diagnosis(probable_causes=["a"], steps=["one", "two"])
    assert d.numbered() == ["1. one", "2. two"]


def test_usage_merge_sums():
    a = TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3, calls=1).model_dump()
    merged = merge_usage(a, a)
    assert merged["total_tokens"] == 6 and merged["calls"] == 2
    assert merge_usage(None, None)["calls"] == 0
