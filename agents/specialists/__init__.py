"""The six specialist agents. Each returns a Pydantic model wrapped in ``AgentResult``."""

from agents.specialists.base import AgentResult, run_tool
from agents.specialists.customer import CustomerAgent
from agents.specialists.escalation import EscalationAgent
from agents.specialists.knowledge import KnowledgeAgent
from agents.specialists.resolution import ResolutionAgent, plan_actions
from agents.specialists.supervisor import SupervisorAgent
from agents.specialists.troubleshooting import TroubleshootingAgent

__all__ = [
    "AgentResult",
    "CustomerAgent",
    "EscalationAgent",
    "KnowledgeAgent",
    "ResolutionAgent",
    "SupervisorAgent",
    "TroubleshootingAgent",
    "plan_actions",
    "run_tool",
]
