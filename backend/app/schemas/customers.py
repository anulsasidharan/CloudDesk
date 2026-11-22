"""Customer response shapes. Mirrors ``docs/API_CONTRACT.md`` (Customers)."""

from pydantic import BaseModel, Field

from app.schemas.records import CustomerMemoryOut, CustomerOut, SubscriptionOut, WorkspaceOut
from app.schemas.tickets import TicketSummary


class CustomerPage(BaseModel):
    items: list[CustomerOut]
    total: int
    page: int
    page_size: int


class CustomerDetail(CustomerOut):
    subscription: SubscriptionOut | None = None
    workspaces: list[WorkspaceOut] = Field(default_factory=list)
    tickets: list[TicketSummary] = Field(default_factory=list)
    memory: list[CustomerMemoryOut] = Field(default_factory=list)
