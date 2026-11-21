"""Audit log (N6)."""

from sqlalchemy import select

from app.models.entities import AuditLog
from app.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def recent(self, *, limit: int = 100, offset: int = 0) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars())
