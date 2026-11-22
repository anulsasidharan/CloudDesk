# Phase 6: System Design Evolution

*CloudDesk: Autonomous Customer Support & Resolution Platform*

**Phase 6: Tools and policy.** Every side effect the agents can take becomes a registered tool with an explicit approval bit. This file shows the design growing step by step, from a bare policy function to the full tool layer.

---

## Step 0: Starting point (end of Phase 5)

The backend can store and read data (Phase 2), authenticate (Phase 3), serve tickets and customers (Phase 4) and search knowledge (Phase 5). **Nothing can act.** There is no controlled way for an agent to change a ticket, escalate, or request money.

```mermaid
flowchart LR
    UI["Browser / curl"] --> API["FastAPI API"]
    API --> SVC["Services"]
    SVC --> REPO["Repositories"] --> DB[("SQLite / Postgres")]
    SVC --> RAG["rag/ retriever"]
    RAG --> VS["Vector store + Redis cache"]
```

---

## Step 1 (P6-1): Tool policy and registry

**Added:** `app/tools/policy.py`, `registry.py`, `base.py`.

- `ToolPolicy.requires_approval(name, args)` is a pure function. Two sets decide it: tools that never need approval, tools that always do. Anything else, **unknown**, needs approval.
- `create_refund_request` is special: it also reads settings (`APPROVAL_REQUIRED_FOR_REFUNDS`, `MAX_REFUND_WITHOUT_APPROVAL`). By default every refund is gated.
- `ToolRegistry.execute(name, args, approved=False)` is the single doorway. It returns a `ToolResult`, never raises.

```mermaid
flowchart TD
    CALLER["Caller (later: a workflow node)"] -->|"execute(name, args, approved)"| REG["ToolRegistry"]
    REG --> POL{"ToolPolicy:<br/>needs approval?"}
    POL -->|"yes and approved=False"| BLOCK["ToolResult<br/>approval_required<br/>nothing runs"]
    POL -->|"no, or approved=True"| FIND{"Tool registered?"}
    FIND -->|"no"| UNK["ToolResult unknown_tool"]
    FIND -->|"yes"| RUN["run with<br/>TOOL_TIMEOUT_SECONDS"]
    RUN -->|"ok"| OK["ToolResult ok + data"]
    RUN -->|"exception"| ERR["ToolResult error"]
    RUN -->|"too slow"| TMO["ToolResult timeout"]
```

---

## Step 2 (P6-4): Mock integrations

**Added:** `integrations/protocols.py`, `integrations/mock/services.py`, `integrations/factory.py`.

Built before the write tools because the write tools need something to call. Four `Protocol` interfaces (billing, email, notifications, workspace admin). Four mock adapters that **record** their calls in a list and return deterministic ids (`re_mock_0001`). A factory returns the mock for each; it is the one file to change when a real provider arrives.

```mermaid
flowchart LR
    T["Tools (later)"] --> F["integrations/factory.py"]
    F --> P["Protocols<br/>BillingService, EmailService,<br/>NotificationService, WorkspaceAdminService"]
    P -. "implemented by" .-> M["Mock adapters<br/>in-memory call log"]
    P -. "future" .-> R["Real providers<br/>(not built)"]
```

---

## Step 3 (P6-2): Read-only tools

**Added:** `app/tools/read_only.py`. Five `@tool` functions: `get_customer`, `get_subscription`, `get_ticket_history`, `search_docs`, `check_service_status`.

They reuse existing code: repositories for SQL, `rag.retriever.retrieve` for search. No new SQL, no new retrieval logic. Each opens its session through one seam, `tool_session()`, so tests can point at a private database.

```mermaid
flowchart LR
    REG["ToolRegistry"] --> GC["get_customer"] & GS["get_subscription"] & GH["get_ticket_history"] & CS["check_service_status"]
    REG --> SD["search_docs"]
    GC & GS & GH & CS --> REPO["Repositories"] --> DB[("DB")]
    SD --> RET["rag.retriever"] --> VS["Vector store"]
```

---

## Step 4 (P6-3): Approval-gated write tools

**Added:** `app/tools/write.py`. Four tools:

| Tool | Writes to | Gate |
|---|---|---|
| `update_ticket` | `tickets` (values validated against the enums) | none |
| `create_escalation` | `escalations`, plus a team notification | none (the safe path) |
| `create_refund_request` | billing integration | **approval** |
| `reset_demo_setting` | workspace row plus workspace-admin integration; only three whitelisted settings | **approval** |

```mermaid
flowchart TD
    REG["ToolRegistry<br/>(policy checked here)"] --> UT["update_ticket"] --> TK[("tickets")]
    REG --> CE["create_escalation"] --> ES[("escalations")]
    CE --> NOTE["Notification mock"]
    REG -->|"approved only"| RF["create_refund_request"] --> BILL["Billing mock"]
    REG -->|"approved only"| RS["reset_demo_setting"] --> WS[("workspaces")]
    RS --> ADM["Workspace-admin mock"]
```

---

## End of phase: full picture

```mermaid
flowchart TB
    subgraph Existing["Phases 1-5 (unchanged)"]
        API["FastAPI + middleware"]
        SVC["Services"]
        REPO["Repositories"]
        DB[("DB")]
        RAG["rag/"]
    end
    subgraph Phase6["Phase 6 (new)"]
        REG["ToolRegistry<br/>single doorway"]
        POL["ToolPolicy"]
        RO["5 read-only tools"]
        WR["4 write tools"]
        INT["integrations/<br/>protocols + mocks + factory"]
    end
    FUTURE["Phases 9-10: workflow nodes<br/>and the approval gate<br/>(not built)"] -.->|"execute(..., approved)"| REG
    REG --> POL
    REG --> RO & WR
    RO --> REPO
    RO --> RAG
    WR --> REPO --> DB
    WR --> INT
```

Nothing in the HTTP API changed. The tool layer sits **beside** the API, waiting for the workflow.

---

## Design decisions to remember

1. **One doorway.** `ToolRegistry.execute` is the only way to run a tool, so policy cannot be bypassed.
2. **Policy is code, not a prompt.** The model never decides what is allowed.
3. **Failures are data.** `ToolResult(ok=False)` for errors, timeouts, unknown tools and blocked calls, so the graph never crashes on a tool.
4. **Deny by default.** Unknown tool names need approval.
5. **Protocols over concrete services.** Mocks today, real providers later, no tool edits.
6. **Layering respected.** Tools call repositories (SQL) and `rag/`; they never contain SQL or call a model. `core` does not import integrations.

---

## Status (honest)

| Item | State |
|---|---|
| Policy, registry, 9 tools, 4 mock integrations | Implemented |
| 28 new unit tests; full suite 192 passed, offline | Validated locally |
| Tools called by any agent or workflow node | **Not yet** (Phases 8-10) |
| `resolution_actions` rows written after an approved action | **Not yet** (Phase 10) |
| `/mcp/tools` endpoint exposing tool specs | **Not yet** (`registry.specs()` is ready for it) |
| Real billing, email, chat providers | Not planned for v1 |
