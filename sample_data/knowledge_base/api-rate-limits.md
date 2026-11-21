---
title: API rate limits
category: api_failure
tags: [api, 429, rate limit, retry-after, backoff]
summary: Per-plan request limits and how to handle HTTP 429 responses.
---

# API rate limits

## Limits per minute
Free 60 requests, Pro 300, Business 1200, Enterprise 3000. Limits apply per workspace across all API keys.

## HTTP 429
A 429 response includes a Retry-After header with the seconds to wait. Clients should back off exponentially and retry after that delay.

## Reducing usage
Batch operations, use the changes feed instead of polling, and spread scheduled jobs over a longer window. The API boost add-on doubles the limit.
