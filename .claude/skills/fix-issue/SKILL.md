---
name: fix-issue
description: Fix an issue, run tests, request review, then commit once green.
argument-hint: <issue number or description>
context: fork
agent: implementer
---
Fix issue: $ARGUMENTS. Steps: reproduce, fix within minimal scope, run targeted tests, then report changed files. Do not commit until the caller confirms review and green tests.
