"""One place that decides which adapter is used. v1 returns mocks for every service."""

from functools import lru_cache

from integrations.mock.services import (
    MockBillingService,
    MockEmailService,
    MockNotificationService,
    MockWorkspaceAdminService,
)
from integrations.protocols import (
    BillingService,
    EmailService,
    NotificationService,
    WorkspaceAdminService,
)


@lru_cache(maxsize=1)
def get_billing() -> BillingService:
    return MockBillingService()


@lru_cache(maxsize=1)
def get_email() -> EmailService:
    return MockEmailService()


@lru_cache(maxsize=1)
def get_notifications() -> NotificationService:
    return MockNotificationService()


@lru_cache(maxsize=1)
def get_workspace_admin() -> WorkspaceAdminService:
    return MockWorkspaceAdminService()


def reset_integrations() -> None:
    """Forget the cached adapters (tests use this to start from empty call logs)."""
    for getter in (get_billing, get_email, get_notifications, get_workspace_admin):
        getter.cache_clear()
