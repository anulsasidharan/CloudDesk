"""Run one ticket through the whole workflow in the terminal (``make demo``).

    make demo                    CD-1002: refund -> pauses for a person -> approve -> refund runs
    make demo TICKET=CD-1005     security -> policy escalation, no approval wait
    python scripts/demo.py CD-1002 --reject      reject instead: the run escalates
    python scripts/demo.py CD-1002 --ask         type y/n at the pause

It runs on a THROWAWAY database and an in-memory checkpointer, so it never touches ``data/`` and
can be repeated. Defaults to the offline ``fake`` model: no API key needed.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

_TMP = Path(tempfile.mkdtemp(prefix="clouddesk-demo-"))
os.environ.update(
    {
        "DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite+aiosqlite:///{(_TMP / 'demo.db').as_posix()}",
        "CHECKPOINT_DB_PATH": ":memory:",
        "USE_FAKE_REDIS": "true",
        "REDIS_URL": "",
        "VECTOR_STORE": "memory",
    }
)
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")

from app.core import database
from app.core.security import AuthUser
from app.repositories import ProfileRepository, TicketRepository
from app.schemas.common import Role
from app.services import approval_service, workflow_service
from app.services.knowledge_service import ensure_indexed
from app.services.seed_service import bootstrap_demo_data

LINE = "-" * 68


def say(title: str) -> None:
    print(f"\n{LINE}\n{title}\n{LINE}")


def show_state(state: dict) -> None:
    classification = state.get("classification") or {}
    print(f"  status      : {state['status']}")
    print(f"  category    : {classification.get('category')}   severity: {state.get('severity')}")
    print(f"  risk        : {(state.get('risk') or {}).get('level')}")
    print(f"  steps done  : {' > '.join(state.get('completed_nodes', []))}")
    for action in state.get("actions", []):
        print(f"  action      : {action['tool']:<22} {action['status']}")
    if state.get("escalation_required"):
        print(f"  escalation  : {state.get('escalation_reason')}")


async def decide_at_the_pause(args: argparse.Namespace, approval: dict) -> bool:
    action = approval.get("action") or {}
    print(f"  A person must decide: {action.get('tool')} {action.get('arguments')}")
    print(f"  why        : {approval['reason']}")
    if args.ask:
        return (await asyncio.to_thread(input, "  approve? [y/N] ")).strip().lower().startswith("y")
    approved = not args.reject
    print(f"  (demo) {'approving' if approved else 'rejecting'} automatically")
    return approved


async def main(args: argparse.Namespace) -> int:
    await database.create_tables()
    await bootstrap_demo_data()
    await ensure_indexed()

    async with database.session_scope() as session:
        ticket = await TicketRepository(session).get_by_number(args.ticket)
        if ticket is None:
            print(f"{args.ticket} not found")
            return 1
        agent = await ProfileRepository(session).first_with_role(Role.AGENT.value)
        caller = AuthUser(id=agent.id, email=agent.email, role=agent.role)
        print(f"{ticket.number}: {ticket.subject}")

    say("1. Run the AI workflow")
    async with database.session_scope() as session:
        run = await workflow_service.create_run(session, args.ticket)
    await workflow_service.start_workflow(run.id)
    async with database.session_scope() as session:
        state = await workflow_service.get_workflow(session, args.ticket)
    show_state(state)

    if state["status"] == "waiting_for_approval":
        say("2. The run paused: money moves only with a person's approval")
        async with database.session_scope() as session:
            approval = (await approval_service.get_approval(session, state["approval_request_id"])).model_dump()
        approved = await decide_at_the_pause(args, approval)
        say(f"3. {'Approve' if approved else 'Reject'} and resume")
        async with database.session_scope() as session:
            result = await approval_service.decide(
                session,
                approval["id"],
                approved=approved,
                note="Checked the seat count" if approved else "Not convinced, escalate",
                caller=caller,
            )
        show_state(result.workflow)
    elif state["status"] == "escalated":
        say("2. Policy rule fired: escalated to a team, no approval wait")
    else:
        say("2. No approval needed and no policy rule matched: only safe actions ran, the reply is a draft")

    async with database.session_scope() as session:
        ticket = await TicketRepository(session).get_by_number(args.ticket)
        print(f"\nFinal ticket status: {ticket.status}")
    await database.dispose_engine()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("ticket", nargs="?", default="CD-1002")
    parser.add_argument("--reject", action="store_true", help="reject at the approval pause")
    parser.add_argument("--ask", action="store_true", help="ask y/n at the approval pause")
    sys.exit(asyncio.run(main(parser.parse_args())))
