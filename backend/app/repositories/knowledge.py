"""Knowledge articles, incidents and the product catalogue."""

from sqlalchemy import func, or_, select

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


    async def search(self, term: str = "", category: str | None = None) -> list[SupportArticle]:
        """Case-insensitive match on title, slug or summary, optionally within one category."""
        stmt = select(SupportArticle).order_by(SupportArticle.title)
        if term.strip():
            like = f"%{term.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(SupportArticle.title).like(like),
                    func.lower(SupportArticle.slug).like(like),
                    func.lower(SupportArticle.summary).like(like),
                )
            )
        if category:
            stmt = stmt.where(SupportArticle.category == category)
        return list((await self.session.execute(stmt)).scalars())

    async def get_by_id_or_slug(self, key: str) -> SupportArticle | None:
        return await self.get(key) or await self.get_by_slug(key)


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
