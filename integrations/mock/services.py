"""Mock integrations (CLAUDE.md non-goal: no real emails, no real refunds).

Each mock keeps what it "sent" in a list so tests and demos can prove what did, and did not,
happen. Ids are sequential so output is deterministic.
"""

from itertools import count
from typing import Any


class _Recorder:
    prefix = "mock"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._ids = count(1)

    def _next_id(self, kind: str) -> str:
        return f"{kind}_mock_{next(self._ids):04d}"

    def _record(self, **values: Any) -> dict[str, Any]:
        self.calls.append(values)
        return values


class MockBillingService(_Recorder):
    async def create_refund(
        self, *, customer_id: str, amount: float, currency: str, reason: str
    ) -> dict[str, Any]:
        return self._record(
            refund_id=self._next_id("re"),
            status="pending_settlement",
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            reason=reason,
        )


class MockEmailService(_Recorder):
    async def send_email(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        return self._record(
            message_id=self._next_id("msg"), status="not_sent_mock", to=to, subject=subject
        )


class MockNotificationService(_Recorder):
    async def notify_team(self, *, team: str, message: str) -> dict[str, Any]:
        return self._record(
            notification_id=self._next_id("ntf"), status="queued_mock", team=team, message=message
        )


class MockWorkspaceAdminService(_Recorder):
    async def reset_setting(
        self, *, workspace_id: str, setting: str, value: bool
    ) -> dict[str, Any]:
        return self._record(
            change_id=self._next_id("chg"),
            status="applied_mock",
            workspace_id=workspace_id,
            setting=setting,
            value=value,
        )
