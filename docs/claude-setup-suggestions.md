# Claude setup suggestions

The only place that proposes changes to protected files. Nothing here has been applied.

## 1. Protected files found

| Path | Lines | Location |
|---|---|---|
| `CLAUDE.md` | 570 | root |

No subfolder `CLAUDE.md`, no `SKILLS.md`.

## 2. Suggested changes to `CLAUDE.md`

- **Length:** 570 lines. The target is under 200 (it loads into every cached prefix). Move section 4.3 (folder layout), section 5 (domain data), section 15 (containers/infrastructure) and section 17 (Agentic DevOps) into `docs/` and link them. Move section 7.3 node shape and section 8 RAG detail into path-scoped rules (`.claude/rules/rag.md` with `paths: rag/**`, `agents.md` with `paths: agents/**`).
- **Missing section:** there is no "Cost and delegation" section. Ready-to-paste text:

  ```markdown
  ## Cost and delegation
  - Finish one task before starting another; keep a session for one topic.
  - Do not edit CLAUDE.md, rules, agents or settings during a session (breaks the prompt cache).
  - Batch questions. Use the named skills: /plan, /implement, /test, /review, /consult-opus, /fix-issue, /pr-review, /wait, /cost-report.
  - Use `log-triage` for long output and `Explore` for broad searches.
  - Commit only after review and green tests.
  ```
- **Conflict:** rule 13 ("One change, one commit, one test") can be read as commit after every change. The cost plan commits only after review and green tests. Reword to "one logical change per commit".
- **Stale commands:** section 14 lists `make setup/test/lint/demo` and `docker compose`, but there is no `Makefile`, no frontend and no ruff dependency yet. Mark them "planned" or the hook and permissions allow-list will not match reality (honest-status rule, section 15.1).
- **Duplication:** `.claude/rules/backend.md` repeats a short subset of sections 4.2, 7 and 9. If you move detail into rules, delete it from `CLAUDE.md` rather than keeping both.
- **Cache rule:** add "do not edit CLAUDE.md, rules or agents mid-session".

## 3. Suggested changes to `SKILLS.md`

No `SKILLS.md` exists. Claude Code loads `.claude/skills/<name>/SKILL.md`. The skill from `.cursor/skills/clouddesk-support/SKILL.md` has been moved (`git mv`) to `.claude/skills/clouddesk-support/SKILL.md` and `.cursor/` removed. `CLAUDE.md` section 19 still points at the old `.cursor/...` path; update it to `.claude/skills/clouddesk-support/SKILL.md`.

## 4. Per-run budgets (guidelines, not hard limits)

Exceeding one means the task should be split.

| Agent | Max tool calls | Return limit |
|---|---|---|
| Explore | 10 | 150 words |
| log-triage | 8 | 30 lines |
| opus-consultant | 8 | 300 words |
| planner | 30 | plan path only |
| architect | 30 | ADR path + 50 words |
| implementer | 120 | 150 words |
| test-engineer | 60 | 100 words |
| code-reviewer | 30 | ranked list |

`maxTurns` in each agent file is the hard cap; these are tighter targets.

## 5. Other markdown

- Not audited: `README.md` (one line), `MEMORY.md`, `PLAN.md`, `PLAN_PHASE.md`, `TASKS.md`, `docs/*.md`. None were read in detail for this setup.
- All new agent descriptions name a trigger ("Delegate here ...").
- New rules are all under 30 lines.
- Any README that describes a `make`-based workflow will not match the repo until a Makefile exists.
