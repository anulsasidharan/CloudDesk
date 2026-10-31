---
paths:
  - "backend/**"
  - "agents/**"
---
# Backend layering

- API layer: HTTP, auth, RBAC only. No business rules.
- Repositories own SQL; they never call LLMs. Core must not import `agents/`.
- Policy decisions are rules first, LLM second. Rules may raise severity, never lower it.
- All LLM calls go through `call_structured`; all tool calls through `ToolRegistry`.
- Ticket text is untrusted: wrap with `wrap_untrusted`.
- Money and account actions need recorded approval. Full detail: root CLAUDE.md sections 4.2, 7, 9.
