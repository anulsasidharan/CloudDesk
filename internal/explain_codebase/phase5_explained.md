# Phase 5 Explained: The Searchable Help Library

*CloudDesk: Autonomous Customer Support & Resolution Platform*

---

## 1. The project in one minute

**CloudDesk** is a fictional company that sells online tools for teamwork: file storage, shared workspaces, billing. Customers write in with problems ("I can't log in", "I was charged twice"). Each message is a **ticket**.

We are building an **AI assistant that investigates tickets for the human support agent**. It works out how urgent the ticket is, looks up the customer, finds the right help article, suggests a fix and drafts a reply. **Anything that costs money or changes an account waits for a human to approve.**

---

## 2. The 13 phases

| Phase | Name | In plain words |
|---|---|---|
| 1 | Runtime skeleton | The foundation: the system starts and reports its health. *(done)* |
| 2 | Persistence and demo data | The filing cabinet, filled with sample data. *(done)* |
| 3 | Identity and request guards | The security guards at the door. *(done)* |
| 4 | Support API | The reception desk: create and read tickets and customers. *(done)* |
| **5** | **Knowledge pipeline** | **The searchable help library.** |
| 6 | Tools and policy | The tools the AI may use, and which need permission. |
| 7 | Rules and guardrails | The rulebook and defences against trickery. |
| 8 | Specialist agents | The team of AI specialists. |
| 9 | Workflow graph and trace | The step-by-step process with a visible trail. |
| 10 | Approval and escalation | The "ask a human first" gate. |
| 11 | Memory | Remembering each customer. |
| 12 | Agent console | The screen the agent uses. |
| 13 | Evaluation and delivery | Measuring quality and packaging for the cloud. |

---

## 3. What Phase 5 is

A support agent who answers "how do I recover a locked account?" from memory will sometimes be wrong. A good one **looks it up in the company's help articles and quotes them**. Our AI must do the same, because it must never make up company policy.

Phase 5 builds the **help library and its search engine**. We have 15 help articles (refunds, MFA lockouts, API limits, and so on). Phase 5 makes them **searchable by meaning, not just by exact words**, and makes every answer come back with a **citation**: which article, which section.

### 3.1 The library analogy

Imagine a library with 15 books, and a very fast librarian.

| Step | In a library | In our system |
|---|---|---|
| **1. Cut into pages** | Photocopy each book chapter by chapter, so you can hand over just the relevant page, not the whole book | **Chunking**: each article is cut at its headings into small pieces (about 900 characters). We got 46 pieces from 15 articles. |
| **2. Label each page** | Stamp every page with the book title and chapter name, so a page that just says "Wait 30 minutes" still says what it is about | Every piece starts with "Article title - Section". |
| **3. Index by meaning** | A card catalogue that files pages by *topic*, so "locked out" finds the page about "account lockout" | **Embeddings and a vector store**: each piece becomes a list of numbers that captures its topic. Similar topics have similar numbers. |
| **4. Two librarians** | One finds pages that *mean* the same; another finds pages with the *same words* | **Hybrid search**: a meaning search and a keyword search run together. |
| **5. Combine their votes** | If both librarians point at the same page, trust it more | **Rank fusion**: pages that rank well in both lists rise to the top. |
| **6. One page per book** | Do not hand over five pages of the same book | The final answer has **at most one hit per article**. |
| **7. Remember recent questions** | If the same question is asked twice in five minutes, reuse the answer | **A short-term cache** (5 minutes). |

### 3.2 Why two kinds of search?

- **Meaning search** understands that "I can't get in" and "account locked" are related, but can miss exact product words such as "429".
- **Keyword search** is exact, but misses synonyms.

Together they cover each other's blind spots. We checked this: on the 12 demo tickets that have a matching article, our combined search put the right article **in the top 3 every time (12 out of 12)**, and first place 11 times.

### 3.3 How it works with no internet and no paid AI

