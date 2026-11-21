# Task: Set up Claude Code cost governance, prompt caching, model routing and parallel execution

You are configuring this repository's `.claude/` folder and related markdown so that prompt caching is active and verified, routine work runs on cheaper models, heavy reasoning runs on Opus, subagent cost is controlled, and independent work runs in parallel. Work in phases and report at the end. Do not change application code.

This prompt is project-agnostic. Detect everything you can; never assume a stack, platform, OS or tool. Where a value cannot be detected, use a placeholder (`<TODO: ...>`, `<PIN: ...>`, `<DECIDE: ...>`) and list it in the report.

## Project parameters (optional; fill in or leave as-is)

Values here override detection. Anything left as `auto` is detected in Phase 0.

| Parameter | Value | Notes |
|---|---|---|
| Platform | `auto` | `anthropic-api`, `vertex`, `bedrock`, `foundry`, or `auto` |
| Model IDs (Opus / Sonnet / Haiku) | `auto` | Full IDs in the platform's own format |
| Default session model | `sonnet` | `sonnet` or `opusplan` (see Phase 1c) |
| Max parallel agents | `3` | Raise only with approval |
| Protected file patterns | `CLAUDE.md`, `SKILLS.md` | Case-insensitive; add more if needed |
| Extra secret file patterns to deny | none | e.g. `*.pem`, `*.tfvars`, `secrets/**` |
| Usage report script path | `scripts/claude_usage/` | |
| Plans folder | `docs/plans/` | |
| Suggestions file | `docs/claude-setup-suggestions.md` | |
| Optional agents/skills to skip | none | e.g. `pr-review` if no PR workflow |

## Protected files (read first, never edit)

Any file matching a protected pattern (any letter case) anywhere in the project is protected:
- Do not edit, rename, overwrite, append to, or back up-and-replace these files.
- You may read them to inform suggestions.
- Do not create a `CLAUDE.md` in a folder that already has one. Do not create a `SKILLS.md`.
- If no root `CLAUDE.md` exists, create one using the spec in Phase 3. If it exists, leave it alone.

Find them with (extend the pattern list if the parameters add more):
```bash
find . \( -iname 'CLAUDE.md' -o -iname 'SKILLS.md' \) \
  -not -path '*/node_modules/*' -not -path '*/.git/*' \
  -not -path '*/vendor/*' -not -path '*/.venv/*' -not -path '*/target/*' -not -path '*/dist/*' -not -path '*/build/*'
```

## Phase 0: Inspect before changing anything

1. **Environment**
   - OS and shell: Windows (Git Bash, WSL or PowerShell), macOS or Linux. Hooks must run with `bash` and use POSIX-portable commands. On Windows, confirm `bash` is on PATH; if it is not, say so and propose the Git Bash path before writing hooks.
   - Git: `git rev-parse --is-inside-work-tree`. If not a git repo, say so and ask before running `git init`.
   - Claude Code version: `claude --version`. Record it. Every setting key, hook format and subagent field used below must be checked against the docs for this version. If a key is not documented for this version, leave it out or mark it unverified; do not invent keys.
   - Platform: detect from environment (`CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_FOUNDRY`, or none = first-party API) unless set in the parameters. Record it, because model ID format, cache TTL options and pricing differ by platform.

