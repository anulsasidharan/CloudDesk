# Phase 5 Interview Q&A: Knowledge Pipeline

*CloudDesk: Autonomous Customer Support & Resolution Platform*

Answers are written the way you would say them out loud. Each includes where it lives in the code so you can back it up.

---

## A. Big picture

**Q1. What did you build in Phase 5?**
The searchable help library. The 15 knowledge articles are cut into chunks, turned into vectors, indexed, and searched by a hybrid retriever that combines meaning search and keyword search. Four API routes expose it: list and open articles, search, and an admin-only reindex.

**Q2. Which requirements does it cover?**
F5 (cited evidence from the knowledge base: semantic plus keyword, reranked) and the retrieval half of F6. The "find similar resolved cases" half and the agent that uses all this come in the specialist-agents phase.

**Q3. Why does a support AI need retrieval at all?**
Because it must never invent company policy. Retrieval gives the model real article text to quote, and every result carries a citation (`kb://slug#section`). CLAUDE.md says knowledge articles are the only source for customer-facing policy claims.

**Q4. Is the AI using it yet?**
No. Phase 5 builds the search engine and the API. The Knowledge Agent that calls `retrieve()` during a ticket run is a later phase. I say this plainly because it is easy to overclaim.

**Q5. What is RAG, in one sentence?**
Retrieval-Augmented Generation: find the relevant documents first, then give them to the model so its answer is grounded in them instead of in its memory.

---

## B. Chunking

**Q6. How do you chunk?**
Split on headings first, then cut long sections into 900-character windows with 150 characters of overlap, preferring to cut at a space. Every chunk's text is prefixed with `"{title} - {heading}"`. Code: `rag/chunking.py`, `chunk_article`, `split_sections`, `window`.

**Q7. Why chunk at all? Why not embed whole articles?**
One vector per article blurs several topics together and cannot point to the right section. A chunk answers one question, so retrieval is sharper and the citation can name the section.

**Q8. Why split on headings before windowing?**
A heading is the author's own topic boundary. Windowing alone could cut a section in the middle of a step list.

**Q9. Why overlap?**
So a sentence that straddles a boundary appears whole in at least one window. A test checks that the head of each window appears in the tail of the previous one.

**Q10. Why the title prefix?**
A short chunk like "Wait 30 minutes for the lock to clear" is nearly unfindable on its own. With "MFA lockout and recovery - Why accounts lock" in front, both the embedding and the keyword index know what it is about.

**Q11. How many chunks do you get?**
15 articles produce 46 chunks. `make ingest` prints it.

**Q12. What happens with a heading that has no text?**
It produces no chunk. The `# Title` line is followed immediately by a `##` heading, so it is skipped.

---

## C. Embeddings and the vector store

**Q13. What are embeddings?**
A list of numbers that represents the meaning of a text, so texts about similar things end up close together. Closeness is measured with cosine similarity, which on unit-length vectors is a dot product.

**Q14. You use fake embeddings. Isn't that cheating?**
It is a deliberate trade-off, and I label it as such. The demo must run offline with no key and no cost (requirement F14). `FakeEmbeddings` hashes each word into one of 384 buckets with a plus or minus sign, then normalises. Texts that share words point in similar directions. It is deterministic, free and instant, but it is weaker than a real model at true synonyms. Swapping in a real provider is a settings change behind `get_embeddings()`; only `fake` is implemented today.

**Q15. Why `blake2b` and not Python's `hash()`?**
`hash()` is randomised per process for strings, so vectors would differ between runs and a Qdrant collection built yesterday would not match today's queries. `blake2b` is stable.

**Q16. Why 384 dimensions?**
It is the size the spec fixes for the fake embedder (`EMBEDDING_DIMENSIONS`), and a common size for small real models. A Qdrant collection is created with a fixed size, so changing the dimension means recreating the collection.

**Q17. What is `VectorStoreService`?**
A Python `Protocol` with `add_documents`, `search`, `delete`, `count` and `health`. `InMemoryVectorStore` and `QdrantVectorStore` both satisfy it and `VECTOR_STORE` picks one. Nothing else in the code knows which is running.

**Q18. The spec lists five methods. You have six?**
Yes, I added `list_chunks`. BM25 keyword search needs the whole corpus, and the protocol had no way to hand it over. I recorded the decision in MEMORY.md.

**Q19. What does `delete(None)` mean?**
Recreate the whole collection. `delete([article_ids])` removes only those articles' chunks. Reindex uses the first form so deleted or renamed articles cannot linger.

