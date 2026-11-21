"""What CloudDesk needs from the outside world, as ``Protocol`` interfaces.

Tools depend on these protocols only. Swapping a mock for a real billing, email or chat
provider means writing a new adapter and changing ``integrations/factory.py``; no tool changes.
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BillingService(Protocol):
    async def create_refund(
        self, *, customer_id: str, amount: float, currency: str, reason: str
    ) -> dict[str, Any]:
        """Start a refund. Returns ``{"refund_id", "status", ...}``."""


@runtime_checkable
class EmailService(Protocol):
    async def send_email(self, *, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send one email. Returns ``{"message_id", "status"}``."""


@runtime_checkable
class NotificationService(Protocol):
    async def notify_team(self, *, team: str, message: str) -> dict[str, Any]:
        """Page or message a named internal team. Returns ``{"notification_id", "status"}``."""


@runtime_checkable
class WorkspaceAdminService(Protocol):
    async def reset_setting(
        self, *, workspace_id: str, setting: str, value: bool
    ) -> dict[str, Any]:
        """Change one workspace setting. Returns ``{"change_id", "status", ...}``."""
