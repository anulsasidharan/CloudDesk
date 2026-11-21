---
name: wait
description: Wait for a background job without polling more often than needed.
argument-hint: <job or condition>
model: haiku
---
Wait for: $ARGUMENTS. Use a single blocking check or a background run; never poll more often than every 270 s. Report only the final state.
