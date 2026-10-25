"""JSON logs. Every line includes ``request_id`` and ``workflow_id``.

Call ``setup_logging()`` once at process startup. Bind the ids for the current
task with ``log_context`` (request middleware and workflow runs). Unset ids are
JSON ``null``. Extra log attributes are not copied onto the line.
"""

import contextvars
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TextIO


request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)
workflow_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "workflow_id",
    default=None,
)


class _Unset:
    """Marks a ``log_context`` argument the caller did not pass."""


_UNSET = _Unset()


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "request_id", None) is None:
            record.request_id = request_id_var.get()
        if getattr(record, "workflow_id", None) is None:
            record.workflow_id = workflow_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with a fixed set of keys."""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", None)
        if request_id is None:
            request_id = request_id_var.get()
        workflow_id = getattr(record, "workflow_id", None)
        if workflow_id is None:
            workflow_id = workflow_id_var.get()
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id,
            "workflow_id": workflow_id,
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def _coerce_level(level: int | str) -> int:
    if isinstance(level, int):
        return level
    try:
        return logging.getLevelNamesMapping()[level.strip().upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown log level: {level}") from exc


def setup_logging(level: int | str = logging.INFO, stream: TextIO | None = None) -> None:
    """Attach a single JSON handler to the root logger."""
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)
    root.setLevel(_coerce_level(level))


@contextmanager
def log_context(
    *,
    request_id: str | None | _Unset = _UNSET,
    workflow_id: str | None | _Unset = _UNSET,
) -> Iterator[None]:
    """Bind ids for the current context. Omitted arguments are left unchanged."""
    tokens: list[tuple[contextvars.ContextVar[str | None], contextvars.Token[str | None]]] = []
    if not isinstance(request_id, _Unset):
        tokens.append((request_id_var, request_id_var.set(request_id)))
    if not isinstance(workflow_id, _Unset):
        tokens.append((workflow_id_var, workflow_id_var.set(workflow_id)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