2. **Stack and commands.** Look for every manifest and task runner that exists, not only one:
   - JS/TS: `package.json` (and its package manager: npm, pnpm, yarn, bun), `tsconfig.json`
   - Python: `pyproject.toml`, `setup.cfg`, `requirements*.txt`, `tox.ini`, `noxfile.py`
   - JVM: `pom.xml`, `build.gradle(.kts)`, `settings.gradle`
   - .NET: `*.sln`, `*.csproj`
   - Go: `go.mod`; Rust: `Cargo.toml`; Ruby: `Gemfile`; PHP: `composer.json`; others as found
   - Task runners: `Makefile`, `justfile`, `Taskfile.yml`, `scripts/`
   - CI: `.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, `azure-pipelines.yml`, `.circleci/`, `bitbucket-pipelines.yml`
   - `README.md`, `CONTRIBUTING.md`
   Record build, test, lint, format and type-check commands. Prefer what CI actually runs. Use `<TODO: command>` for anything unknown.

3. **Repo shape.** Single package or monorepo (workspaces, multiple manifests, `packages/`, `apps/`, `services/`). For a monorepo, record commands per package and the top-level areas, because rules and parallel scopes follow them.

4. **Integrations.** Whether `gh` or `glab` is installed and authenticated, and whether an issue tracker is referenced. These decide whether the optional `pr-review` and `fix-issue` skills are created.

5. Run the protected-file search. List each hit with its path and line count. Read them without changing them.

6. Inventory `.claude/`, `.gitignore`, and the usage report folder. Mark each as missing, matches spec, or differs. Note any existing agents, skills, rules, hooks or MCP config.

7. Before changing an existing file that differs from spec, copy only that file to `.claude.bak-<YYYYMMDD-HHMM>/` with its original path. Never back up or touch protected files.

8. Report the inventory and plan (create, merge, keep, skip) in a short table. Ask only if a step is hard to reverse.

## Phase 1: Prompt caching

Claude Code caches prompts by default. This phase makes the setup cache-friendly and verifies the cache works. It does not assume any TTL setting is honoured.

**1a. Keep the cached prefix stable.** The cache covers the start of each request: system prompt, tools, CLAUDE.md, rules, and agent definitions. Any change to that prefix invalidates the cache. Therefore:
- Do not add, remove or edit CLAUDE.md, rules, agents, skills or settings during a session. Make those changes between sessions.
- Do not add or remove MCP servers mid-session. Set them up before a session starts.
- Keep rules and agent descriptions short and stable, so the prefix is small and rarely changes.

**1b. Decide the TTL with a probe, not by default.** A longer cache write costs more than the default 5-minute write. Use it only if the measured saving on idle re-writes exceeds the extra write cost.
- Record the current price on the detected platform for the 5-minute write, the 1-hour write (if offered) and the cache read, for each model in use. Use the platform's official pricing page; do not quote prices from memory.
- Confirm whether the installed Claude Code version and platform support a longer TTL and through which setting. If neither is documented, leave TTL at the default and record why.
- If supported and the longer write is cheaper than the saved idle re-writes for the team's typical idle gaps, set the documented key in `settings.json` `env`.
- Otherwise leave the key out, so the default applies, and record the decision.
- Until the probe is done, write the key as `<DECIDE: probe result>` and do not treat it as set.

**1c. Avoid cache-breaking defaults.**
- Use `opusplan` only if its model-switch cost is accepted. Record in the report that switching models mid-session can rewrite the cache. If the team wants fewer switches, use Sonnet as the default and reach Opus only through the Opus-tier agents.
- Do not enable auto memory or persistent agent memory until they have been measured.

**1d. Verify caching works.** Do this in a fresh session, after the setup is written:
1. Send one short message. Note the input and cache-write tokens reported by `/cost` (or the platform's usage view).
2. Send a second message within a minute. The second call should report cache-read tokens. If it reports none, caching is not working. Stop and report the failure with the Claude Code version and platform.
3. Record both results in the report.
If you cannot open a fresh session yourself, write these steps into the report as a pending check and mark caching unverified.

**1e. Make cache health visible.** The `cost-report` skill must show the cache-read share of input tokens for the last 7 days. A drop after rollout means something is breaking the cache.

## Phase 2: Model routing and subagent cost controls

Every agent gets an explicit `model`. Tier map:

| Tier | Model | Use for |
|---|---|---|
| Opus | `opus` | Architecture, ADRs, plans, one narrow escalation question |
| Sonnet | `sonnet` | Code changes from a plan, tests, diff review |
| Haiku | `haiku` | Codebase search, log digests, summaries, wait and cost helpers |

Routing rules:
- Opus appears only on `architect`, `planner` and `opus-consultant`.
- `opus-consultant` has no `Agent` tool and no edit tools. It answers in 300 words or fewer.
- Pin full model IDs for Opus, Sonnet and Haiku in `settings.json` `env`, in the format the detected platform requires (first-party, Vertex, Bedrock and Foundry IDs differ). Use `<PIN: ...>` placeholders if unknown. Do not rely on bare aliases.
- Set the subagent default model to `sonnet` via the documented key for this version.
- Do not switch models with `/model` mid-session unless the task needs it.

Subagent cost controls:
- **Return limits.** Every agent's instructions must end with a maximum return size:

  | Agent | Return limit |
  |---|---|
  | Explore | 150 words: file paths and line numbers, one line each |
  | log-triage | 30 lines: result, failing items with file:line, first error |
  | opus-consultant | 300 words |
  | implementer | 150 words: changed files and open issues |
  | test-engineer | 100 words: pass or fail plus the digest |
  | code-reviewer | Ranked findings list, no preamble |
  | planner | Plan file path only |
  | architect | ADR path plus a 50-word summary |

- **Per-run budgets.** Record a guideline for each agent type in the suggestions file: maximum tool calls per run (starting points: Explore 10, log-triage 10, opus-consultant 10, code-reviewer 30, planner 40, architect 40, test-engineer 80, implementer 120). Scale by repo size. Exceeding a guideline is a signal to split the task, not an automatic failure.
- **Per-agent cost tracking.** `/cost-report` must break cost down by agent type if the usage data includes agent identity. If it does not, record "per-agent breakdown unavailable on this version" in the report.
- **Override name.** The built-in search agent is replaced only if its file is named exactly `Explore.md` and its frontmatter `name` is `Explore`. Check both.
- **Spawn depth.** Limit nested subagent spawning to 2 if this version documents a setting for it. Mark it unverified until tested.
- **Log-triage repo rules.** Set the documented field that skips CLAUDE.md loading (for example `omitClaudeMd: true`) on `log-triage` only, if supported. Mark it unverified until tested.

## Phase 3: Files to create or merge

**Root `CLAUDE.md`**: create only if missing. Spec: Stack, Commands, Conventions (two to five rules taken from the repo, not invented), Cost and delegation. Keep it under 150 lines. For a monorepo, list each package's commands briefly and put package-specific conventions in scoped rules instead. The Cost and delegation section must include: finish one task before starting another; keep a session for one topic; do not edit CLAUDE.md, rules or agents during a session; batch questions; use the named skills; use `log-triage` for long output; commit only after review and green tests.

**`.claude/rules/cost-and-delegation.md`**: create only when a root `CLAUDE.md` exists and is protected. Give it no `paths:` frontmatter so it applies everywhere. Include the same Cost and delegation rules. Flag in the report that unscoped rules must be verified to load every session.

**`.gitignore`** (root-anchored; merge, never remove or reorder existing rules; skip lines already present):
```
/.claude/*
!/.claude/settings.json
!/.claude/agents/
!/.claude/skills/
!/.claude/rules/
!/.claude/hooks/
.claude/settings.local.json
.claude/transcripts/
```
If the project already tracks other `.claude/` content on purpose, keep it tracked and note it.

**`.claude/settings.json`**: merge into existing JSON; never drop existing keys. Set:
- `model` to the default session model from the parameters.
- `permissions.allow` for the project's real lint, test, build, format and type-check commands, plus `git diff`, `git log` and `git status`.
- `permissions.deny` for reading `.env*` and other secret files (add patterns from the parameters and any found in the repo, such as `*.pem`, `*.key`, credential JSON), `rm -rf`, and force push.
- `env` with pinned model IDs, the subagent default model, the spawn-depth limit (if supported), and the TTL key only as decided in Phase 1b.
- A `PreToolUse` hook on matcher `Bash` running `bash .claude/hooks/pre-commit.sh`, in the hook JSON format documented for this version.
Never put API keys, project IDs, account IDs or credentials in this file.

**Agents** (`.claude/agents/*.md`). Each needs `name`, a `description` containing "Delegate here" and its trigger, `model`, `effort` (if supported on this version), `tools`, `maxTurns`, and a return limit at the end of its instructions.

Core agents (always create):

| File | Model | Effort | Tools | maxTurns | Extra |
|---|---|---|---|---|---|
| planner.md | opus | high | Read, Grep, Glob, Write | 40 | Return: plan path only |
| opus-consultant.md | opus | high | Read, Grep, Glob | 10 | Return: 300 words |
| implementer.md | sonnet | high | Read, Grep, Glob, Edit, Write, Bash, Agent(opus-consultant) | 120 | Return: 150 words |
| code-reviewer.md | sonnet | high | Read, Grep, Glob, Bash (read-only git), Agent(opus-consultant) | 60 | Return: ranked list |
| log-triage.md | haiku | low | Read, Grep, Bash | 15 | Skip CLAUDE.md if supported; return: 30 lines |
| Explore.md | haiku | low | Read, Grep, Glob | 30 | Exact name `Explore`; return: 150 words |

Conditional agents:

| File | Create when | Model | Effort | Tools | maxTurns | Extra |
|---|---|---|---|---|---|---|
| architect.md | Project has more than one service/module or an ADR folder | opus | high | Read, Grep, Glob, Write | 40 | Return: ADR path plus 50 words |
| test-engineer.md | Project has a test command | sonnet | high | Read, Grep, Glob, Edit, Write, Bash, Agent(opus-consultant) | 120 | Return: 100 words |

Also create `_TEMPLATE.md` with the same frontmatter fields and a return-limit line. Existing agents outside this list are kept unchanged and noted in suggestions. Confirm the `Agent(name)` tool syntax against this version; if it differs, use the documented form.

**Skills** (`.claude/skills/<name>/SKILL.md`). Use the exact file name `SKILL.md`. Skip any skill whose target agent was not created or whose prerequisite is missing.

| Skill | Mode | Target | Create when | Purpose |
|---|---|---|---|---|
| plan | fork | planner | Always | Write `<plans folder>/<topic>.md` |
| implement | fork | implementer | Always | Execute an approved plan |
| review | fork | code-reviewer | Always | Ranked findings on the diff |
| consult-opus | fork | opus-consultant | Always | One narrow question |
| cost-report | inline, `model: haiku` | none | Always | Run the usage report; show cost, cache-read share, and per-agent cost if available |
| wait | inline, `model: haiku` | none | Project has long-running jobs (builds, deploys, test suites over a few minutes) | Background jobs, no polling over 270 s |
| test | fork | test-engineer | test-engineer exists | Targeted tests, digest only |
| fix-issue | fork | implementer | Issue tracker referenced | Fix an issue, test, review, commit |
| pr-review | fork | code-reviewer | `gh` or `glab` available | Review a PR/MR by number |

Forked skills use `context: fork` and an `agent:` field. Use `$ARGUMENTS` for input. Do not create skills the project does not need; list skipped ones and why.

**Rules** (`.claude/rules/`): one file per area with distinct conventions (for example per language, per package in a monorepo, infrastructure, migrations), using `paths:` frontmatter. Keep each under 30 lines. Take conventions from the repo's linters, configs and existing code; do not invent style rules. Create `tests.md` when the project has tests.

**`.claude/hooks/pre-commit.sh`**:
- Read the hook payload from stdin. Exit 0 unless the Bash command contains `git commit`.
- Fail open: if a required tool is missing, exit 0 with a short note on stderr.
- Otherwise run, in this order and only those that exist: type check, lint on staged files, then tests (scoped to changed packages or files when the tooling supports it). Use the project's real commands from Phase 0.
- For a monorepo, run checks only for packages with staged changes.
- Exit 2 with a short message on failure.
- Use only POSIX shell features; no GNU-only flags without a fallback.
- Run `bash -n` on it and make it executable.

**`<usage report path>/README.md`**: placeholder describing a stdlib-only usage report (cost, cache-read share, per-agent cost if available). Do not write the script unless asked.

## Phase 4: Parallel execution

Parallel agents speed up development only for independent work.

- **Parallel:** different modules or packages, separate test files, reviews of separate PRs, searches across different directories.
- **Sequential:** anything touching the same file, migration, lock file, shared config, generated code, or schema. Plan with `/plan`, then implement.
- Use one git worktree per parallel agent (`isolation: "worktree"`).
- Give each parallel agent an explicit file scope and forbid edits outside it.
- Cap concurrency at the parameter value (default 3) unless the user approves more.
- Route each parallel task to the cheapest tier that can do it.
- Check for file overlap before starting. Overlapping tasks run in sequence.
- If the repo is not git, run sequentially and say so.

Parallel work also affects caching: each agent has its own context, so keep agent prompts short and stable so their prefixes cache well.

## Phase 5: Verification

1. `settings.json` parses as JSON. Each agent has `name`, `description`, `model`, `tools` and `maxTurns`.
2. `opus` appears only on architect (if created), planner and opus-consultant. opus-consultant has no `Agent` or edit tools.
3. `CLAUDE.md` (protected or created) and each rules file are 200 lines or fewer. Report line counts for protected files without changing them.
4. No secrets, project IDs, account IDs or credentials in created files.
5. `bash -n .claude/hooks/pre-commit.sh` passes.
6. If git is available, `git status --ignored` shows only the intended tracked set.
7. The two-turn cache test from Phase 1d has run and its result is recorded, or it is listed as pending.
8. Each agent's instructions end with a return limit that matches the Phase 2 table.
9. `Explore.md` exists with `name: Explore`.
10. Each agent `description` contains "Delegate here" followed by its trigger.
11. `log-triage.md` has the CLAUDE.md-skip field if supported. Mark it unverified.
12. `/cost-report` either shows per-agent cost or records that it is unavailable.
13. The suggestions file lists the per-run budget for each agent type created.
14. Every skill's target agent exists.
15. List every `<PIN: ...>`, `<TODO: ...>` and `<DECIDE: ...>` placeholder.

## Phase 6: Suggestions file and report

Write the suggestions file (default `docs/claude-setup-suggestions.md`). This is the only place to propose changes to protected files. Include:

1. **Protected files found:** path, line count, and whether root or subfolder.
2. **Suggested changes to each `CLAUDE.md`:** missing sections, conflicts with the cost plan (such as auto-commit after every change), content that belongs in `.claude/rules/`, ready-to-paste Cost and delegation text, subfolder duplication of root rules, and the cache rule against editing CLAUDE.md, rules or agents during a session.
3. **Suggested changes to each `SKILLS.md`:** Claude Code loads `SKILL.md` inside `.claude/skills/<name>/`, not `SKILLS.md`. Suggest migrating its content with `name` and `description` frontmatter, and note any duplicates.
4. **Per-run budgets for each agent type**, as set in Phase 2.
5. **Skipped agents and skills**, with the reason and what would justify adding them later.
6. **Suggested changes to other markdown:** agent descriptions that don't name a trigger, rules over 30 lines, and READMEs describing an old setup.

Then give a short chat report:
- Detected environment: OS and shell, platform, Claude Code version, stack(s), single repo or monorepo.
- Table of files created, merged, kept, skipped and backed up.
- Protected files found and confirmed untouched.
- Caching: TTL decision with its probe data, the two-turn test result (or pending), and the Claude Code version and platform.
- Model routing table, with pinned IDs or placeholders.
- Subagent cost controls applied, and whether per-agent cost tracking is available.
- Parallel rules applied.
- Remaining placeholders.
- Items to verify on the pinned version: each `env` key, the TTL key, the spawn-depth and CLAUDE.md-skip keys, `Agent(...)` tool syntax, `effort` field support, hook JSON format, whether unscoped rules load every session, and whether agent identity appears in usage data.
- Next steps: fill placeholders, run one `/plan` → `/implement` → `/test` → `/review` cycle on a small task, and compare cost per accepted task, cache-read share and per-agent cost against the baseline.

Do not claim a setting works until it has been tested. Mark unverified values as unverified.
