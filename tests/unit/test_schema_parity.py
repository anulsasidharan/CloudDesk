"""Phase 2: models and ``database/schema.sql`` agree on tables, columns, types and nullability."""

import re
from pathlib import Path

from app.models import entities
from app.models.base import Base
from app.schemas.common import Category
from sqlalchemy.dialects import postgresql

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = (ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
EXPECTED_TABLES = {
    "profiles", "customers", "subscriptions", "workspaces", "products", "tickets",
    "ticket_messages", "support_articles", "incidents", "workflow_runs", "workflow_events",
    "resolution_actions", "approval_requests", "escalations", "customer_memory", "audit_logs",
}  # fmt: skip


def _sql_tables() -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}
    for name, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", SCHEMA, flags=re.DOTALL):
        columns = {}
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.startswith("CONSTRAINT"):
                continue
            column, _, rest = line.partition(" ")
            columns[column] = rest
        tables[name] = columns
    return tables


def test_model_and_schema_have_the_same_sixteen_tables():
    assert entities.TABLE_NAMES  # registers the models
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert set(_sql_tables()) == EXPECTED_TABLES


def test_columns_types_and_nullability_match():
    sql = _sql_tables()
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        assert set(sql[table.name]) == {c.name for c in table.columns}, table.name
        for column in table.columns:
            declared = sql[table.name][column.name]
            expected_type = column.type.compile(dialect=dialect).replace("JSON", "JSONB")
            assert declared.startswith(expected_type), (table.name, column.name, declared)
            assert ("NOT NULL" in declared) == (not column.nullable), (table.name, column.name)


def test_foreign_keys_match():
    declared = set(
        re.findall(r"CONSTRAINT fk_(\w+?)_(\w+?)_(\w+) FOREIGN KEY", SCHEMA)
    )
    expected = {
        (t.name, fk.parent.name, fk.column.table.name)
        for t in Base.metadata.tables.values()
        for fk in t.foreign_keys
    }
    assert expected
    assert {name for name in expected if "_".join(name) in {"_".join(d) for d in declared}} == expected


def test_every_table_has_an_updated_at_trigger_and_rls():
    rls = (ROOT / "database" / "rls_policies.sql").read_text(encoding="utf-8")
    for table in EXPECTED_TABLES:
        assert f"create trigger trg_{table}_updated_at" in SCHEMA
        assert f"alter table {table} enable row level security;" in rls
        assert f'create policy "{table}_service_role_all"' in rls


def test_rls_grants_nothing_to_anon():
    rls = (ROOT / "database" / "rls_policies.sql").read_text(encoding="utf-8")
    statements = "\n".join(line for line in rls.splitlines() if not line.startswith("--"))
    assert "anon" not in statements.lower()


def test_migrations_cover_the_schema():
    migrations = ROOT / "database" / "migrations"
    initial = (migrations / "0001_initial_schema.sql").read_text(encoding="utf-8")
    assert set(re.findall(r"CREATE TABLE (\w+) \(", initial)) == EXPECTED_TABLES
    rls = (migrations / "0002_row_level_security.sql").read_text(encoding="utf-8")
    assert rls == (ROOT / "database" / "rls_policies.sql").read_text(encoding="utf-8")


def test_category_check_matches_the_ten_categories():
    assert len(Category) == 10
    for category in Category:
        assert f"'{category.value}'" in SCHEMA
