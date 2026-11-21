---
name: cost-report
description: Show Claude Code cost, cache-read share of input tokens (7 days) and per-agent cost if available.
argument-hint: 
model: haiku
---
Run `python scripts/claude_usage/report.py` (stdlib only). If the script does not exist, say so and stop. Show: total cost, cache-read share of input tokens for the last 7 days (a drop after rollout means something is breaking the cache), and cost by agent type. If the usage data has no agent identity, print "per-agent breakdown unavailable on this version".
