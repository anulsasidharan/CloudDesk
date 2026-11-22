# Phase 8 Interview Q&A: Memory

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code.

---

## A. Big picture

**Q1. What did you build in Phase 8?**
The memory layer, in a new `memory/` package: a short-term Redis facade (`short_term.py`), a long-term customer-notes facade (`long_term.py`), and a service with two calls, recall and record (`memory_service.py`).

**Q2. Which requirements does it cover?**
F4 (load previous notes for a customer), F11 (update customer memory after a run) and N7 (no secrets in memory notes).

**Q3. Why two kinds of memory?**
Different jobs. Short-term is fast and temporary: the conversation and progress of one ticket, gone in 24 hours. Long-term is permanent knowledge about the customer, such as past issues and what resolved them.

**Q4. Is anything calling memory yet?**
No. The graph nodes (`customer_context` for recall, `memory_update` for record) come in Phase 10. Phase 8 is built and tested alone, and I say so to avoid overclaiming.

**Q5. What is the demo checkpoint?**
Recording the CD-1002 refund twice does not duplicate the resolution note. `test_recording_twice_does_not_duplicate`.

**Q6. Why was memory built before the agents?**
It only depends on the database (Phase 2) and the secret scrub (Phase 7), not on agents. Building it earlier lets the agents use it from day one.

---

## B. Short-term memory

**Q7. What goes in Redis?**
Per-ticket conversation (`conv:{ticket_id}`, a list), a workflow state snapshot (`wfstate:{ticket_id}`), and the Phase 5 retrieval cache (`rag:{mode}:{category}:{top_k}:{query}`).

**Q8. What are the expiry times?**
24 hours for conversation and state, 300 seconds for the retrieval cache. The tests assert a positive TTL no greater than 86,400 seconds.

**Q9. How do you stop a conversation growing forever?**
`ltrim` keeps only the newest 50 messages, and each message is cut to 2,000 characters.

**Q10. Why scrub text going into short-term memory? It expires anyway.**
Defence in depth and cost. Scrubbing is cheap, and it means a secret never exists at rest in any store. Redis can also be inspected or snapshotted.

**Q11. What happens if Redis is down?**
Nothing breaks. Every short-term method catches the error, logs a warning and returns `False`, `[]` or `None`. Scratchpad data is advisory. A test uses a broken client to prove it.

**Q12. Why not the same for long-term memory?**
A failed permanent write should be visible. Silent loss of the customer's file is worse than a logged error. Long-term errors propagate to the caller.

**Q13. Who owns the retrieval cache?**
`rag/retriever.py`. `short_term.py` re-exports its key builder and TTL so there is one documented list of Redis contents, without a second definition that could drift.

**Q14. How does the code use fakeredis offline?**
`get_redis()` returns `FakeAsyncRedis` when `USE_FAKE_REDIS` is set or `REDIS_URL` is empty. Same API as real Redis, so tests need no container.

---

## C. Long-term memory

**Q15. What are the note kinds?**
`preference`, `past_issue`, `troubleshooting`, `note`. They come from the `MemoryKind` enum, and an unknown kind raises `ValueError`. The database also has a CHECK constraint.

**Q16. What happens to text before it is stored?**
Scrub (cards, keys, passwords become `[REDACTED:...]`), collapse whitespace, cap at 500 characters, skip if empty, then a duplicate check.

**Q17. How is a duplicate detected?**
A SHA-256 of the lower-cased, whitespace-normalised text. A duplicate means same customer, same kind, same hash. Differences in case or spacing still match.

**Q18. Why dedupe in code and with a unique constraint?**
Code gives a clean "skip" with no exception. The constraint (`uq_customer_memory_note`) is the backstop if two writers race between the check and the insert.

**Q19. Is the hash computed before or after scrub?**
After. The text that is hashed is the text that is stored, so two notes that differ only in a secret both become `[REDACTED:...]` and are treated as the same.

**Q20. How many notes does recall return?**
At most 10, newest first. The cap is enforced in the repository (`MAX_RECALL`) and cannot be exceeded by passing a bigger limit.

**Q21. Can customer A see customer B's notes?**
No. Every write and read is keyed by one `customer_id`. A test saves notes for two customers and checks each recall.

**Q22. Why a dataclass `MemoryNote` instead of returning database rows?**
Callers get a plain, immutable value with no session attached, so agents and nodes do not depend on SQLAlchemy.

---

