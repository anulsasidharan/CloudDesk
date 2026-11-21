"""P5-4 and the phase exit: ingest count, and retrieval hit-rate@3 over the demo tickets."""

import json

import pytest
from app.services.seed_service import resolve_data_dir

from rag.ingest import ingest_articles
from rag.retriever import retrieve
from rag.vector_store import InMemoryVectorStore

# What each demo ticket's reply should cite. CD-1013 is a prompt injection with no article.
EXPECTED = {
    "CD-1001": "sso-login-troubleshooting",
    "CD-1002": "refund-policy",
    "CD-1003": "api-rate-limits",
    "CD-1004": "storage-quota-and-upgrades",
    "CD-1005": "security-incident-response",
    "CD-1006": "file-recovery-and-version-history",
    "CD-1007": "external-sharing-and-permissions",
    "CD-1008": "slack-integration-troubleshooting",
    "CD-1009": "account-deletion-and-data-erasure",
    "CD-1010": "feature-requests-and-roadmap",
    "CD-1011": "payment-disputes-and-chargebacks",
    "CD-1012": "mfa-recovery",
}
THRESHOLD = 0.75  # CLAUDE.md section 13: retrieval hit-rate@3


@pytest.fixture(scope="module")
def tickets() -> dict[str, str]:
    raw = json.loads((resolve_data_dir() / "tickets.json").read_text(encoding="utf-8"))
    return {t["number"]: f"{t['subject']} {t['body']}" for t in raw}


async def test_ingest_counts_and_reindex_recreates(articles):
    store = InMemoryVectorStore()
    first = await ingest_articles(articles, store, cache=None)
    assert first.articles == 15 and first.chunks >= 15
    assert await store.count() == first.chunks

    again = await ingest_articles(articles, store, cache=None)  # recreate: no duplicates
    assert again == first and await store.count() == first.chunks

    shrunk = await ingest_articles(articles[:3], store, cache=None)  # dropped articles disappear
    assert await store.count() == shrunk.chunks < first.chunks


async def test_checkpoint_mfa_ticket_gets_its_article_in_top_3(store, tickets):
    hits = await retrieve(tickets["CD-1012"], store=store, top_k=3, use_cache=False)
    assert "kb://mfa-recovery#" in {h.source.split("#")[0] + "#" for h in hits}


async def test_hit_rate_at_3_meets_the_threshold(store, tickets):
    misses = []
    for number, slug in EXPECTED.items():
        hits = await retrieve(tickets[number], store=store, top_k=3, use_cache=False)
        if not any(h.source.startswith(f"kb://{slug}#") for h in hits):
            misses.append(number)
    rate = 1 - len(misses) / len(EXPECTED)
    assert rate >= THRESHOLD, f"hit-rate@3 {rate:.2f}; missed {misses}"