**Q20. Is the Qdrant store tested?**
No, and I say so. It is written against the Qdrant client API, imports the client lazily, and `qdrant-client` is not a dependency. It has never run against a real server. The in-memory store carries all the tests.

---

## D. Retrieval

**Q21. Walk me through a search.**
1. Check Redis for a cached answer.
2. Semantic search: top 20 chunks by vector similarity.
3. Keyword search: BM25 over all chunks, top 20.
4. Fuse the two ranked lists with reciprocal rank fusion.
5. Heuristic rerank (category hint, title overlap).
6. Optional LLM rerank hook.
7. Keep only the best chunk per article, take the top `top_k`.
8. Cache the result for 300 seconds.
Code: `retrieve()` in `rag/retriever.py`.

**Q22. Why hybrid? Why not just vector search?**
Vectors capture meaning but can miss exact tokens such as "429" or a product name; keywords are exact but miss synonyms. Each covers the other's blind spot. Measured on the demo tickets: hybrid found the right article in the top 3 for 12 of 12, with 11 at rank 1.

**Q23. What is reciprocal rank fusion, and why use it?**
Each item's score is the sum of `1 / (60 + rank)` over every list it appears in. It merges ranked lists using ranks only. That matters because BM25 scores and cosine scores are on completely different scales, so adding them directly would let one method drown the other. An item both methods like beats an item only one likes.

**Q24. Why k = 60?**
It is the standard constant from the original RRF paper and the value fixed in the spec. It damps the difference between rank 1 and rank 2 so one lucky top spot does not dominate.

**Q25. Did you use a BM25 library?**
No. The spec mentions `rank_bm25`, but it is not installed, and BM25 is about thirty lines. I wrote a small Okapi BM25 (`k1=1.5`, `b=0.75`) to avoid a dependency. It is rebuilt on every call, which is fine for 46 chunks. With a large corpus I would cache the index or use the store's own keyword search. Recorded in MEMORY.md.

**Q26. What does the heuristic rerank do?**
Adds a small boost when a chunk's category matches the hint, and a boost proportional to how many of the title's words appear in the query. The boosts are small next to one rank step of RRF, so they break near-ties rather than overruling the search.

**Q27. What is the difference between `category` and `category_hint`?**
`category` is a hard filter: only that category is searched. `category_hint` only nudges ranking. The future Knowledge Agent will pass the classifier's category as a hint, so if the classifier is wrong, the right article can still surface.

**Q28. Why one hit per article?**
Without it, five chunks of the refund policy could fill the top 5 and hide every other source. The agent gets diverse evidence, and a reply cites distinct articles.

**Q29. What shape is a result?**
`Evidence`: `id`, `title`, `source` (`kb://slug#section`), `snippet` (first 240 characters), `score`, `url` (`/knowledge/<article id>`), `article_id`. The score orders results; it is not a probability.

**Q30. What are the three modes?**
`hybrid` (default), `semantic`, `keyword`. The API validates the value (422 otherwise).

**Q31. What is the LLM rerank?**
An optional hook: an async function that reorders the results. The spec lists an LLM rerank step. There is no LLM call path until a later phase, and all LLM calls must go through `call_structured`, so I left a hook rather than a half-built call. A test shows a reranker can reorder results.

---

## E. Caching

**Q32. How does caching work?**
Key `rag:{mode}:{category}:{top_k}:{query}`, value is the JSON evidence list, TTL 300 seconds, in Redis (fakeredis offline).

**Q33. What if Redis is down?**
Search still works. Cache reads and writes are wrapped so any error falls through to a live search. A test uses a cache that raises on every call. The cost is speed, never correctness.

**Q34. How do you avoid serving stale answers?**
Ingest deletes every `rag:*` key after a rebuild. A test fills the cache, invalidates it, and checks no keys remain.

**Q35. Why skip the cache when an LLM reranker is given?**
Its output may not be a pure function of the query, so caching it could return another caller's ordering.

---

## F. Ingest and the API

**Q36. How do the articles get into the index?**
`knowledge_service.reindex` reads all articles from `support_articles` (put there by the Phase 2 bootstrap), maps them to plain records and calls `rag.ingest.ingest_articles`. The database is the source of truth; the index is rebuildable.

**Q37. Why does a service sit between the API and `rag/`?**
Layering. `rag/` must not know about tickets or SQL, and repositories must not touch the index. The service is the only place both meet. The route stays HTTP-only.

**Q38. When is the index built?**
At startup, after demo data loads (`ensure_indexed` in the lifespan), and again on first search if the store is empty. If indexing fails at startup it logs a warning and the API still boots.

