"""Generate ``database/seed.sql`` from ``sample_data/`` (Postgres / Supabase SQL editor).

Uses the same records as the SQLite bootstrap, so the two cannot disagree.
``tests/unit/test_seed.py`` fails when the committed file is out of date.
Run: ``python scripts/generate_seed_sql.py`` (add ``--check`` to verify only).
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.seed_service import build_seed_records

OUTPUT = ROOT / "database" / "seed.sql"

HEADER = """-- CloudDesk demo data for the Supabase SQL editor. GENERATED: do not edit by hand.
-- Source: sample_data/*.json and sample_data/knowledge_base/*.md
-- Regenerate with: python scripts/generate_seed_sql.py
-- Safe to re-run: every insert is ON CONFLICT (id) DO NOTHING.
"""


def literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    if isinstance(value, dict | list):
        return "'" + json.dumps(value, sort_keys=True).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def render(root: Path | None = None) -> str:
    parts = [HEADER]
    for table, rows in build_seed_records(root).items():
        parts.append(f"\n-- {table} ({len(rows)})")
        for row in rows:
            columns = ", ".join(row)
            values = ", ".join(literal(v) for v in row.values())
            parts.append(
                f"insert into {table} ({columns}) values ({values}) on conflict (id) do nothing;"
            )
    return "\n".join(parts) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != content:
            print("database/seed.sql is out of date; run scripts/generate_seed_sql.py")
            return 1
        return 0
    OUTPUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