The demo has to run on a laptop with no account and no cost. So the "meaning numbers" come from a **fake embedder**: a simple, repeatable method that turns words into numbers. It is not as smart as a real AI model, but it is predictable, free and instant. Because everything is behind a single plug-in point, switching to a real model or a cloud database later is a settings change, not a rewrite.

### 3.4 What an agent can do with it

Four new screens-worth of capability are exposed to the console:

| Action | Who | Result |
|---|---|---|
| Browse or search the list of articles | Anyone logged in (viewer and up) | Title, category, summary |
| Open one article | Anyone logged in | Full text. Works with the long ID or the short name (`mfa-recovery`) |
| **Search the library** | Anyone logged in | Best articles, each with a citation like `kb://mfa-recovery#why-accounts-lock`, a snippet and a score |
| **Rebuild the library index** | **Admins only** | Throws away the old index and rebuilds it from the articles |

The rebuild is admin-only because it replaces the entire searchable library. If it were wrong, every AI answer would be affected.

### 3.5 The "checkpoint" we can demo live

Run one command (`make ingest`). It builds the library and then replays real ticket **CD-1012** ("Locked out after too many MFA attempts"). The system prints its top three articles, and the **MFA recovery article is number one**:

```text
indexed 15 articles into 46 chunks
  1. kb://mfa-recovery#why-accounts-lock
  2. kb://billing-seat-changes-and-proration#lowering-seats
  3. kb://api-rate-limits#http-429
CD-1012 -> mfa-recovery in top 3: yes
```

---

## 4. How we know it works

We added **37 new automated tests**, bringing the total to **164, all passing**, with the style checker clean. Highlights:

- Articles are cut at headings, long sections overlap by 150 characters so no sentence is lost at a boundary, and every piece carries its title.
- The fake embedder gives the **same numbers every time** and related texts score closer than unrelated ones.
- All three search modes find the MFA article for the MFA ticket.
- Filters really filter: searching only the billing category returns only billing pieces.
- **The cache works**: a repeated question is answered without searching again, and a rebuild clears stale answers. If the cache is down, search still works.
- **Hit-rate check**: retrieval must find the right article in the top 3 for at least 75% of tickets. We get 100% on the demo set.
- Viewers and agents get **403** on the rebuild. Admins can run it, and search still works afterwards.

---

## 5. What is honest to say is *not* done

- **The AI does not use the library yet.** The specialist that reads the library and cites it is built in a later phase. Phase 5 builds the library and the search engine it will use.
- **The "smart" embedder is a stand-in.** It is deterministic and free but not as good at meaning as a real model. Real models are not wired in yet.
- **The cloud database for the index (Qdrant) is written but has never been run.** Only the in-memory version is tested.
- **The 100% hit-rate is optimistic.** The 12 test tickets were written together with the 15 articles. A fair measure needs the larger evaluation set planned for the last phase.
- **An optional "AI re-ranker" is a plug-in point only.** Nothing is connected to it yet.
- The in-memory index is rebuilt each time the server starts (about 46 small pieces, instant). With the cloud index it would persist.
- Nothing is deployed to the cloud.

---

## 6. The 30-second version to say out loud

> "Phase 5 is the searchable help library. We cut our 15 help articles into small labelled pieces, turn each into numbers that capture its topic, and search two ways at once: by meaning and by exact words. We combine the two ranked lists, so a page both methods like wins, and we return one result per article with a citation. That matters because the AI must quote real company policy and never invent it. It runs fully offline, caches repeated questions for five minutes, and only an admin can rebuild it. On our 12 demo tickets the right article is in the top three every time. 37 new tests prove it, and I'm upfront that the AI isn't using the library until a later phase."

---

## 7. Where Phase 5 fits

```text
Phase 1: the building stands.        Phase 2: the filing cabinet is full.
Phase 3: guards at the door.         Phase 4: the reception desk opens.
Phase 5: the help library opens.     <-- we are here
Phase 6-7: tools and the rulebook.   Phase 8-10: the AI team and its process.
```
