"""ToolRegistry: the ONLY way a tool runs (CLAUDE.md 7.4).

Auto-resolved and human-approved actions share this path. The registry checks ``ToolPolicy``,
enforces the timeout and turns every exception into ``ToolResult(ok=False)``.
"""

import asyncio
import logging
from typing import Any

from langchain_core.tools import BaseTool

from app.core.config import get_settings
from app.tools.base import ToolResult
from app.tools.policy import ToolPolicy

logger = logging.getLogger("clouddesk.tools")


class ToolRegistry:
    def __init__(self, tools: list[BaseTool] | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        """Name, description and approval bit for each tool (UI, MCP, LLM binding)."""
        return [
            {
                "name": name,
                "description": (tool.description or "").strip(),
                "requires_approval": ToolPolicy.requires_approval(name),
            }
            for name, tool in sorted(self._tools.items())
        ]

    async def execute(
        self, name: str, args: dict[str, Any] | None = None, *, approved: bool = False
    ) -> ToolResult:
        args = dict(args or {})
        needs_approval = ToolPolicy.requires_approval(name, args)

        if needs_approval and not approved:
            logger.info("tool blocked pending approval: %s", name)
            return ToolResult(
                tool=name,
                ok=False,
                status="approval_required",
                requires_approval=True,
                error="approval required before this tool can run",
            )

        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool=name,
                ok=False,
                status="unknown_tool",
                requires_approval=needs_approval,
                error=f"unknown tool: {name}",
            )

        timeout = get_settings().tool_timeout_seconds
        try:
            data = await asyncio.wait_for(tool.ainvoke(args), timeout=timeout)
        except TimeoutError:
            return ToolResult(
                tool=name,
                ok=False,
                status="timeout",
                requires_approval=needs_approval,
                error=f"tool timed out after {timeout:g}s",
            )
        except Exception as exc:  # noqa: BLE001 - a tool failure must never crash the graph
            logger.warning("tool failed: %s (%s)", name, type(exc).__name__)
            return ToolResult(
                tool=name,
                ok=False,
                status="error",
                requires_approval=needs_approval,
                error=f"{type(exc).__name__}: {exc}",
            )
        return ToolResult(
            tool=name,
            ok=True,
            status="ok",
            requires_approval=needs_approval,
            executed=True,
            data=data if isinstance(data, dict) else {"result": data},
        )


def build_default_registry() -> ToolRegistry:
    from app.tools.read_only import READ_ONLY_TOOLS
    from app.tools.write import WRITE_TOOLS

    return ToolRegistry([*READ_ONLY_TOOLS, *WRITE_TOOLS])


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = build_default_registry()
    return _registry
