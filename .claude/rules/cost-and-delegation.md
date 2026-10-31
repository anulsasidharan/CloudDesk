# Cost and delegation

- Finish one task before starting another; keep one session for one topic.
- Do not edit CLAUDE.md, rules, agents, skills, settings or MCP servers during a session (it breaks the prompt cache). Change them between sessions.
- Batch questions into one message.
- Use the named skills: `/plan`, `/implement`, `/test`, `/review`, `/consult-opus`, `/fix-issue`, `/pr-review`, `/wait`, `/cost-report`.
- Use `log-triage` for any long command output; use `Explore` for broad searches.
- Do not switch models with `/model` mid-session unless the task needs it.
- Commit only after review and green tests.
- Parallel agents only for independent work: one worktree each, an explicit file scope, max 3 at once. Same file, migration, lock file or config means sequential.
