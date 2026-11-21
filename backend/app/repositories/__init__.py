"""Repositories: the only place SQL is written. They never call LLMs."""

from app.repositories.audit import AuditRepository
from app.repositories.base import BaseRepository
from app.repositories.knowledge import (
    IncidentRepository,
    ProductRepository,
    SupportArticleRepository,
)
from app.repositories.people import (
    CustomerMemoryRepository,
    CustomerRepository,
    ProfileRepository,
    SubscriptionRepository,
    WorkspaceRepository,
)
from app.repositories.tickets import TicketMessageRepository, TicketRepository
from app.repositories.workflows import (
    ApprovalRepository,
    EscalationRepository,
    ResolutionActionRepository,
    WorkflowEventRepository,
    WorkflowRunRepository,
)

__all__ = [
    "ApprovalRepository",
    "AuditRepository",
    "BaseRepository",
    "CustomerMemoryRepository",
    "CustomerRepository",
    "EscalationRepository",
    "IncidentRepository",
    "ProductRepository",
    "ProfileRepository",
    "ResolutionActionRepository",
    "SubscriptionRepository",
    "SupportArticleRepository",
    "TicketMessageRepository",
    "TicketRepository",
    "WorkflowEventRepository",
    "WorkflowRunRepository",
    "WorkspaceRepository",
]
