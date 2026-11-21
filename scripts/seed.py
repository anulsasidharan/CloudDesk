"""Load the sample data into the configured database (``make seed``).

Creates missing tables, then loads ``sample_data/`` only when the database is empty,
so running it twice is harmless. Prints CD-1002 and the customer count as a checkpoint.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.database import create_tables, dispose_engine, session_scope
from app.repositories import CustomerRepository, TicketRepository
from app.services.seed_service import bootstrap_demo_data


async def main() -> int:
    await create_tables()
    result = await bootstrap_demo_data()
    print("loaded sample data" if result.loaded else "database not empty; nothing loaded")
    for table, count in result.counts.items():
        print(f"  {table}: {count}")
    async with session_scope() as session:
        ticket = await TicketRepository(session).get_by_number("CD-1002")
        customers = await CustomerRepository(session).count()
        if ticket is None:
            print("CD-1002 is missing")
            return 1
        owner = await CustomerRepository(session).get(ticket.customer_id)
        print(f"CD-1002 {ticket.subject!r} for {owner.company if owner else '?'}; {customers} customers")
    await dispose_engine()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
