"""Phase 2: the sample data is complete, consistent and mirrored in ``database/seed.sql``."""

import re
import sys
from pathlib import Path

from app.schemas.common import Category
from app.services.seed_service import (
    build_seed_records,
    parse_front_matter,
    resolve_data_dir,
    stable_id,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_seed_sql


def test_demo_scenario_sizes():
    records = build_seed_records()
    assert len(records["tickets"]) == 13
    assert len(records["customers"]) == 8
    assert len(records["support_articles"]) == 15
    assert len(records["profiles"]) == 3
    assert len(records["subscriptions"]) == 8
    assert len(records["ticket_messages"]) == 13


def test_tickets_cd_1001_to_1013_in_order():
    numbers = [t["number"] for t in build_seed_records()["tickets"]]
    assert numbers == [f"CD-{n}" for n in range(1001, 1014)]


def test_all_four_plans_are_represented():
    plans = {c["plan"] for c in build_seed_records()["customers"]}
    assert plans == {"free", "pro", "business", "enterprise"}


def test_every_foreign_key_resolves():
    records = build_seed_records()
    ids = {table: {r["id"] for r in rows} for table, rows in records.items()}
    for table, column, target in [
        ("subscriptions", "customer_id", "customers"),
        ("workspaces", "customer_id", "customers"),
        ("tickets", "customer_id", "customers"),
        ("ticket_messages", "ticket_id", "tickets"),
    ]:
        assert all(r[column] in ids[target] for r in records[table]), (table, column)


def test_ids_are_deterministic():
    assert stable_id("ticket", "CD-1002") == stable_id("ticket", "CD-1002")
    assert stable_id("ticket", "CD-1002") != stable_id("ticket", "CD-1003")
    first = [t["id"] for t in build_seed_records()["tickets"]]
    assert first == [t["id"] for t in build_seed_records()["tickets"]]


def test_cd_1002_is_the_seat_mismatch_refund_case():
    records = build_seed_records()
    ticket = next(t for t in records["tickets"] if t["number"] == "CD-1002")
    subscription = next(s for s in records["subscriptions"] if s["customer_id"] == ticket["customer_id"])
    assert (subscription["seats_purchased"], subscription["seats_used"]) == (8, 5)


def test_cd_1001_customer_is_enterprise_with_an_active_sso_incident():
    records = build_seed_records()
    ticket = next(t for t in records["tickets"] if t["number"] == "CD-1001")
    customer = next(c for c in records["customers"] if c["id"] == ticket["customer_id"])
    assert customer["plan"] == "enterprise"
    assert any(i["service"] == "sso" and i["status"] == "active" for i in records["incidents"])


def test_cd_1013_keeps_the_injection_as_ticket_data():
    ticket = next(t for t in build_seed_records()["tickets"] if t["number"] == "CD-1013")
    assert "ignore all previous instructions" in ticket["body"].lower()
    assert ticket["status"] == "new"


def test_tickets_start_unclassified_and_new():
    for ticket in build_seed_records()["tickets"]:
        assert ticket["status"] == "new"
        assert "category" not in ticket and "severity" not in ticket


def test_articles_have_valid_categories_and_front_matter():
    valid = {c.value for c in Category}
    for article in build_seed_records()["support_articles"]:
        assert article["category"] in valid
        assert article["title"] and article["summary"] and article["tags"]
        assert not article["body"].startswith("---")


def test_every_category_has_at_least_one_article():
    covered = {a["category"] for a in build_seed_records()["support_articles"]}
    assert covered == {c.value for c in Category}


def test_front_matter_parser():
    meta, body = parse_front_matter("---\ntitle: T\ntags: [a, b]\n---\n\nBody")
    assert meta == {"title": "T", "tags": ["a", "b"]}
    assert body == "Body"
    assert parse_front_matter("no front matter") == ({}, "no front matter")


def test_data_dir_resolves_from_any_working_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert (resolve_data_dir("sample_data") / "tickets.json").is_file()


def test_no_secrets_or_card_numbers_in_sample_data():
    pattern = re.compile(r"\b(?:\d[ -]?){13,16}\b|sk-[A-Za-z0-9]{10,}|password\s*[:=]", re.IGNORECASE)
    for path in (ROOT / "sample_data").rglob("*"):
        if path.is_file():
            assert not pattern.search(path.read_text(encoding="utf-8")), path.name


def test_seed_sql_is_up_to_date():
    committed = (ROOT / "database" / "seed.sql").read_text(encoding="utf-8")
    assert committed == generate_seed_sql.render()


def test_seed_sql_is_idempotent_and_covers_every_table():
    sql = (ROOT / "database" / "seed.sql").read_text(encoding="utf-8")
    inserts = re.findall(r"^insert into (\w+) ", sql, flags=re.MULTILINE)
    assert inserts.count("tickets") == 13 and inserts.count("customers") == 8
    assert sql.count("on conflict (id) do nothing") == len(inserts)
