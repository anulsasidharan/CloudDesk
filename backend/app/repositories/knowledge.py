"""Knowledge articles, incidents and the product catalogue."""

from sqlalchemy import select

from app.models.entities import Incident, Product, SupportArticle
from app.repositories.base import BaseRepository
from app.schemas.common import IncidentStatus


class SupportArticleRepository(BaseRepository[SupportArticle]):
    model = SupportArticle

    async def get_by_slug(self, slug: str) -> SupportArticle | None:
        stmt = select(SupportArticle).where(SupportArticle.slug == slug)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_by_category(self, category: str | None = None) -> list[SupportArticle]:
        stmt = select(SupportArticle).order_by(SupportArticle.title)
        if category:
            stmt = stmt.where(SupportArticle.category == category)
        return list((await self.session.execute(stmt)).scalars())


class IncidentRepository(BaseRepository[Incident]):
    model = Incident

    async def active(self, service: str | None = None) -> list[Incident]:
        stmt = (
            select(Incident)
            .where(Incident.status == IncidentStatus.ACTIVE.value)
            .order_by(Incident.started_at.desc())
        )
        if service:
            stmt = stmt.where(Incident.service == service)
        return list((await self.session.execute(stmt)).scalars())


class ProductRepository(BaseRepository[Product]):
    model = Product

    async def get_by_sku(self, sku: str) -> Product | None:
        stmt = select(Product).where(Product.sku == sku)
        return (await self.session.execute(stmt)).scalar_one_or_none()