## D. The service

**Q23. What does `record_resolution` write?**
Five notes: one `past_issue`, the first three `troubleshooting` steps, and one `note` starting "Resolution:". It returns `RecordResult(written, skipped_duplicates)`.

**Q24. Why only three troubleshooting steps?**
Enough to be useful, small enough to keep memory focused. It is a named constant, `MAX_TROUBLESHOOTING_STEPS`.

**Q25. Why does it take a summary and not the ticket text?**
CLAUDE.md says never store raw ticket bodies. They may hold private details or secrets. The caller passes a one-line issue summary and plan text.

**Q26. What does it do on a second run of the same ticket?**
Every note is an exact duplicate, so `written=0` and `skipped_duplicates=5`. The customer's file stays at five notes.

**Q27. What if the troubleshooting wording changes between runs?**
Then the notes differ and are stored as new ones. Dedupe is exact-match only. That is a known limit, not a bug.

---

## E. Security and privacy

**Q28. How do you prove no secret reaches the database?**
A test records a card number, an API key and a password through the service, reads every row from `customer_memory`, and asserts none of the three appear.

**Q29. Is the scrub guaranteed to catch everything?**
No. It is pattern-based (Luhn-checked cards, common key formats, password phrases). It is a strong net, not a guarantee, and the status section says so.

**Q30. Can memory be abused through prompt injection?**
Notes come from summaries and plans, not raw ticket text, which reduces the chance of an attacker planting instructions. Phase 9 will also wrap recalled notes as untrusted when it puts them in a prompt. That wrapping is not part of this phase.

**Q31. What about a customer asking to be forgotten?**
There is no delete path yet. TTL only covers short-term data. I list it as not built. The foreign key has `ON DELETE CASCADE`, so deleting a customer removes their notes, but a dedicated erasure flow is future work.

**Q32. Which of the "must never happen" rules does this touch?**
"Memory notes containing card numbers, keys, passwords, or raw ticket bodies" and, by keying on one customer, "another customer's data".

---

## F. Design and trade-offs

**Q33. Why a separate `memory/` package, not `backend/app/services`?**
CLAUDE.md puts memory at the top level with `rag/`, `agents/` and `integrations/`. It stays free of HTTP. It depends only downward on `core`, `repositories` and `rag`, and `core` never imports it.

**Q34. Why does the service take a session instead of creating one?**
So the caller owns the transaction. A graph node can commit memory with the rest of its work or roll everything back together.

**Q35. Why lazy Redis connection?**
Constructing a facade does no I/O, which keeps tests simple and lets one inject a client. The real client is fetched on first use.

**Q36. Why not store memory in a vector database for semantic recall?**
v1 only needs the 10 most recent notes per customer. A vector store adds cost and moving parts for little gain at this size. It is an upgrade path if notes grow.

**Q37. Why newest-first and not most-relevant?**
Simple and predictable. Relevance ranking is a later improvement.

**Q38. What would you change for production?**
Add an erasure path, similar-meaning dedupe, a retention policy for old notes, and real Redis with persistence and authentication.

---

## G. Testing

**Q39. How many tests, and how do they run?**
10 new tests in `tests/memory/test_memory.py`. The full suite is 304 passing, offline, with fakeredis and in-memory SQLite. Ruff is clean.

**Q40. What do they cover?**
24 h TTL, 50-message cap, scrub in conversation, state save and clear, Redis-down behaviour, cache key and TTL contract, long-term scrub and dedupe, recall cap of 10 and customer isolation, the five-note record, the run-twice checkpoint, and a no-secrets-in-database check.

**Q41. How do you simulate Redis being down?**
A stub client whose every method raises `ConnectionError`, then assert the facade returns safe defaults.

**Q42. What is not tested?**
Real Redis, real Postgres, and concurrent writers. Those need containers, which come in the final phase.

---

## H. Quick-fire

**Q43. Short-term TTL?** 24 hours.
**Q44. Retrieval cache TTL?** 300 seconds.
**Q45. Max recall?** 10 notes.
**Q46. Notes per resolution?** Five: one issue, three steps, one resolution.
**Q47. Max note length?** 500 characters.
**Q48. Max stored conversation?** 50 messages.
**Q49. Who may write `customer_memory`?** Only `LongTermMemory`.
**Q50. Phase 8 one-liner?** "The system remembers each customer, safely: scrubbed, de-duplicated, capped, and never another customer's data."
