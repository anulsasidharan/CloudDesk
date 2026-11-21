---
title: API authentication errors
category: api_failure
tags: [api, 401, 403, token, key]
summary: Diagnosing 401 and 403 responses from the public API.
---

# API authentication errors

## 401 Unauthorized
The token is missing, expired or revoked. Create a new API key in workspace settings.

## 403 Forbidden
The key is valid but lacks the scope for the endpoint, or the workspace blocks the action.

## Safe handling
Never ask a customer to paste an API key into a ticket. If a key was posted, tell them to revoke it immediately.
