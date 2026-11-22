"""LLM access (F14). Every model call in the project goes through ``call_structured``.

``LLM_PROVIDER=fake`` (the default) runs offline: the caller supplies an ``offline`` function that
builds the answer deterministically, and the call still returns validated output, token counts and
timing, so the workflow behaves the same with or without an API key. Real providers go through
LangChain's ``init_chat_model`` with structured output.

``core`` must not import ``agents/``, so this module knows nothing about specialists.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.schemas.workflow import TokenUsage

logger = logging.getLogger("clouddesk.llm")

T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 2
FAKE_PROVIDER = "fake"


class LLMError(RuntimeError):
    """The model could not produce valid structured output."""


@dataclass(frozen=True)
class StructuredResult(Generic[T]):
    output: T
    usage: TokenUsage
    duration_ms: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate (about four characters each). Telemetry only."""
    return max(1, len(text) // 4)


def is_fake_provider() -> bool:
    return get_settings().llm_provider == FAKE_PROVIDER


def get_llm():
    """A LangChain chat model for the configured real provider. Never called for ``fake``."""
    settings = get_settings()
    if settings.llm_provider == FAKE_PROVIDER:
        raise LLMError("the fake provider has no chat model; use call_structured with offline=")
    if not settings.llm_model:
        raise LLMError("LLM_MODEL must be set for a real provider")
    from langchain.chat_models import init_chat_model

    kwargs = {}
    key = settings.llm_api_key.get_secret_value()
    if key:
        kwargs["api_key"] = key
    return init_chat_model(settings.llm_model, model_provider=settings.llm_provider, **kwargs)


async def call_structured(
    schema: type[T],
    *,
    system: str,
    user: str,
    offline: Callable[[], T],
    agent: str = "agent",
) -> StructuredResult[T]:
    """Ask the model for ``schema``. Retries once on invalid output, then raises ``LLMError``.

    ``offline`` is the deterministic answer used by the fake provider. Raw prompts are never
    logged or returned; only sizes are.
    """
    started = time.perf_counter()
    input_tokens = estimate_tokens(system) + estimate_tokens(user)

    if is_fake_provider():
        output = schema.model_validate(offline().model_dump())
        output_tokens = estimate_tokens(output.model_dump_json())
        return StructuredResult(
            output=output,
            usage=_usage(input_tokens, output_tokens),
            duration_ms=_ms(started),
        )

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            runnable = get_llm().with_structured_output(schema)
            raw = await runnable.ainvoke(
                [("system", system), ("human", user)],
            )
            output = raw if isinstance(raw, schema) else schema.model_validate(raw)
            return StructuredResult(
                output=output,
                usage=_usage(input_tokens, estimate_tokens(output.model_dump_json())),
                duration_ms=_ms(started),
            )
        except (ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning("structured output invalid (%s, attempt %d)", agent, attempt)
        except Exception as exc:
            raise LLMError(f"{agent}: {type(exc).__name__}") from exc
    raise LLMError(f"{agent}: no valid structured output after {MAX_ATTEMPTS} attempts") from last_error


def _usage(input_tokens: int, output_tokens: int) -> TokenUsage:
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
        cost_usd=0.0,  # estimates only; pricing is not tracked in v1
        calls=1,
    )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
