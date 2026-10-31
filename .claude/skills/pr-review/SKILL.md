---
name: pr-review
description: Review a GitHub PR by number.
argument-hint: <PR number>
context: fork
agent: code-reviewer
---
Review PR #$ARGUMENTS using `gh pr view` and `gh pr diff`. Return ranked findings.
