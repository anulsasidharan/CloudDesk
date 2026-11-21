"""Generic async repository. All SQL lives under ``app/repositories``; callers pass a session."""

from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: str) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def add(self, **values: Any) -> ModelT:
        entity = self.model(**values)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def add_many(self, records: Sequence[Mapping[str, Any]]) -> int:
        """Insert plain-dict records (used by the seed loader). Returns the row count."""
        self.session.add_all([self.model(**record) for record in records])
        await self.session.flush()
        return len(records)

    async def count(self) -> int:
        result = await self.session.execute(select(func.count()).select_from(self.model))
        return int(result.scalar_one())

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = select(self.model).order_by(self.model.created_at).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars())