**Q39. Why is reindex admin-only?**
It replaces the entire library every AI answer cites. Tests prove viewer and agent get 403 and admin gets `{indexed, articles}`, after which search still works.

**Q40. Why can a viewer search?**
CLAUDE.md gives viewers read access to knowledge. Search changes no data, so it needs only the lowest role.

**Q41. Can I fetch an article by a friendly name?**
Yes. `GET /knowledge/articles/{id}` accepts the UUID or the slug (`mfa-recovery`), the same idea as accepting `CD-1001` or a UUID for tickets. Missing gives 404 `Article not found`.

**Q42. What does `make ingest` do?**
Loads the data if needed, rebuilds the index, then replays ticket CD-1012 and prints the top 3. Exit code 0 only if the MFA recovery article is among them. Note the in-memory index lives only for that process; with Qdrant it persists.

**Q43. You changed the API contract again. What changed?**
Marked the four routes implemented, added the optional `category` filter to search, defined `Evidence`, and defined `/reindex` as `{indexed: chunks, articles}`. The contract rule is that contract, schemas and types change together.

**Q44. A search is a POST. Is it audited?**
Yes, the Phase 3 audit middleware records every non-GET request. Fine for the demo; at scale I would exclude read-only searches.

---

## G. Testing and quality

**Q45. How did you test it?**
37 new tests, 164 in total, all offline. They cover chunking rules, deterministic embeddings, store add/search/filter/delete, all three modes, RRF math, rerank, BM25, one hit per article, cache hit, cache invalidation, a broken cache, the rerank hook, ingest counts and recreate, the hit-rate threshold, and the API's auth, validation and RBAC.

**Q46. What is hit-rate@3?**
The fraction of test tickets whose expected article appears in the top 3 results. The project threshold is 0.75. I measure it over the 12 demo tickets that have a matching article (CD-1013 is a prompt injection with no article): hybrid scores 12 of 12.

**Q47. Is 100% believable?**
Not by itself, and I would not present it as a quality claim. The tickets and articles were written together, so the set is easy. It proves the pipeline works end to end and guards against regressions. A fair measure needs the larger evaluation dataset planned for the final phase.

**Q48. Did the test run reveal anything?**
Two of my own tests failed on first run because I searched for a word ("account") that the billing articles do not contain. The code was right; the test queries were wrong. I fixed the tests rather than bending the code.

**Q49. How is test isolation handled?**
The rag tests build their own private in-memory store and a fresh fakeredis instance, so they never share state with the app's singleton store.

---

## H. Design trade-offs and "what would you change?"

**Q50. Biggest trade-off?**
Fake embeddings. It makes the demo free, offline and deterministic, at the cost of weaker semantic matching. The retrieval design does not change when a real model arrives.

**Q51. How would you scale this to 10,000 articles?**
Real embeddings, Qdrant with its payload filter, ANN indexing, and either Qdrant's sparse vectors or a persistent BM25 index instead of rebuilding per query. Batch embedding during ingest, and incremental ingest instead of recreating the collection each time.

**Q52. How do replicas behave with the in-memory store?**
Each replica has its own index, built at startup, so a reindex call affects only one replica. That is acceptable for a demo; the cloud profile uses Qdrant so the index is shared. I reasoned about this but have not tested multiple replicas.

**Q53. What if an article is edited?**
For now, run reindex. Incremental update by article id is possible because `delete([article_ids])` exists, but no route or trigger calls it yet.

**Q54. What security considerations apply?**
Article text is company-authored, not customer input, so it is not treated as untrusted. Customer ticket text used as a *query* is just a search string. It is not executed or given to the model here. Prompt-injection wrapping arrives with the guardrails phase before any text reaches an LLM. Search `query` is length-capped at 500 characters.

**Q55. What is not done?**
- The Knowledge Agent and similar cases (later phase).
- Real embeddings and any provider other than `fake`.
- Qdrant has never been run.
- LLM rerank has no caller.
- Readiness does not probe the vector store.
- Hit-rate measured on a small, optimistic set.
- Nothing is deployed.

**Q56. Give me the 20-second summary.**
"Phase 5 is the help library. Articles are chunked by heading, embedded, and searched two ways at once, by meaning and by keyword, then merged by rank so a page both like wins. Each result has a citation, one per article, and repeated questions are cached for five minutes. It runs offline, is admin-only to rebuild, and the right article is in the top three for all 12 demo tickets. The AI doesn't use it until a later phase, and the cloud vector store is written but untested."
