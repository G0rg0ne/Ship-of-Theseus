# Development log

## [2026-03-23 12:00] - FEATURE

### Changes
- Added authenticated route **`/how-it-works`** with an in-app guide: pipeline overview (upload → extract → community graph → explore), feature sections (document upload, document graph, brain graph, chat/Q&A, real-time visualization), quick-start checklist, and CTAs back to the dashboard.
- Dashboard header now includes a **How it works?** link to that page (next to Admin for admins).

### Files Modified
- `frontend-next/src/app/how-it-works/page.tsx` (new)
- `frontend-next/src/app/dashboard/page.tsx`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Users need a single place to learn how to use the app, what each panel does, and how GraphRAG-style Q&A relates to their documents and live graphs.

### Breaking Changes
None.

### Next Steps
Optional: add a matching link from the welcome page for logged-out users, or extract shared header icons to a small component to avoid duplication.

---

## [2026-03-14] - BUGFIX: Filter entity hits by QUERY_SIMILARITY_THRESHOLD before neighborhood expansion

### Changes
- **query_service:** In both the sync and streaming query pipelines, entity hits from `vector_search_entities` are now filtered by `score >= QUERY_SIMILARITY_THRESHOLD` before building `entity_keys` and calling `get_entity_neighborhood`. Previously the threshold was only applied later to communities, so low-score entity matches were still expanded into triplets and could dominate the local/hybrid prompt. A new `filtered_entities` list is used for expansion and passed as `entities_for_context` into `_build_context_and_sources` so context and sources only include above-threshold entities.

### Files Modified
- `backend/app/services/query_service.py`

### Rationale
Noisy or low-similarity entity matches were being expanded into full neighborhoods, adding irrelevant triplets to the synthesis context. Applying the same similarity threshold to entities before expansion keeps the prompt focused on high-signal matches and aligns entity pruning with community pruning.

### Breaking Changes
None. Same threshold and behavior for communities; entities now use it earlier in the pipeline.

### Next Steps
None.

---

## [2026-03-14] - FEATURE: Include vector-search entity hits in context and sources

### Changes
- **query_service:** `_build_context_and_sources` now accepts an optional `entities: List[Dict[str, Any]]` (e.g. from `vector_search_entities`). When provided, each entity is deduplicated by `(document_name, id)`, then added to the context string as an identity card line `[Entity <id>]\n<description_or_label+type>` and to the sources list as `SourceAttribution(type="entity", id=..., label=..., excerpt=description[:200]+'…')`. Entity cards are emitted before communities and triplets so synthesis sees matched entities first.
- **query_service:** Both call sites of `_build_context_and_sources` (sync and streaming pipeline) now pass the retrieved `entities` from the local/hybrid flow.
- **neo4j_service:** `vector_search_entities` now returns a `description` field (entity identity-card text from the node) so the query pipeline can surface it in context and in source excerpts.

### Files Modified
- `backend/app/services/query_service.py`
- `backend/app/services/neo4j_service.py`

### Rationale
The context builder previously ignored the actual entity hits from `vector_search_entities` and only used them to fetch triplets. Including entity identity cards and source attributions ensures the LLM and the UI get the matched entities and their descriptions for synthesis and citation.

### Breaking Changes
None. `entities` is optional; existing callers without it behave as before.

### Next Steps
None.

---

## [2026-03-14] - CONFIG: Composite index for :Entity neighborhood lookups

### Changes
- **neo4j_service:** In `_ensure_indexes()`, added a composite b-tree index on `:Entity` for `(user_id, document_name, id)`. `get_entity_neighborhood()` matches `(e:Entity)` by this tuple on the request hot path; without the index Neo4j falls back to a label scan as the graph grows. Index creation uses `CREATE INDEX entity_scope_idx IF NOT EXISTS FOR (n:Entity) ON (n.user_id, n.document_name, n.id)` and runs before the existing Person/Organization/Location/KeyTerm indexes.

### Files Modified
- `backend/app/services/neo4j_service.py`

### Rationale
Neighborhood expansion uses the composite key (user_id, document_name, id) to scope Entity lookups. Existing indexes were only on :Person, :Organization, :Location, :KeyTerm (document_name and document_name+id); they do not apply to a generic :Entity match, so adding the Entity composite index allows the planner to use it for the MATCH in get_entity_neighborhood().

### Breaking Changes
None. Index is created if not exists; no migration script required.

### Next Steps
None.

---

## [2026-03-14] - BUGFIX: Prevent unbounded history when CHAT_HISTORY_WINDOW is zero/invalid

### Changes
- **query_service:** When `CHAT_HISTORY_WINDOW` is 0 or invalid, `[-max_messages:]` with `max_messages == 0` returns the full list in Python, silently disabling trimming and bloating Redis/prompt payloads. Introduced `max_messages = max(0, int(history_window) * 2)` and a module-level `_trim_messages(items, max_n)` that returns `items[-max_n:]` when `max_n > 0` else `[]`. All history slices (cache fingerprint snapshot, cache-hit save, synthesis history, final save) now use `_trim_messages(...)` so zero/negative window yields empty history.

### Files Modified
- `backend/app/services/query_service.py`

### Rationale
Python slice `list[-0:]` is equivalent to `list[:]`, so a zero window did not trim; fixing this ensures `CHAT_HISTORY_WINDOW=0` correctly disables conversation history.

### Breaking Changes
None. `CHAT_HISTORY_WINDOW=0` now behaves as documented (no history).

### Next Steps
None.

---

## [2026-03-14] - BUGFIX: Guard top_k before vector-index calls in neo4j_service

### Changes
- **neo4j_service:** In `vector_search_entities` and `vector_search_communities`, added early return when `top_k <= 0` (alongside existing `not query_vector` check). This prevents computing `fetch_k`/`candidate_k` as non-positive and avoids calling `db.index.vector.queryNodes(...)` with invalid parameters.

### Files Modified
- `backend/app/services/neo4j_service.py`

### Rationale
When `top_k <= 0`, `fetch_k = min(..., top_k * 2)` and `candidate_k = min(..., top_k * 5)` can be zero or negative, which can break the Neo4j vector index API. Returning empty results for non-positive `top_k` is the correct behavior.

### Breaking Changes
None.

### Next Steps
None.

---

## [2026-03-14] - BUGFIX: Answer cache key includes conversation-state fingerprint

### Changes
- **query_service:** Answer cache fingerprint now includes a hash of the trimmed conversation history (same window used for synthesis), so cache identity reflects the current conversation state. In both `run_query_pipeline` and `run_query_pipeline_stream`: load chat history once before the cache check; build `history_snapshot` as the last `max_messages` entries, `history_hash = sha256(json.dumps(history_snapshot, sort_keys=True))`; set `cache_fingerprint = f"{mode}|{session_id or ''}|{history_hash}|{question}"`. Reuse the loaded history for synthesis to avoid a second Redis read. Removed duplicate history fetch in cache-hit branches.

### Files Modified
- `backend/app/services/query_service.py`

### Rationale
Synthesis is history-aware (conversation context is sent to the LLM). The cache key previously used only `mode|session_id|question`, so the same question after new turns could return a stale cached answer. Including the history fingerprint ensures cache hits only when the question and the conversation state (last N turns) match.

### Breaking Changes
None. Existing cache entries will miss (different key shape); new entries are keyed by user + hash(mode|session_id|history_hash|question). Old keys expire by TTL.

### Next Steps
None.

---

## [2026-03-14] - BUGFIX: CHAT_HISTORY_WINDOW applied as turns (not raw message count)

### Changes
- **query_service:** `CHAT_HISTORY_WINDOW` is documented as conversation **turns** (user+assistant pairs). The code was trimming to `history_window` **messages**, under-keeping context and diverging from the cache-hit branch (which already used `history_window * 2`). Introduced `max_messages = history_window * 2` in both `run_query_pipeline` and `run_query_pipeline_stream`; history is now sliced with `history_messages[-max_messages:]` when loading from Redis and `to_save[-max_messages:]` when saving, so behavior is consistent across cache-hit and normal paths.

### Files Modified
- `backend/app/services/query_service.py`

### Rationale
Docs and config describe the setting as "max conversation turns"; one turn = two messages. Using raw `history_window` as message count kept only half the intended turns and was inconsistent with the cache-hit branches.

### Breaking Changes
None. Existing sessions may now retain more messages (up to 2×) before trim; behavior now matches documentation.

### Next Steps
None.

---

## [2026-03-14 14:00] - BUGFIX: Include mode and session_id in query answer cache key

### Changes
- **query_service:** Answer cache key is now derived from `mode`, `session_id`, and `question` (fingerprint `f"{mode}|{session_id or ''}|{question}"`), hashed with SHA256, and passed to `cache_key_query_answer(user_id, question_hash)`. Applied in both `run_query_pipeline` and `run_query_pipeline_stream`. Replaced MD5 with SHA256 for the fingerprint hash.

### Files Modified
- `backend/app/services/query_service.py`

### Rationale
Previously the cache key used only a hash of the question, so the same question in different modes (global/local/hybrid) or different conversation sessions could receive a cached answer from another context. Mode affects retrieval strategy and session history is passed to synthesis; caching without these parameters could return incorrect or stale answers.

### Breaking Changes
None. Existing cache entries keyed only by user + question hash will no longer be hit; new entries are keyed by user + (mode|session_id|question) hash. Old keys will expire by TTL.

### Next Steps
None.

---

## [2026-03-14 14:01] - BUGFIX: Scope neighborhood and entity search by (user_id, document_name, id)

### Changes
- **vector_search_entities:** RETURN now includes `node.user_id`, `node.document_name`, and `node.id` so each result carries the full composite key; Python result dicts include `user_id` and `document_name` in addition to `id`, `label`, `entity_type`, and `score`.
- **get_entity_neighborhood:** Signature changed from `(entity_ids: List[str], user_id: str)` to `(entity_keys: List[Dict[str, str]])` where each dict has `user_id`, `document_name`, and `id`. Cypher now uses `UNWIND $entity_keys AS ek` and matches on `e.user_id = ek.user_id AND e.document_name = ek.document_name AND e.id = ek.id` (and same-document target `t`) so neighborhood is scoped per document and avoids collisions when the same entity id exists in multiple documents.
- **query_service:** Both `run_query_pipeline` and `run_query_pipeline_stream` build `entity_keys` from `vector_search_entities` results and call `get_entity_neighborhood(entity_keys)`; entities without `user_id` or `document_name` are skipped for neighborhood lookup.

### Files Modified
- `backend/app/services/neo4j_service.py`
- `backend/app/services/query_service.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Neighborhood queries previously matched only on `entity_id` and `user_id`, allowing the same entity id in two documents to mix edges. Scoping by the full tuple `(user_id, document_name, id)` aligns with embedding key usage and keeps retrieval document-isolated.

### Breaking Changes
- **get_entity_neighborhood** now expects a list of `{user_id, document_name, id}` dicts instead of `(entity_ids, user_id)`. Callers must use the composite key from `vector_search_entities` (or equivalent).

### Next Steps
None.

---

## [2026-03-14 14:02] - REFACTOR: Use asyncio.get_running_loop() in query_service async paths

### Changes
- Replaced `asyncio.get_event_loop()` with `asyncio.get_running_loop()` in `query_service.py` for all executor usage. In the first router-invoke block the loop variable was removed and `asyncio.get_running_loop().run_in_executor(...)` is used inline; in the two places where the loop is reused for multiple `run_in_executor` calls, `loop = asyncio.get_running_loop()` is used so subsequent calls stay correct.

### Files Modified
- `backend/app/services/query_service.py`

### Rationale
In Python 3.10+, `get_event_loop()` inside an async context is deprecated; `get_running_loop()` returns the currently running loop without fallback behavior and is the recommended API.

### Breaking Changes
None.

### Next Steps
None.

---

## [2026-03-14 14:03] - BUGFIX: Log cache parse failures in query service instead of swallowing

### Changes
- Replaced bare `except Exception: pass` in `query_service.py` (cache-hit path and streaming cache-hit path) with DEBUG-level logging. On cache deserialization/parse failure, the exception and full traceback are now logged via `logger.opt(exception=True).debug(...)` before falling through to the full pipeline.

### Files Modified
- `backend/app/services/query_service.py`

### Rationale
Silently passing on exceptions hid cache deserialization and validation issues; logging at DEBUG aids troubleshooting while keeping fallback behaviour unchanged.

### Breaking Changes
None.

### Next Steps
None.

---

## [2026-03-14 14:04] - BUGFIX: Vector search over-fetch so post-filtering returns up to top_k

### Changes
- **Neo4j vector search:** `vector_search_entities` and `vector_search_communities` now over-fetch from the index (`fetch_k = min(500, top_k * 2)`) then apply `WHERE user_id` / `WHERE derived_user_id` and `LIMIT top_k`. Previously, requesting top_k and then filtering by user could return fewer than top_k results when multiple users share the same Neo4j DB.
- **Cap:** Added `_VECTOR_SEARCH_FETCH_MAX = 500` to avoid unbounded over-fetching.
- **Docstrings:** Both methods document the over-fetch behaviour for multi-tenant DBs.

### Files Modified
- `backend/app/services/neo4j_service.py`

### Rationale
Post-filtering by user_id after vector retrieval can yield sparse results; over-fetching then limiting ensures callers receive up to top_k results when data exists for the user.

### Breaking Changes
None. Return shape and semantics unchanged; results may now be fuller when multiple users share the DB.

### Next Steps
None.

---

## [2026-03-14 14:05] - REFACTOR: Align chat message roles (user | assistant) with frontend

### Changes
- **Backend:** `ChatMessage.role` in `app/schemas/query.py` now uses `Literal["user", "assistant"]` instead of `"human" | "ai"`, aligned with the frontend `ChatSection` interface. Redis-stored history and all new writes use `"user"` and `"assistant"`. When reading from Redis, the query service accepts both legacy `"human"`/`"ai"` and `"user"`/`"assistant"` for backward compatibility.
- **Docstring:** `ChatMessage` documents that role values are aligned with the frontend so chat history can be shared or exposed via API without mapping.

### Files Modified
- `backend/app/schemas/query.py` (Literal type, docstring)
- `backend/app/services/query_service.py` (write "user"/"assistant", read "human"/"user" and "ai"/"assistant")
- `README.md` (CHAT_HISTORY_WINDOW note)
- `DEVELOPMENT.md`

### Rationale
Frontend uses "user" | "assistant"; backend previously used "human" | "ai". Aligning on "user" | "assistant" avoids mismatch when chat history is shared or exposed to the frontend and keeps a single vocabulary across the stack.

### Breaking Changes
None. Existing Redis entries with "human"/"ai" are still read correctly; new entries use "user"/"assistant".

### Next Steps
None.

---

## [2026-03-14] - FEATURE: Chatbot token and speed optimizations

### Changes
- **History windowing:** Added `CHAT_HISTORY_WINDOW` (default 6). Only the last N conversation turns are sent to the synthesis LLM. When saving to Redis, human turns store only the bare question (not the full context block). Legacy history entries with "Context:... Question: ..." are stripped to the question part when loaded for token savings.
- **Summary cap:** Added `QUERY_MAX_SUMMARY_CHARS` (default 800). Community summaries in synthesis context are truncated to this length before being sent to the LLM.
- **Answer cache:** Added `QUERY_ANSWER_CACHE_TTL` (default 3600) and Redis cache key `query:answer:{user_id}:{question_hash}`. Identical questions return the cached response and skip the full pipeline; the Q&A is still appended to chat history.
- **Streaming:** Synthesis step now supports streaming. `POST /api/query` accepts `stream: true` in the body; response is `text/event-stream` with SSE events: `{ "content": "..." }` per token chunk, then `{ "done": true, "answer", "mode_used", "session_id", "sources" }`. Non-streaming behavior unchanged when `stream` is omitted or false.
- **Frontend:** ChatSection uses streaming by default: sends `stream: true`, consumes the SSE response, and appends tokens to the assistant message as they arrive. Shows "Thinking…" in the assistant bubble until the first token.

### Files Modified
- `backend/app/core/config.py` (CHAT_HISTORY_WINDOW, QUERY_MAX_SUMMARY_CHARS, QUERY_ANSWER_CACHE_TTL)
- `backend/app/core/cache.py` (cache_key_query_answer)
- `backend/app/services/query_service.py` (_human_content_to_question, history trim, summary truncation, answer cache, run_query_pipeline_stream)
- `backend/app/api/v1/endpoints/query.py` (stream query param, StreamingResponse)
- `backend/app/schemas/query.py` (stream field on QueryRequest)
- `frontend-next/src/components/chat/ChatSection.tsx` (streaming fetch, SSE parsing, incremental message update)
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Chat felt slow due to unbounded history and large context. Windowing and summary truncation cut token usage; streaming improves perceived latency; answer cache makes repeated questions instant.

### Breaking Changes
None. Existing clients that do not send `stream: true` receive the same JSON response as before.

### Next Steps
If the project uses `.env.example`, add the new variables: `CHAT_HISTORY_WINDOW`, `QUERY_MAX_SUMMARY_CHARS`, `QUERY_ANSWER_CACHE_TTL`.

---

## [2026-03-13] - FEATURE: GraphRAG Query Pipeline (chat with your brain)

### Changes
- **Backend:** Implemented full 4-stage GraphRAG query pipeline: (1) Intent Router (LLM classifies query as global/local/hybrid), (2) Retrieval via Neo4j vector search on `entity_embedding_idx` and `community_summary_embedding_idx` plus 1-hop entity neighborhood, (3) Context pruning (score threshold, deduplication), (4) LLM synthesis with conversation history. Conversation history is stored in Redis per user/session and loaded each request for multi-turn answers.
- **Neo4j:** Added `vector_search_entities`, `vector_search_communities`, and `get_entity_neighborhood` to `neo4j_service.py`.
- **API:** New `POST /api/query` endpoint; request body `question`, optional `mode` (auto|global|local|hybrid), optional `session_id`; response includes `answer`, `mode_used`, `session_id`, `sources` (community/entity attribution).
- **Prompts:** Added `query_router.json` (few-shot intent classifier) and `query_synthesis.json` (answer + cite sources).
- **Config:** Added `QUERY_ROUTER_MODEL`, `QUERY_SYNTHESIS_MODEL`, `QUERY_ENTITY_TOP_K`, `QUERY_COMMUNITY_TOP_K`, `QUERY_SIMILARITY_THRESHOLD`, `CHAT_HISTORY_TTL_SECONDS`.
- **Frontend:** Wired `ChatSection` to `queryBrain()` API; messages state, loading indicator, session ID in localStorage, message bubbles and source attribution pills below assistant replies. Dashboard passes `token` to `ChatSection`.
- **Cache:** Added `cache_key_chat_history(user_id, session_id)` and Redis persistence for chat history.

### Files Modified
- `backend/app/schemas/query.py` (new)
- `backend/app/services/neo4j_service.py`
- `backend/app/services/query_service.py` (new)
- `backend/app/api/v1/endpoints/query.py` (new)
- `backend/app/core/config.py`
- `backend/app/core/cache.py`
- `backend/app/main.py`
- `backend/app/prompts/query_router.json` (new)
- `backend/app/prompts/query_synthesis.json` (new)
- `frontend-next/src/lib/api.ts` (queryBrain, QueryResponse, SourceAttribution, QueryMode)
- `frontend-next/src/components/chat/ChatSection.tsx`
- `frontend-next/src/app/dashboard/page.tsx`
- `backend/requirements.txt` (added `langchain-core>=0.3.0` for query service)
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Users need to ask questions against their knowledge graph and get answers grounded in community summaries and entity triplets, with conversation context and source attribution. The router avoids over-fetching (e.g. global questions use only community summaries).

### Breaking Changes
None. New endpoint and optional frontend token prop.

### Next Steps
Optional: add tests for query pipeline and `POST /api/query` endpoint. `langchain-core` was added to `backend/requirements.txt` for `InMemoryChatMessageHistory` and message types used by the query service.

---

## [2026-03-13 16:20] - DOCS: Clarify email verification endpoints

### Changes
- Updated `README.md` auth endpoint list to explicitly document `GET /api/auth/verify-email?token=...` usage and clarify that there is **no** `POST /api/auth/verify-email` route; resend is handled via `POST /api/auth/resend-verification` with `{ email }`.

### Files Modified
- `README.md`
- `DEVELOPMENT.md`

### Rationale
The backend implements email verification via a tokenized GET link; calling this out directly prevents confusion with a nonexistent POST verification endpoint and makes the verification flow easier to follow.

### Breaking Changes
None.

### Next Steps
None.

## [2026-03-13 16:00] - BUGFIX: Prevent stale refresh from resurrecting session

### Changes
- Updated Next.js `AuthContext` refresh scheduling and session restoration to use a session generation guard so in-flight `refreshToken()` / `getMe()` calls cannot re-set auth state after `logout()` clears the timer and state.
- Updated `logout()` to propagate `api.logout()` failures instead of swallowing them, while still clearing local auth state.

### Files Modified
- `frontend-next/src/contexts/AuthContext.tsx`

### Rationale
Clearing a refresh timeout does not cancel an already-running async refresh chain; without a guard, a stale refresh could complete after logout and rehydrate the in-memory token/user. Surfacing logout errors allows callers/UI to handle cases where server-side session cookies may remain valid.i

### Breaking Changes
None.

### Next Steps
None.

## [2026-03-13] - BUGFIX: Clear verification resend target on login reset

### Changes
- In the Next.js login form, whenever the verification flow is cleared (e.g. on a new sign-in attempt), the stored resend target email is now also cleared so the **Resend** action cannot reuse a stale address.

### Files Modified
- `frontend-next/src/components/auth/LoginForm.tsx`

### Rationale
Previously, `handleResend()` used the last value of `verifyEmail`; if the verification UI was hidden and later re-shown, the resend could incorrectly target a previous email. Clearing `verifyEmail` alongside the verification state prevents this.

### Breaking Changes
None.

### Next Steps
None.

## [2026-03-13] - BUGFIX: Avoid account-state disclosure in resend-verification

### Changes
- `POST /api/auth/resend-verification`: When the user does not exist or the email is already verified, the endpoint now returns the same generic message: "If an account exists for this email, a verification link was sent."
- Removed the distinct "This email is already verified. You can sign in." response, which leaked account existence/state to unauthenticated callers.

### Files Modified
- `backend/app/api/v1/endpoints/auth.py`

### Rationale
Returning "already verified" only for existing users reveals that an account exists and is verified; attackers can use this to enumerate valid emails and their verification status. A single generic response for both "no user" and "already verified" prevents this information disclosure.

### Breaking Changes
None (UX: users with already-verified emails see the same message as unknown emails; behavior is intentionally opaque).

### Next Steps
None.

## [2026-03-13 14:10] - REFACTOR: Offload verification email sending to background tasks

### Changes
- Updated `POST /api/auth/register` and `POST /api/auth/resend-verification` to schedule `send_verification_email(...)` using FastAPI `BackgroundTasks` instead of awaiting SMTP work in-request.
- Preserved existing logging; registration now marks `email_sent = True` immediately after scheduling.

### Files Modified
- `backend/app/api/v1/endpoints/auth.py`
- `README.md`

### Rationale
SMTP can be slow/blocking; moving email sending to background tasks keeps registration/resend endpoints responsive and avoids tying up request workers.

### Breaking Changes
- Email delivery failures are no longer surfaced synchronously (e.g., resend no longer fails the request due to SMTP errors during the request); failures will appear in backend logs.

### Next Steps
- If you need reliable delivery/guaranteed retries, consider moving to a real job queue (Celery/RQ) with persistent retry semantics.

## [2026-03-13] - REFACTOR: Auth endpoint return type annotations

### Changes
- Added explicit return type annotations to all auth endpoint handlers in `backend/app/api/v1/endpoints/auth.py`: `register` → `MessageResponse`, `login` → `JSONResponse`, `refresh` → `JSONResponse`, `logout` → `JSONResponse`, `verify_email` → `MessageResponse`, `resend_verification` → `MessageResponse`, `get_current_user_info` → `UserResponse`, `verify_token` → `dict[str, Any]`.
- Added `from typing import Any` for the `verify_token` return type.

### Files Modified
- `backend/app/api/v1/endpoints/auth.py`

### Rationale
Satisfies backend typing rule; annotations match the actual returned values and improve static analysis and IDE support.

### Breaking Changes
None.

### Next Steps
None.

## [2026-03-12] - BUGFIX: MailHog verification emails not received

### Changes
- **Email service:** For SMTP port 1025 (MailHog), force plain TCP: `MAIL_STARTTLS=False`, `MAIL_SSL_TLS=False`, `VALIDATE_CERTS=False` so fastapi-mail does not attempt TLS or cert validation.
- **Email service:** Pass empty string for `MAIL_USERNAME`/`MAIL_PASSWORD` when unset (fastapi-mail `ConnectionConfig` requires string, not None).
- **Config:** Default `SMTP_FROM` changed from `noreply@shipoftheseus.local` to `noreply@example.com`; `.local` is rejected by fastapi-mail's email validator.
- **Docker Compose:** Backend env sets `SMTP_FROM=noreply@example.com` so MailHog sends with a valid From address.
- **Auth endpoint:** Log verification-email failure reason in the warning message and call `logger.exception()` so the real error appears in logs when send fails.
- **Docker Compose:** Backend now `depends_on: mailhog` (service_started) so MailHog is up before the backend starts.

### Files Modified
- `backend/app/services/email_service.py`
- `backend/app/api/v1/endpoints/auth.py`
- `docker-compose.yml`

### Rationale
Verification emails were failing with no message in MailHog; backend logged "Verification email send failed; user created" but the actual exception was only in structured `extra` (not shown when DEBUG=False). With port 1025 we must disable TLS and cert validation for MailHog. Improved logging ensures the next failure shows the real error.

### Breaking Changes
None.

### Next Steps
If emails still fail after rebuild, check backend logs for the exception message and traceback.

## [2026-03-11 00:00] - FEATURE: Email verification + refresh-token auth

### Changes
- **Backend auth:** Registration now sends an email verification link and new accounts must verify before signing in.
- **Session UX:** Added refresh token flow using **httpOnly cookies** so users don’t get logged out mid-session when the access token expires.
- **New endpoints:** `/api/auth/refresh`, `/api/auth/logout`, `/api/auth/verify-email`, `/api/auth/resend-verification`.
- **Frontend auth:** Access token is kept in memory; the app performs a silent refresh on load and periodically refreshes the access token.
- **Dev email inbox:** Added MailHog to Docker Compose (UI at `http://localhost:8025`).

### Files Modified
- `backend/app/models/user.py`
- `backend/app/db/init_db.py`
- `backend/app/core/security.py`
- `backend/app/core/config.py`
- `backend/app/schemas/auth.py`
- `backend/app/services/user_service.py`
- `backend/app/services/email_service.py` (new)
- `backend/app/api/v1/endpoints/auth.py`
- `backend/requirements.txt`
- `docker-compose.yml`
- `frontend-next/src/contexts/AuthContext.tsx`
- `frontend-next/src/lib/api.ts`
- `frontend-next/src/components/auth/RegisterForm.tsx`
- `frontend-next/src/components/auth/LoginForm.tsx`
- `frontend-next/src/app/verify-email/page.tsx` (new)
- `README.md`
- `.env.example` (new)

### Rationale
The previous design used a single JWT stored in `localStorage` that expired during active use and exposed the token to XSS. Email verification improves account security and reduces spam/sign-up abuse. Refresh-token cookies improve UX and security by keeping access tokens short-lived and off persistent storage.

### Breaking Changes
- `POST /api/auth/register` now returns a message and requires email verification before login succeeds.
- Frontend no longer persists tokens in `localStorage`; sessions are restored via refresh cookie.

### Next Steps
- Consider adding CSRF protection if you introduce cross-site cookie usage (current cookie is `SameSite=Lax`).

## [2026-03-11] - BUGFIX: 403 on POST /api/graph/save/{job_id}

### Changes
- In `save_graph_to_neo4j`, the cache lookup for the extraction job now uses `neo4j_user_id` (`str(current_user.id)`) when calling `_get_graph_from_cache`, instead of `cache_user_id` (email or username). Entity and relationship jobs are stored in Redis with `user_id = str(current_user.id)`, so the authorization check inside `_get_graph_from_cache` was failing (403) when comparing the cached job's `user_id` to email/username.

### Files Modified
- `backend/app/api/v1/endpoints/graph.py`

### Rationale
The extraction flow stores jobs with `user_id = str(current_user.id)`. The graph save endpoint was passing `current_user.email or current_user.username` to `_get_graph_from_cache`, so `entity_job.get("user_id") != user_id` was always true, resulting in 403 Forbidden when clicking "Add to Brain" after extraction completed.

### Breaking Changes
None.

### Next Steps
None.

## [2026-03-11] - BUGFIX: Neo4j schema notifications and GET /community/brain 404

### Changes
- **Neo4j:** Disabled `UNRECOGNIZED` notification classification when creating the Neo4j driver so that schema-hint warnings (missing property/label/relationship type) are not sent when the database is empty or schema does not yet exist. Uses `notifications_disabled_classifications=[neo4j.NotificationClassification.UNRECOGNIZED]` when the driver supports it.
- **Community brain:** `GET /api/community/brain` now returns **200** with an empty `UserBrain` (zeros, `status="empty"`) when the user has no graph in Neo4j, instead of 404. This allows the frontend to show an onboarding/empty state without treating the response as an error.

### Files Modified
- `backend/app/services/neo4j_service.py`
- `backend/app/api/v1/endpoints/community.py`

### Rationale
Neo4j 5.x sends notifications for every query that references labels, relationship types, or properties not yet present in the DB, which filled logs with "missing property name: user_id/document_name/id/type" and "missing label: Entity/Community/Brain" / "missing relationship type: RELATES". Disabling UNRECOGNIZED at the driver level suppresses these while keeping real errors. Returning 200 with an empty brain for new users avoids 404s on the dashboard and lets the UI distinguish "no data yet" from "endpoint not found".

### Breaking Changes
None. GET /community/brain response shape is unchanged; only the "no graph" case now returns 200 with empty brain instead of 404.

### Next Steps
None.

## [2026-03-10 13:00] - BUGFIX: Avoid Caching Failed Relationship Extractions

### Changes
- Updated per-chunk relationship extraction in `entities.py` so that an empty cached relationship list is now treated as a valid cache hit by checking `cached_rels is not None` and reconstructing `rels = [Relationship(**r) for r in cached_rels]`.
- Wrapped `rel_extractor.extract_relationship_list_async` with a success flag and now only call `cache_set(rel_cache_key, ...)` when extraction completes without raising, avoiding writes of empty lists that originate from exception paths.

### Files Modified
- `backend/app/api/v1/endpoints/entities.py`
- `DEVELOPMENT.md`

### Rationale
Previously, failed relationship extraction attempts were serialized and cached as empty lists, causing subsequent retries for the same chunk + entity-list combination to return empty relationships immediately from cache. Treating `None` as the only cache-miss sentinel and gating cache writes on successful LLM calls ensures failures do not poison the relationship cache while still allowing downstream code to safely handle empty relationship lists when they are the result of genuine extractions.

### Breaking Changes
None. Cache semantics are stricter for failures but API shapes and job status behavior are unchanged.

### Next Steps
Optional: add targeted tests around relationship caching to verify that failed extractions are not cached, empty lists from genuine extractions are, and corrupted cache entries trigger recomputation.

## [2026-03-10 13:30] - BUGFIX: Use Stable UUID for Extraction and Document Caches

### Changes
- Updated entity extraction and relationship extraction endpoints in `entities.py` to derive `user_id` from the stable PostgreSQL UUID (`str(current_user.id)`) instead of mutable identifiers like email or username when building job payloads, validating ownership, and constructing per-chunk cache keys.
- Updated document upload, retrieval, and deletion endpoints in `documents.py` to store and look up the current document in Redis using the same stable UUID-based `user_id`, keeping the upload and extraction flows consistent.
- Clarified in `README.md` that document management and entity extraction caches are now scoped by the authenticated user's UUID rather than email/username.

### Files Modified
- `backend/app/api/v1/endpoints/entities.py`
- `backend/app/api/v1/endpoints/documents.py`
- `README.md`

### Rationale
Using email or username as the cache/user identifier meant that changing either field could orphan in-flight extraction jobs, per-chunk caches, and uploaded documents because their keys no longer matched the authenticated user's identity. Switching to the stable UUID (`str(current_user.id)`) keeps cache keys and job payload `user_id` fields consistent even if a user later updates their email or username.

### Breaking Changes
- Existing Redis entries keyed by email/username will no longer be visible under the new UUID-based scheme; running jobs and cached chunks created before this change will effectively be treated as expired/missing. New uploads and extractions will use the stable UUID going forward.

### Next Steps
- (Optional) Add a short-lived migration script to scan for active email/username-based extraction/document keys and rewrite them to UUID-based keys for currently-logged-in users, if preserving in-flight jobs across the transition is important.

## [2026-03-10 12:30] - BUGFIX: Do Not Cache Failed Entity Extractions

### Changes
- Updated per-chunk entity extraction in `entities.py` so that when `extractor.extract_entities_async` raises an exception, the fallback empty `ExtractedEntities` object is still used for downstream processing but is **not** written into the chunk-hash cache.
- Added a success flag around the extraction call and now only invoke `cache_set(ent_cache_key, ...)` when the LLM extraction completes without raising.

### Files Modified
- `backend/app/api/v1/endpoints/entities.py`
- `DEVELOPMENT.md`

### Rationale
Previously, transient LLM failures during entity extraction resulted in an empty `ExtractedEntities` object that was also cached under the chunk hash, causing subsequent retries on identical content to immediately return an empty result from cache and masking successful extractions. Gating cache writes on successful LLM responses ensures that only good results are cached while still allowing the job to progress with empty entities when necessary.

### Breaking Changes
None. Cache behavior is stricter for failures but the API shape and job status semantics are unchanged.

### Next Steps
Optional: add targeted tests around chunk-hash caching to verify that failed extractions are not cached and successful retries populate the cache as expected.

## [2026-03-10 11:00] - BUGFIX/SECURITY: Prevent Demoting Last Admin

### Changes
- Added `get_admin_count` helper in `admin_service` to count active admin users.
- Updated `PATCH /api/admin/users/{user_id}/toggle-admin` endpoint to prevent demoting the last remaining admin user while still allowing promotions and demotions when more than one admin exists.
- Left authentication/authorization behavior unchanged: the endpoint continues to require an authenticated admin via `get_admin_user`.

### Files Modified
- `backend/app/services/admin_service.py`
- `backend/app/api/v1/endpoints/admin.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Demoting the final admin user would leave the system without any administrative accounts, making recovery difficult and potentially requiring direct database intervention. Counting active admins before demotion and blocking the operation when only one remains enforces a safe invariant at the API layer.

### Breaking Changes
None. Existing admin toggling workflows continue to work as long as at least two admins exist when demoting one of them.

### Next Steps
- Optionally expose the total admin count in the admin UI and surface a clearer error message when attempting to demote the last admin.

---

## [2026-03-13 10:00] - FEATURE

### Changes
- Added an admin-only backend endpoint to permanently delete a user and all of their associated GraphRAG data (Neo4j graphs, community brain) and cached documents.
- Extended the Next.js admin portal user table with a **Delete** action that prompts for confirmation and calls the new backend endpoint, preventing deletion of your own account and the last remaining admin.
- Updated API documentation in `README.md` to describe the new admin delete-user capability.

### Files Modified
- `backend/app/api/v1/endpoints/admin.py`
- `frontend-next/src/app/admin/page.tsx`
- `README.md`

### Rationale
Provide admins with a clear, one-click way to fully remove a user and their knowledge brain, including underlying Neo4j and cache data, while protecting against accidental removal of the last admin or self-deletion from the portal.

### Breaking Changes
None

### Next Steps
- Consider adding an audit log entry model to record who deleted which user and when, and surface it in the admin portal for compliance.

---

## [2026-03-10 10:15] - BUGFIX/SECURITY: Scope Neo4j documents per user

### Changes
- Scoped Neo4j document listing, retrieval, and deletion to the authenticated user (`user_id = PostgreSQL user UUID`) so users only see their own uploaded/saved documents.
- Updated Neo4j service methods to support optional user scoping while keeping admin/global stats behavior unchanged.

### Files Modified
- `backend/app/services/neo4j_service.py`
- `backend/app/api/v1/endpoints/graph.py`
- `README.md`

### Rationale
The dashboard document list was global because `/api/graph/list` and related endpoints queried Neo4j without filtering by user. This is a privacy issue in multi-user deployments.

### Breaking Changes
- Users will no longer see other users' documents.
- If you have older Neo4j graphs created without a `user_id` property, they will no longer appear in the per-user list until re-saved/reprocessed (or migrated).

### Next Steps
- (Optional) Add a one-off migration script to backfill `user_id` for legacy Neo4j data if needed.

## [2026-03-10 00:00] - FEATURE/PERF: Faster community summarization + better upload UX

### Changes
- **Backend:** Implemented async community summarization per hierarchy level using `chain.ainvoke()` + `asyncio.gather()` (replacing thread-pool blocking calls). Pipeline status now emits `community_progress` during summarization so the UI can show per-community completion counts. Batched Neo4j writes for community assignments, community nodes, and entity embeddings using `UNWIND` to remove N+1 query patterns.
- **Frontend (Next.js):** Upload pipeline polling now consumes `community_progress` to drive the progress bar and shows an `X/Y` badge on the active **Summaries** step. Pipeline polling is slightly more responsive (faster retry on initial 404, quicker polls on non-LLM steps).
- **Docs:** Updated README with the new pipeline status response field and added the `COMMUNITY_SUMMARIZATION_CONCURRENCY` tuning knob.

### Files Modified
- `backend/app/services/summarization_service.py`
- `backend/app/services/brain_pipeline_service.py`
- `backend/app/api/v1/endpoints/graph.py`
- `backend/app/services/neo4j_service.py`
- `frontend-next/src/hooks/useUpload.ts`
- `frontend-next/src/components/upload/ProcessingSteps.tsx`
- `README.md`

### Rationale
The upload-to-brain flow felt stalled during long community summarization. Async I/O concurrency plus granular progress updates makes the pipeline finish faster and provides visible feedback while it runs.

### Breaking Changes
None. The pipeline status endpoint adds an optional `community_progress` field during summarization; existing clients can ignore it.

### Next Steps
- If you see OpenAI rate-limit errors during summarization, tune `COMMUNITY_SUMMARIZATION_CONCURRENCY` down.

---

## [2026-03-10 00:00] - PERF: Faster entity + relationship extraction (streaming + caching)

### Changes
- **Backend:** Increased default extraction parallelism and added retry/backoff for transient LLM failures. Implemented *streamed extraction*: relationship extraction starts per chunk as soon as that chunk’s entities finish (no need to wait for the full entity pass). Added chunk-hash caching for entities and for relationships (keyed by chunk hash + entity-list hash) to speed up retries on identical documents/chunks. Added configurable document chunking (`DOCUMENT_CHUNK_SIZE`, `DOCUMENT_CHUNK_OVERLAP`).
- **Frontend (Next.js):** Relationship extraction step now shows true progress by polling the relationship status endpoint while waiting for the final graph.
- **Config/Docs:** Added `.env.example` template and documented new env vars in README.

### Files Modified
- `backend/app/core/config.py`
- `backend/app/core/cache.py`
- `backend/app/api/v1/endpoints/documents.py`
- `backend/app/api/v1/endpoints/entities.py`
- `backend/app/services/entity_extraction_service.py`
- `backend/app/services/relationship_extraction_service.py`
- `frontend-next/src/hooks/useUpload.ts`
- `README.md`
- `DEVELOPMENT.md`

### Files Created
- `.env.example`

### Rationale
Extraction latency was dominated by two sequential LLM passes across chunks. Streaming overlaps the passes and caching avoids redoing identical work, improving time-to-preview while preserving extraction quality constraints (relationships remain constrained to extracted entities).

### Breaking Changes
None. Defaults changed (higher batch sizes / concurrency); env vars allow tuning down if needed.

### Next Steps
- If you see frequent 429s, reduce `ENTITY_EXTRACTION_CONCURRENCY` / `RELATIONSHIP_EXTRACTION_CONCURRENCY`.\n+
## [2026-03-10] - FEATURE: Admin portal

### Changes
- **Backend:** Added `is_admin` to User model (PostgreSQL) and UserResponse schema; migration in `init_db.py` to add column to existing tables. New `get_admin_user` dependency (403 if not admin). New admin schemas: `PlatformStats`, `UserAdminView`, `ServiceHealth`, `SystemHealth`. New `admin_service`: `get_platform_stats`, `get_all_users`, `get_system_health` (PostgreSQL/Neo4j/Redis health + global Neo4j counts). New `Neo4jService.get_global_counts()` for entity/edge/community/document counts. New admin router: `GET /api/admin/stats`, `GET /api/admin/users` (paginated), `GET /api/admin/system`, `PATCH /api/admin/users/{user_id}/toggle-admin`. Added `get_user_by_id` to user_service.
- **Frontend:** New `/admin` page: platform stats cards (users, documents, entities, relationships, communities, avg docs per user), system health badges (PostgreSQL, Neo4j, Redis), users table with promote/demote admin. Admin link in dashboard header when `user.is_admin`. New admin API helpers in `api.ts`: `getAdminStats`, `getAdminUsers`, `getSystemHealth`, `toggleUserAdmin`; extended `UserResponse` with `is_admin`.

### Files Modified
- `backend/app/models/user.py` – added `is_admin`
- `backend/app/schemas/auth.py` – added `is_admin` to UserResponse
- `backend/app/db/init_db.py` – ALTER TABLE for `is_admin` on existing DBs
- `backend/app/api/v1/deps.py` – added `get_admin_user`
- `backend/app/services/user_service.py` – added `get_user_by_id`
- `backend/app/services/neo4j_service.py` – added `get_global_counts`
- `backend/app/main.py` – registered admin router
- `frontend-next/src/lib/api.ts` – UserResponse `is_admin`, admin API types and functions
- `frontend-next/src/app/dashboard/page.tsx` – conditional Admin link for admins
- `README.md` – admin feature, structure, API endpoints
- `DEVELOPMENT.md` – this entry

### Files Created
- `backend/app/schemas/admin.py`
- `backend/app/services/admin_service.py`
- `backend/app/api/v1/endpoints/admin.py`
- `frontend-next/src/app/admin/page.tsx`

### Rationale
Provide a dedicated admin UI to view system information, document and user analytics, service health, and to manage admin status (promote/demote users). First admin must be set via DB (`UPDATE users SET is_admin = true WHERE username = '...'`); thereafter admins can use the portal.

### Breaking Changes
None. New optional `is_admin` field; existing users default to `false`.

### Next Steps
- Optional: add total user count to admin users response for pagination total.

---

## [2026-03-10 00:00] - BUGFIX

### Changes
- Switched Neo4j per-user scoping to use the user's PostgreSQL UUID (`str(current_user.id)`) for graph saves and community/brain operations, ensuring admin per-user document counts match how data is stored.
- Kept pipeline-job authorization checks using the cached user identifier (email/username) so existing client polling remains consistent.

### Files Modified
- `backend/app/api/v1/endpoints/graph.py`
- `backend/app/api/v1/endpoints/community.py`
- `README.md`

### Rationale
UUID is the stable identifier for a user; emails/usernames can change. Using UUID consistently prevents per-user stats and brain reads from returning 0 due to identifier mismatch.

### Breaking Changes
- Existing Neo4j nodes created with email/username-based `user_id` will not be counted under the UUID-based scheme until re-saved/reprocessed or migrated.

### Next Steps
- Add a one-time Neo4j migration script (optional) to rewrite legacy `user_id` values to UUIDs.

## [2026-03-10] - FEATURE: List users API

### Changes
- Added `list_users(db)` in `user_service.py` to return all users ordered by `created_at` descending.
- Added `GET /auth/users` endpoint in `auth.py` returning a list of `UserResponse` (id, username, email, is_active, created_at); requires JWT authentication.

### Files Modified
- `backend/app/services/user_service.py`
- `backend/app/api/v1/endpoints/auth.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Allow authenticated clients to retrieve the list of all users in the database via a GET request.

### Breaking Changes
None.

### Next Steps
None.

---

## [2026-03-13 07:40] - BUGFIX

### Changes
- Normalised the `ServiceStorageStats.status` field description in the admin schemas to use an ASCII hyphen-minus in the explanatory suffix, avoiding mixed Unicode dash characters in API documentation.

### Files Modified
- `backend/app/schemas/admin.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Mixed Unicode dash characters in status descriptions can cause subtle inconsistencies between code, documentation, and logs; standardising on the ASCII hyphen-minus keeps admin health and infra status strings consistent and easier to search for.

### Breaking Changes
None.

### Next Steps
None.

---

## [2026-03-09] - FEATURE: GraphRAG Brain Pipeline

### Changes
- **Entity Identity Card:** Entity extraction now includes a `description` per entity (from surrounding text). Schemas: `Person`, `Organization` and new `LocationEntity`, `KeyTermEntity` (replacing bare `List[str]`) have optional `description`. Prompt `entity_extraction.json` instructs the LLM to produce 1–2 sentence descriptions. Relationship service passes descriptions into `GraphNode.properties` and builds entity list from rich objects.
- **Hierarchical community detection:** Three-level Louvain: leaf (entity graph) → mid (meta-graph of leaf clusters) → root (meta-graph of mid clusters). New `detect_hierarchical_communities()` and `_build_meta_graph` / `_build_meta_graph_for_mids` in `community_detection_service`. `build_user_brain(..., hierarchical=True)` returns `(brain, flat_for_neo4j, hierarchical_raw)`.
- **LLM summarization:** New `SummarizationService` and prompt `community_summary.json`; generates a report per community at every level (leaf/mid/root), with optional child-summary synthesis for mid/root.
- **Vectorization:** New `EmbeddingService` using `text-embedding-3-small` (config: `EMBEDDING_MODEL`). Entity embed text = Identity Card (label + description); community embed text = LLM summary. Batch embedding with configurable batch size.
- **Neo4j extensions:** All entity nodes get `:Entity` label at save. New vector indexes: `entity_embedding_idx` (Entity.embedding), `community_summary_embedding_idx` (Community.embedding). New methods: `ensure_vector_indexes()`, `save_community_nodes()`, `save_entity_embeddings()`. Brain node stores `communities_by_level_json`; `get_brain_node` returns `communities_by_level`. `delete_user_data` deletes `:Community` nodes.
- **Schemas:** `CommunityLevel` enum (leaf/mid/root), `HierarchicalCommunity` (level, parent_community_id, summary, embedding), `UserBrain.communities_by_level` optional.
- **API:** `POST /community/detect` runs full pipeline (hierarchical → summarize → embed → save community nodes + entity embeddings → save brain with `communities_by_level`). `GET /community/brain` returns enriched brain when available. Graph save background task and GET fallback use `flat_for_neo4j` for leaf-only community assignments.

### Files Modified
- `backend/app/schemas/entities.py` – description + LocationEntity, KeyTermEntity
- `backend/app/prompts/entity_extraction.json` – Identity Card instruction
- `backend/app/services/relationship_extraction_service.py` – _build_entity_list / _build_graph for rich locations/key_terms and description
- `backend/app/schemas/community.py` – CommunityLevel, HierarchicalCommunity, UserBrain.communities_by_level
- `backend/app/prompts/community_summary.json` – new
- `backend/app/services/summarization_service.py` – new
- `backend/app/services/embedding_service.py` – new
- `backend/app/services/community_detection_service.py` – hierarchical detection, _community_metadata, _build_meta_graph*, build_user_brain return shape
- `backend/app/services/neo4j_service.py` – :Entity label, vector indexes, save_community_nodes, save_entity_embeddings, brain communities_by_level, delete Community nodes
- `backend/app/core/config.py` – EMBEDDING_MODEL, COMMUNITY_SUMMARIZATION_MODEL
- `backend/app/api/v1/endpoints/community.py` – full pipeline in POST /detect, _nodes_and_edges_for_community
- `backend/app/api/v1/endpoints/graph.py` – build_user_brain unpack three values, use flat_for_neo4j
- `backend/requirements.txt` – openai>=1.35.0
- `README.md` – GraphRAG description, env vars, API and project structure
- `DEVELOPMENT.md` – this entry

### Rationale
Implement the planned GraphRAG pipeline: hierarchical structure (Leaf → Mid → Root), per-community LLM summaries, and vectorization (entity + summary embeddings) in Neo4j for local/global search. Entity descriptions (Identity Cards) improve embedding quality.

### Breaking Changes
- Entity extraction response shape: `locations` and `key_terms` are now lists of `{name, description}` objects instead of lists of strings. Frontends that consume extraction results must use `.name` (and optionally `.description`).
- `build_user_brain` now returns a 3-tuple `(brain, flat_for_neo4j, hierarchical_raw)`; callers must unpack three values and use the second for `save_community_assignments`.

### Next Steps
- Wire query phase: expose search over entity and community summary vector indexes (e.g. `/api/search` or similar) for "Ask your brain" and RAG retrieval.

---

## [2026-03-09 12:00] - BUGFIX

### Changes
- Offloaded blocking Neo4j and GraphRAG pipeline work to background threads when running the full brain pipeline, so that async endpoints and background tasks no longer block the main event loop.

### Files Modified
- `backend/app/services/brain_pipeline_service.py`
- `backend/app/api/v1/endpoints/graph.py`

### Rationale
Ensure that long-running community detection, summarization, embedding, and Neo4j persistence run in worker threads via `run_in_executor`, improving FastAPI/Starlette concurrency behavior for both the manual pipeline trigger and the background pipeline launched from graph saves.

### Breaking Changes
None. Pipeline semantics and API responses are unchanged; only execution strategy and threading behavior were updated.

### Next Steps
- Consider similarly offloading other synchronous Neo4j calls made directly from async endpoints (e.g., document save/list operations) if they become bottlenecks under load.


## [2026-03-09] - FEATURE: Pipeline Preview & Dual Visualization

### Changes
- Extended the **graph save pipeline** so that `POST /api/graph/save/{job_id}` now triggers the **full GraphRAG pipeline** (community detection → summarization → embedding) in a FastAPI background task, instead of just community detection.
- Added Redis-backed **pipeline job tracking** via `cache_key_pipeline_job(pipeline_job_id)`; each pipeline step writes status snapshots (`status`, `step`, `step_index`, `total_steps`, `message`, `error?`) under `pipeline:job:{id}` with a 1-hour TTL.
- Implemented `_background_full_pipeline(pipeline_job_id, user_id, neo4j)` in `graph.py`, which:
  - Loads the user's graph from Neo4j and runs `build_user_brain(..., hierarchical=True)` to compute communities.
  - Summarizes communities at leaf/mid/root using `SummarizationService` and `COMMUNITY_SUMMARIZATION_MODEL`.
  - Embeds entities and community summaries with `EmbeddingService` and `EMBEDDING_MODEL`, saving entity embeddings and `:Community` nodes back to Neo4j.
  - Persists an enriched `Brain` node with `communities_by_level` and warms the `community:brain:{user_id}` cache.
- Added `GET /api/graph/pipeline/status/{pipeline_job_id}` endpoint to expose pipeline status to the frontend (with per-user authorization).
- Updated the Next.js **upload pipeline** (`useUpload` hook) to:
  - Introduce new processing states: `saving_graph`, `detecting_communities`, `summarizing`, `embedding`, and `preview`.
  - Automatically call `/api/graph/save/{job_id}` as soon as extraction + relationship building finish, then poll `/api/graph/pipeline/status/{pipeline_job_id}` until the pipeline reports `done`.
  - When the pipeline completes, reload the document graph from Neo4j so nodes include `community_id` assignments, and switch the UI to a **preview** state.
- Replaced the single upload progress bar with a **multi-stage stepper** (`ProcessingSteps`) that visualizes the full pipeline (Upload → Entities → Relationships → Saving → Communities → Summaries → Embeddings), showing the active stage, completed stages, and a compact progress bar.
- Updated the PDF upload card (`PdfUpload`) so that:
  - The graph is saved and the brain pipeline is triggered automatically; the user no longer has to click a separate \"Add to Knowledge Base\" button.
  - After the pipeline completes, the user sees a **preview** of the processed document graph (with entity/relationship counts and communities when available) and can choose to \"Add to Brain\" (refreshing the brain metrics/graph) or upload another document.
- Added `DocumentGraphView`, a reusable **single-document graph visualizer** (force-directed 2D graph) that:
  - Renders nodes and edges for one `DocumentGraph`.
  - Colors nodes by `community_id` when community information is available.
  - Shows filename and basic stats (entity/relationship counts) in an overlay.
- Extended the dashboard center panel to a **dual visualization**:
  - Added a simple toggle between **\"Document graph\"** and **\"Brain graph\"**.
  - Wired `DocumentList` so selecting a document loads its graph from Neo4j and shows it in the `DocumentGraphView` tab.
  - Kept the existing `BrainSection` for the merged brain view in the \"Brain graph\" tab.

### Files Modified
- `backend/app/core/cache.py` – added `cache_key_pipeline_job(pipeline_job_id)` and documented its purpose.
- `backend/app/api/v1/endpoints/graph.py` – replaced `_background_community_detection` with `_background_full_pipeline`; added `_nodes_and_edges_for_community`, `BRAIN_CACHE_TTL`, `PIPELINE_JOB_TTL`, `_set_pipeline_status`; updated `POST /graph/save/{job_id}` to return `pipeline_job_id` and to launch the full pipeline; added `GET /graph/pipeline/status/{pipeline_job_id}`.
- `frontend-next/src/hooks/useUpload.ts` – extended `ProcessingState`, tracked `pipelineJobId` and `documentName`, auto-saved graphs to Neo4j once extraction completes, polled the new pipeline status endpoint, and reloaded the document graph from Neo4j before entering the `preview` state.
- `frontend-next/src/components/upload/ProcessingSteps.tsx` – rewrote as a multi-stage stepper with per-stage badges, active-stage indicator, and optional progress bar and counts.
- `frontend-next/src/components/upload/PdfUpload.tsx` – integrated the new processing states, switched to a `preview` state (instead of `done`) after the pipeline, and updated actions to \"Add to Brain\" and \"Upload another\".
- `frontend-next/src/components/upload/DocumentGraphView.tsx` – new component for single-document graph visualization with optional community coloring and stats overlay.
- `frontend-next/src/components/documents/DocumentList.tsx` – added `onSelect` callback and `selectedDocumentName` highlighting for active document selection.
- `frontend-next/src/app/dashboard/page.tsx` – added document/brain center toggle, loaded selected document graphs via `getGraphFromNeo4j`, and wired `DocumentGraphView` and `BrainSection` into the two-center views.
- `README.md` – documented the new background pipeline behavior, pipeline status endpoint, and dual visualization (per-document graph + merged brain).

### Rationale
Give users clear visibility into the **entire indexing pipeline** (from upload through community detection, summarization, and embeddings), ensure that **community extraction and embeddings complete before suggesting the graph is merged into the brain**, and provide two distinct visualization surfaces: one for **individual document graphs** and one for the **overall knowledge brain** that aggregates all documents.

### Breaking Changes
- `POST /api/graph/save/{job_id}` now always triggers the **full** GraphRAG pipeline (community detection + summarization + embedding) in the background instead of only community detection. The response now includes a `pipeline_job_id` used by the frontend for progress polling.
- Frontend upload flow changed: saving to Neo4j is automatic after extraction, and the \"Add to Knowledge Base\" button has been replaced by a **preview and confirm** step that assumes the backend save + pipeline have already run.

### Next Steps
- Feed the per-document and brain-level graphs into the chat experience so that \"Ask your brain\" queries can reference both the current document graph and the merged knowledge brain.
- Optionally expose finer-grained pipeline metrics (e.g., chunk-level progress for summarization/embedding) through the pipeline status endpoint for even richer UI feedback.

---

## [2026-03-09] - BUGFIX: Clear Brain Resets Document List

### Changes
- Updated the frontend **Knowledge Brain** section so that using the “Clear brain — start from scratch” action fully resets the dashboard state for the current user.
- Extended `BrainSection` props to accept an optional `onBrainCleared` callback, and added a `handleClearBrain` handler that:
  - Calls `useBrain.remove()` (which hits `DELETE /api/community/brain` and `neo4j.delete_user_data(user_id)`).
  - Clears local brain-related UI state (`graphData`, highlighted community, open community panel).
  - Invokes `onBrainCleared` so the parent layout can reset its own state.
- In the dashboard page, wired `onBrainCleared` to:
  - Clear the **document list** (`documents` state).
  - Clear the **selected document** and its graph (`selectedDocument`, `selectedDocumentGraph`).
  - This makes the left sidebar and center document-graph view immediately reflect that all user graphs have been removed.

### Files Modified
- `frontend-next/src/components/brain/BrainSection.tsx` – added `onBrainCleared` prop, `handleClearBrain` function, and local state reset when brain is cleared.
- `frontend-next/src/app/dashboard/page.tsx` – passed `onBrainCleared` to `BrainSection` and, when invoked, cleared `documents`, `selectedDocument`, and `selectedDocumentGraph`.

### Rationale
When a user chooses to **clear the brain**, they expect *all* of their graph data to be gone, including the list of uploaded documents and any per-document graphs. Previously, the backend correctly deleted user data from Neo4j, but the frontend document list state was not refreshed, so old document entries remained visible until a manual reload. The fix keeps the UI consistent with the backend’s “start from scratch” semantics.

### Breaking Changes
None. The new `onBrainCleared` prop on `BrainSection` is optional and existing usages continue to work unchanged.

### Next Steps
- Optionally show a brief confirmation toast after clearing the brain to reassure users that all documents and graphs were removed.

---

## [2026-03-09] - BUGFIX / CONFIG

### Changes
- **No passwords in docker-compose**: Removed all default password/user/db values from compose (e.g. `:-postgres`, `:-shipoftheseus`). PostgreSQL and Neo4j now use only `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, `${POSTGRES_DB}`, `${NEO4J_USER}`, `${NEO4J_PASSWORD}` from `.env`; the compose files contain no literal secrets.
- **Redis connection in Docker**: Backend was connecting to `localhost:6379` (from `.env`), which inside the container is unreachable. Overrode `REDIS_URL` for the backend service to `redis://redis:6379/0` so the app uses the Redis service name.
- **Neo4j connection in Docker**: Overrode `NEO4J_URI` for the backend service to `bolt://neo4j:7687` so `/api/community/brain` and other Neo4j-dependent endpoints work (fixes 503 when Neo4j was unreachable at localhost from inside the container).
- Postgres healthcheck now uses container env vars `$POSTGRES_USER` and `$POSTGRES_DB` instead of literal defaults in the compose file.

### Files Modified
- `docker-compose.yml` – backend env overrides (REDIS_URL, NEO4J_URI), postgres/neo4j env without defaults, healthcheck
- `docker-compose.prod.yml` – same for backend and postgres
- `README.md` – env docs updated for Docker overrides and no-passwords-in-compose

### Rationale
User requested no passwords in docker-compose; logs showed Redis connection refused and 503 on community/brain due to backend using localhost for Redis and Neo4j inside Docker.

### Breaking Changes
- Compose **requires** a `.env` file with `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `NEO4J_USER`, and `NEO4J_PASSWORD` set. If any are missing, startup may fail or use empty values.

---

## [2025-03-09] - BUGFIX

### Changes
- Fixed backend failing at startup in Docker with `ConnectionRefusedError` when connecting to PostgreSQL.
- Cause: inside the backend container, `DATABASE_URL` (from `.env` or default) used host `localhost`, which points to the container itself, not the Postgres service.
- Overrode `DATABASE_URL` in both `docker-compose.yml` and `docker-compose.prod.yml` for the backend service so it uses host `postgres` (Docker service name) and the same credentials as the postgres container.

### Files Modified
- `docker-compose.yml` – added `environment.DATABASE_URL` for backend service
- `docker-compose.prod.yml` – added `environment.DATABASE_URL` for backend service

### Rationale
Compose already had `depends_on: postgres: condition: service_healthy`, so Postgres was up; the backend was connecting to the wrong host. Setting `DATABASE_URL` in the service environment ensures the app always uses the `postgres` host when run via Compose.

### Breaking Changes
None.

---

## [2026-03-09 17:00] - REFACTOR

### Changes
- Parallelized LLM community summarization within each hierarchy level using `ThreadPoolExecutor`
- Added `SummarizationService.summarize_level()` method that fans out all communities at a given level concurrently (up to 10 threads by default, capped to the community count)
- Level ordering (leaf → mid → root) is preserved: each level waits for the previous to complete before starting, since mid/root summaries depend on child summaries
- Each worker thread creates its own `SummarizationService` instance to avoid lazy LLM client init races
- Replaced the sequential loop in `graph.py` (`_background_full_pipeline`) with calls to `summarize_level`
- Replaced the sequential loop in `community.py` (`trigger_community_detection`) with calls to `summarize_level`
- Removed the now-unused `_nodes_and_edges_for_community` helper from both endpoint files

### Files Modified
- `backend/app/services/summarization_service.py`
- `backend/app/api/v1/endpoints/graph.py`
- `backend/app/api/v1/endpoints/community.py`

### Rationale
With 35 leaf communities (as seen in logs), sequential summarization was taking ~7–8 minutes just for the leaf level. Parallelizing within each level reduces wall-clock time by up to 10× (default pool size), while still respecting the leaf → mid → root dependency ordering.

### Breaking Changes
None.

---

## [2026-03-09] - BUGFIX: Processing Steps Preview State

### Changes
- Fixed the frontend upload processing stepper so that when the pipeline finishes and the state transitions to `preview` or `done`, all seven pipeline stages are rendered as completed instead of appearing pending/gray while the progress bar shows 100%.
- Adjusted the `ProcessingSteps` component to treat `preview` and `done` as a terminal, fully-completed position in the stage sequence even though they are not explicit entries in the `STAGES` array.
- Documented the corrected behavior in the main `README.md` under Frontend UX notes.

### Files Modified
- `frontend-next/src/components/upload/ProcessingSteps.tsx`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Ensure visual consistency between the detailed stepper and the numeric progress bar so that users clearly see a fully completed pipeline when entering the preview/done state, avoiding confusion caused by all stages appearing inactive.

### Breaking Changes
None.

### Next Steps
- Consider a subtle completion state (e.g., no active ping) for the final step when in `preview` or `done` to further distinguish \"in progress\" from \"finished\" pipelines.

---

## [2026-03-09] - REFACTOR: Shared GraphRAG Brain Pipeline Service

### Changes
- Extracted the full GraphRAG brain pipeline (hierarchical community detection, summarization loop, entity and summary embedding, community node persistence, Brain node persistence, and cache warming) into a shared service module `brain_pipeline_service`.
- Updated `POST /api/community/detect` (`trigger_community_detection`) to call `run_full_brain_pipeline_for_user`, removing its inlined copy of the pipeline logic.
- Updated the background pipeline task in `graph.py` (`_background_full_pipeline`) to delegate to `detect_communities_and_assign`, `summarize_hierarchy`, `embed_and_persist_brain`, and `warm_brain_cache`, keeping only pipeline job status tracking and error handling in the endpoint layer.
- Introduced a `NoUserGraphError` exception to represent the \"no nodes in Neo4j for this user\" case, reused by both the manual trigger endpoint and the background task.

### Files Modified
- `backend/app/services/brain_pipeline_service.py` (new)
- `backend/app/api/v1/endpoints/community.py`
- `backend/app/api/v1/endpoints/graph.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Remove nearly identical copies of the GraphRAG pipeline from `community.py` and `graph.py` so that future behavior changes (e.g., new stages, updated summarization/embedding strategy, or different cache semantics) are implemented in a single place, reducing the risk of subtle divergences between code paths.

### Breaking Changes
None. Public API shapes and pipeline semantics are unchanged; only internal wiring has been consolidated.

### Next Steps
- Consider exposing finer-grained instrumentation hooks in `brain_pipeline_service` (e.g., timing per stage) for more detailed pipeline monitoring and metrics.

---

## [2026-03-09 18:15] - BUGFIX: Redis Cache Fallback Uses In-Memory Store

### Changes
- Updated `cache_get` so that it only returns immediately when Redis returns a non-`None` value, and otherwise falls through to the in-memory cache fallback.
- Kept the `try/except` around `redis.get(key)` and now only clears the Redis client on actual exceptions, not on simple cache misses.

### Files Modified
- `backend/app/core/cache.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Ensure that the documented in-memory cache fallback is actually used when Redis is configured but a key is missing or Redis temporarily fails, instead of returning `None` and masking available values in the in-memory store.

### Breaking Changes
None. Callers already handle `None` for missing keys; the only behavior change is that existing values in the in-memory cache are now visible when Redis misses or is unavailable.

### Next Steps
- Consider adding targeted tests around cache behavior (Redis hit, Redis miss with in-memory hit, Redis failure) to prevent regressions.

---

## [2026-03-09 18:25] - BUGFIX: Consistent CORS Default Origins

### Changes
- Introduced a shared `DEFAULT_ALLOWED_ORIGINS` constant (`["http://localhost:3000", "http://127.0.0.1:3000"]`) in `config.py`.
- Updated `_parse_origins` to use `DEFAULT_ALLOWED_ORIGINS` whenever the `ALLOWED_ORIGINS` value is empty or whitespace, so empty-string environment values behave the same as the unset/default case.
- Set the `ALLOWED_ORIGINS` setting default to `",".join(DEFAULT_ALLOWED_ORIGINS)` to keep the class default in sync with the parser’s fallback.
- Updated the README environment variable documentation so the documented default for `ALLOWED_ORIGINS` matches the actual setting.

### Files Modified
- `backend/app/core/config.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Ensure CORS behavior is predictable and consistent regardless of whether `ALLOWED_ORIGINS` is unset or explicitly set to an empty string, and keep documentation aligned with the effective defaults to avoid confusion.

### Breaking Changes
None. The change only broadens the default CORS allowlist for the empty-string case to match the already-documented and implemented multi-origin default.

### Next Steps
- Optionally add small configuration tests to assert that `_parse_origins("")` and `_parse_origins(Settings().ALLOWED_ORIGINS)` return the same list of default origins.

---

## [2026-03-09 19:00] - BUGFIX: Neo4j Vector Index Dimensions Track EMBEDDING_MODEL

### Changes
- Removed the hardcoded `VECTOR_DIMENSIONS = 1536` constant from the Neo4j service and updated `ensure_vector_indexes` to derive the vector dimension at runtime based on the active `EMBEDDING_MODEL`.
- Introduced a private `_get_vector_dimensions()` helper on `Neo4jService` that first consults a model→dimension map for known OpenAI embedding models, then falls back to probing the `EmbeddingService` for the actual embedding size when the model is unknown, caching the result.
- Extended `EmbeddingService` with a `get_embedding_dimension()` method that performs a single probe embedding and caches the resulting vector length for reuse.
- Documented in `README.md` that Neo4j vector index dimensions are now derived from `EMBEDDING_MODEL` at runtime so index configuration stays aligned with the configured embedding model.

### Files Modified
- `backend/app/services/embedding_service.py`
- `backend/app/services/neo4j_service.py`
- `README.md`

### Rationale
Ensure that Neo4j vector index configuration always matches the currently configured embedding model, avoiding subtle bugs when switching from the default `text-embedding-3-small` to a different model with a different vector dimension.

### Breaking Changes
None. Existing behavior for the default `text-embedding-3-small` model remains the same; additional models are now supported more safely.

### Next Steps
- Extend the model→dimension map as new embedding models are adopted and, optionally, add tests to assert that vector index dimensions match the actual embedding size returned by `EmbeddingService`.

---

## [2026-03-09 19:30] - BUGFIX: Separate Derived Community Nodes from Source User Graph

### Changes
- Updated Neo4j community persistence so `save_community_nodes` no longer writes `user_id` onto `:Community` nodes or uses it in the MERGE key.
- Introduced a `derived_user_id` property on `:Community` nodes and changed the MERGE pattern to use `{community_id, derived_user_id}` while still keeping `community_id` in the key.
- Adjusted `delete_user_data` to delete `:Community` nodes by `derived_user_id`, ensuring per-user cleanup still removes derived community nodes.
- Documented the separation between source user graph nodes (keyed by `user_id`) and derived `:Community` nodes (keyed by `community_id` + `derived_user_id`) in the main README.

### Files Modified
- `backend/app/services/neo4j_service.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Prevent derived `:Community` nodes written by the GraphRAG pipeline from being re-read as part of the per-user source graph returned by `get_user_graph`, while still allowing complete deletion of a user's derived communities via `delete_user_data`.

### Breaking Changes
None for API consumers. Existing `:Community` nodes that still carry `user_id` will continue to be removed by the generic `MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n` query; newly written communities no longer carry `user_id` and are instead deleted via `derived_user_id`.

### Next Steps
- If additional Neo4j queries are added that read `:Community` nodes directly, ensure they filter by `derived_user_id` rather than `user_id` when scoping to a user.

---

## [2026-03-09 19:45] - BUGFIX: Scope Entity Embeddings by Document

### Changes
- Updated `Neo4jService.save_entity_embeddings` to require a `document_name` argument and to match target nodes by `user_id`, `document_name`, and `id`, preventing embeddings from being written to all nodes that share the same `id` across different documents.
- Changed `embed_and_persist_brain` in the brain pipeline to group nodes by `document_name`, embedding entities per document and calling `save_entity_embeddings(user_id, document_name, embeddings_map)` for each group.
- Documented that entity embeddings are now written to nodes scoped by `(user_id, document_name, id)` so entities with the same id in different documents remain isolated.

### Files Modified
- `backend/app/services/neo4j_service.py`
- `backend/app/services/brain_pipeline_service.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Ensure that entity embeddings are applied only to the intended document-scoped nodes, aligning with the rest of the graph layer which treats node ids as unique per document (indexed by `(document_name, id)`), and avoiding cross-document contamination when ids collide.

### Breaking Changes
None for external APIs. Internal callers of `save_entity_embeddings` must now provide `document_name`, and the only caller (`embed_and_persist_brain`) has been updated accordingly.

### Next Steps
- If future features need to embed entities outside the full brain pipeline, ensure they either supply `document_name` or perform their own per-document grouping before calling `save_entity_embeddings`.

---

## [2026-03-09] - BUGFIX: Align Frontend Save Response Type with Pipeline Job ID

### Changes
- Updated the `useUpload` hook so that the response from `saveGraphToNeo4j` is typed with a dedicated `SaveGraphToNeo4jResponse` shape that includes `ok`, `document_name`, `pipeline_job_id`, and `message`.
- Replaced the previous `as any` cast used to access `pipeline_job_id` with a strongly typed cast to `SaveGraphToNeo4jResponse`, making the expected API response contract explicit in the upload pipeline.

### Files Modified
- `frontend-next/src/hooks/useUpload.ts`

### Rationale
The backend `POST /graph/save/{job_id}` endpoint returns `{ ok, message, document_name, pipeline_job_id }`, but the frontend helper was only typed to expose `ok` and `document_name`, forcing the upload flow to use an unsafe `as any` cast to access `pipeline_job_id`. Introducing an explicit response type clarifies the expected shape at the call site and removes the untyped cast in the main upload pipeline.

### Breaking Changes
None. The runtime behavior is unchanged; only TypeScript typing at the upload pipeline call site has been strengthened.

### Next Steps
- Consider updating the shared frontend API client typings so that `saveGraphToNeo4j` itself advertises the full response shape (including `pipeline_job_id` and `message`) without needing a local cast in the hook.

---

## [2026-03-09] - BUGFIX: Make Pipeline Status Poll Robust to Initial 404

### Changes
- Updated the `pollPipeline` logic in the upload hook so that a 404 from `GET /api/graph/pipeline/status/{pipeline_job_id}` is treated as a transient condition (likely due to the background job not yet having written status to cache) and simply triggers another poll after `POLL_INTERVAL_MS`, instead of immediately setting the state to `"error"`.
- Kept hard failures (non-404 HTTP errors and network failures) as terminal errors while still honoring the overall `TIMEOUT_MS` guard to avoid polling indefinitely.

### Files Modified
- `frontend-next/src/hooks/useUpload.ts`

### Rationale
Right after `saveGraphToNeo4j` returns a `pipeline_job_id`, the background task may not have written its first status snapshot to Redis yet, causing the first status request to return 404. The previous implementation treated any non-OK response as a terminal error, leading the UI to show a failed pipeline even though the job was starting normally. Retrying on 404 aligns the polling behavior with the entity extraction and relationship graph polling, which already tolerate transient unavailability via retries.

### Breaking Changes
None. The user-visible behavior is improved (fewer spurious errors), and the API contract is unchanged.

### Next Steps
- Optionally add a dedicated "waiting for pipeline to start…" progress message for the initial 404 phase to make the status clearer in the UI.

---

## [2026-03-09] - PERF: Use Set Membership in Mid-Level Meta-Graph

### Changes
- Optimized `_build_meta_graph_for_mids` so that leaf community membership checks use precomputed `set` objects (`leaf_sets`) instead of scanning `leaf_partition[li]` lists, reducing each membership test from O(n) to O(1).
- Kept the existing meta-graph construction logic (iterating over edges and mid partitions) but swapped list lookups for set lookups to avoid O(E × N) behavior when many edges connect large leaf communities.

### Files Modified
- `backend/app/services/community_detection_service.py`

### Rationale
The mid-level meta-graph builder was checking `src in leaf_partition[li]` and `tgt in leaf_partition[li]` where `leaf_partition[li]` is a list of node ids, making each membership test O(n) and turning the overall complexity into O(E × N) for dense graphs. The sibling `_build_meta_graph` function already converts partitions to sets for O(1) membership; aligning `_build_meta_graph_for_mids` with the same pattern improves performance on larger graphs without changing behavior.

### Breaking Changes
None. The meta-graph structure and downstream community detection behavior are unchanged; only the internal data structure used for membership checks has been optimized.

### Next Steps
- If mid-level graphs grow further, consider precomputing a direct node→mid index map to completely avoid scanning mid partitions for each edge.

---

## [2026-03-09] - REFACTOR: Remove Redundant Brain Delete in Neo4j User Cleanup

### Changes
- Simplified `delete_user_data` so it no longer issues a separate `MATCH (b:Brain {user_id: $user_id}) DETACH DELETE b` query, relying instead on the existing `MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n` to remove the user's `:Brain` node along with all other user-scoped nodes.
- Kept the explicit `MATCH (c:Community {derived_user_id: $user_id}) DETACH DELETE c` query, since derived `:Community` nodes are keyed by `derived_user_id` and do not carry `user_id`.

### Files Modified
- `backend/app/services/neo4j_service.py`

### Rationale
After introducing `derived_user_id` on `:Community` nodes and removing their `user_id` property, the generic `MATCH (n) WHERE n.user_id = $user_id` still correctly deletes all per-user source graph nodes and the `:Brain` node, but no longer reaches derived communities. The subsequent `MATCH (b:Brain {user_id: $user_id})` therefore became redundant and would always match zero nodes immediately after the first query. Removing it avoids an unnecessary Cypher round trip during user-data cleanup while preserving correct deletion of both source and derived data.

### Breaking Changes
None. User data deletion semantics are unchanged; only an internal redundant query has been removed.

### Next Steps
- Optionally add a small test around `delete_user_data` to assert that entity nodes, relationships, `:Community` nodes (by `derived_user_id`), and the `:Brain` node are all removed for a user.

---

## [2026-03-09] - REFACTOR: Fingerprint-Aware Brain Embedding Pipeline

### Changes
- Updated `embed_and_persist_brain` to compute a stable SHA-256 fingerprint for each entity's Identity Card text and only call `EmbeddingService.embed_entities` for entities whose stored `embedding_fingerprint` differs from the newly computed value.
- Extended `Neo4jService.save_entity_embeddings` to accept an optional `fingerprint_map` and persist `embedding_fingerprint` alongside each entity embedding, scoped by `(user_id, document_name, id)`.
- Added `Neo4jService.get_community_embeddings_and_fingerprints` and updated the brain pipeline to compute a SHA-256 fingerprint of each community summary, reuse existing embeddings when the stored `summary_fingerprint` matches, and only re-embed changed summaries before persisting via `save_community_nodes`.
- Updated `save_community_nodes` so `:Community` nodes now store a `summary_fingerprint` property in addition to `embedding`, enabling idempotent re-runs of the pipeline without redundant OpenAI embedding calls.

### Files Modified
- `backend/app/services/brain_pipeline_service.py`
- `backend/app/services/neo4j_service.py`
- `README.md`

### Rationale
Re-running the GraphRAG brain pipeline on the same underlying graph was re-embedding every entity and community summary on each save, incurring unnecessary OpenAI usage and latency. By introducing content-based fingerprints on both entity Identity Cards and community summaries, the pipeline can now detect when a node's semantic content is unchanged and skip re-embedding while still keeping Neo4j and the Brain node up to date for changed items only.

### Breaking Changes
None. Existing data remains valid; nodes without `embedding_fingerprint` or `summary_fingerprint` are treated as needing an initial embedding on the next pipeline run, after which subsequent runs become incremental.

### Next Steps
- Add tests around the incremental behavior (e.g. verifying that re-running the pipeline without content changes does not call the embedding service for unchanged entities/communities).

---

## [2026-03-09] - BUGFIX: Only Persist Complete Brain in /community/brain Fallback

### Changes
- Updated `GET /community/brain` fallback logic so that when no Brain node exists yet, it now calls `run_full_brain_pipeline_for_user` instead of directly invoking `build_user_brain` and immediately persisting a partial brain without summaries/embeddings.
- Removed the direct `neo4j.save_community_assignments` and `neo4j.save_brain_node` calls from the fallback path; persistence is now handled exclusively by the shared brain pipeline, ensuring only a fully built brain (with summaries and embeddings) is written.

### Files Modified
- `backend/app/api/v1/endpoints/community.py`

### Rationale
Previously, the fallback path for `GET /community/brain` would compute only community detection (via `build_user_brain` with `hierarchical=True`), persist community assignments, and save a Brain node lacking `communities_by_level`, summaries, and embeddings. This diverged from the behavior of the explicit `/community/detect` pipeline and could leave Neo4j with an incomplete brain representation. By delegating the fallback to the shared full pipeline, the endpoint now guarantees that any persisted brain is complete and consistent.

### Breaking Changes
None. The endpoint contract remains the same; the fallback path now runs the full GraphRAG pipeline instead of persisting a partial brain, which is a correctness and quality improvement.

### Next Steps
- Add tests exercising the `GET /community/brain` fallback to verify that it invokes the full pipeline and only persists complete brains.

---

## [2026-03-09 20:15] - BUGFIX: Add to Brain Resets Upload Preview

### Changes
- Updated the **PdfUpload** component so that clicking **Add to Brain** now refreshes the brain metrics/graph via the dashboard callback and then calls the upload hook’s `reset()` method, returning the upload panel to the idle state instead of leaving it stuck in `preview`.
- Added a lightweight loading state and error message handling around the **Add to Brain** action so users see when the brain refresh is in progress or has failed.
- Documented in the main README that saving to Neo4j happens automatically during processing and that **Add to Brain** is a UI refresh + completion action.

### Files Modified
- `frontend-next/src/components/upload/PdfUpload.tsx`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Ensure that, after the background save + brain pipeline complete, the **Add to Brain** button actually behaves like a completion step: it refreshes the dashboard’s brain view and then returns the upload flow to the idle state, rather than keeping the user indefinitely in a `preview` state that still shows "Add to Brain" as if saving had not yet occurred.

### Breaking Changes
None. The backend API and upload pipeline semantics are unchanged; only the frontend behavior of the preview card and button wiring has been refined.

### Next Steps
- Optionally show a small toast or inline success message when the **Add to Brain** action completes to make the refresh more explicit to users.

---

## [2026-03-09 20:30] - BUGFIX: Cache Delete Clears In-Memory Fallback

### Changes
- Updated `cache_delete` so that it no longer returns early after a successful Redis `DEL` and instead always clears the corresponding key from the in-memory fallback store under the same lock.
- Ensures that keys deleted from Redis cannot "reappear" via a stale in-memory entry when `cache_get` falls back to memory after a Redis miss, keeping the two tiers consistent.

### Files Modified
- `backend/app/core/cache.py`

### Rationale
Previously, if data had been written to the in-memory cache during a Redis outage and later only removed from Redis once Redis recovered, a subsequent `cache_get` would miss in Redis and then return the stale in-memory value, effectively resurrecting deleted data. Clearing both Redis and the in-memory store on delete aligns behavior with the expected semantics of a full cache invalidation.

### Breaking Changes
None. Callers already treat deletes as best-effort invalidation; the only change is that the in-memory fallback now respects deletions performed while Redis is available.

### Next Steps
- Add focused tests around `cache_delete` to cover scenarios where values exist in only Redis, only memory, or both, and verify that deletes correctly invalidate all tiers.

---

## [2026-03-09 20:40] - BUGFIX: Allow build_user_brain Hierarchical Flag in run_in_executor

### Changes
- Relaxed the `build_user_brain` signature so that the `hierarchical` flag is no longer keyword-only and can be passed positionally.
- This aligns with the existing usage in `brain_pipeline_service`, where `loop.run_in_executor` invokes `build_user_brain` with positional arguments (ending in `True` for the `hierarchical` flag).

### Files Modified
- `backend/app/services/community_detection_service.py`

### Rationale
`loop.run_in_executor` calls the target function as `func(*args)`, which cannot satisfy keyword-only parameters. With `hierarchical` declared after a `*`, passing `True` as the fifth positional argument would raise a `TypeError` at runtime, breaking both the manual `/community/detect` pipeline (`run_full_brain_pipeline_for_user`) and the background pipeline launched from `/graph/save/{job_id}`. Making `hierarchical` positional-or-keyword preserves the intended semantics while matching how the function is actually invoked.

### Breaking Changes
None. Any existing callers that pass `hierarchical` by keyword continue to work, and the previously failing positional usage via `run_in_executor` is now valid.

### Next Steps
- Add a small test case around `run_full_brain_pipeline_for_user` to ensure the pipeline runs end-to-end without `TypeError` and to catch regressions if the signature changes again.

---

## [2026-03-09 21:15] - BUGFIX: Restore Manual Add to Brain Save

### Changes
- Updated the Next.js upload flow so that the `useUpload` hook no longer saves the extracted document graph to Neo4j and starts the GraphRAG pipeline automatically as soon as extraction finishes.
- Adjusted `useUpload` to stop after relationship extraction with a `preview` state that exposes the extracted `DocumentGraph` and a simple "preview ready" progress message, allowing the user to review the graph before committing it.
- Added an `addToBrain` action to `useUpload` that, when called, saves the graph to Neo4j via `POST /api/graph/save/{job_id}`, starts the full brain pipeline, and polls `/api/graph/pipeline/status/{pipeline_job_id}` until completion, updating processing states (`saving_graph`, `detecting_communities`, `summarizing`, `embedding`, `done`) along the way.
- Wired the PDF upload card's **Add to Brain** button to call `addToBrain`, then invoke the dashboard's `onSaveComplete` callback and reset the upload hook back to `idle`, so the button once again performs the actual save instead of only refreshing the brain view.
- Updated `README.md` to describe the revised behavior: users see a per-document preview after extraction, and **Add to Brain** both saves to Neo4j and runs the GraphRAG pipeline.

### Files Modified
- `frontend-next/src/hooks/useUpload.ts`
- `frontend-next/src/components/upload/PdfUpload.tsx`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Users reported that the upload flow was saving graphs to the knowledge base and triggering the expensive brain pipeline without any confirmation, while the **Add to Brain** button only refreshed the dashboard, making the label misleading and removing the opportunity to review extracted graphs before committing them. The new flow restores an explicit confirmation step and aligns the button label with its behavior.

### Breaking Changes
- Frontend behavior change: saving to Neo4j is no longer automatic at the end of extraction; users must click **Add to Brain** from the preview state to persist the graph and run the brain pipeline. Backend APIs are unchanged.

### Next Steps
- Consider adding a lightweight inline message or toast when the brain pipeline completes successfully after **Add to Brain**, and optionally surface more detailed pipeline progress in the dashboard when a document is being added.

---

## [2026-03-09 21:25] - BUGFIX: Clamp Pipeline Step Progress at Zero

### Changes
- Updated the upload pipeline status polling in the Next.js `useUpload` hook so that the computed `completed` value passed to `setProgress` is clamped with `Math.max(0, status.step_index - 1)`, preventing negative progress when `step_index` is 0.

### Files Modified
- `frontend-next/src/hooks/useUpload.ts`

### Rationale
Ensure the multi-stage processing stepper never shows a negative completed-step count during brief initial phases of the GraphRAG pipeline status polling, keeping the progress UI numerically consistent.

### Breaking Changes
- None. This is a visual correctness fix; pipeline behavior and API contracts are unchanged.

---

## [2026-03-09 21:40] - REFACTOR: Centralize GraphRAG Pipeline Orchestration

### Changes
- Updated `run_full_brain_pipeline_for_user` in `brain_pipeline_service` to become the single orchestrator of the three-stage GraphRAG pipeline (detect → summarize → embed/persist/cache), with an optional async `on_step` callback for progress reporting.
- Refactored the `_background_full_pipeline` task in the `graph` endpoint to delegate the actual pipeline work to `run_full_brain_pipeline_for_user` instead of manually reimplementing the sequence, while keeping the pipeline job status updates in Redis for UI polling.
- Ensured that `/api/community/detect` and the background job triggered by `/api/graph/save/{job_id}` both use the same shared pipeline implementation, eliminating drift risk between synchronous and background code paths.

### Files Modified
- `backend/app/services/brain_pipeline_service.py`
- `backend/app/api/v1/endpoints/graph.py`
- `DEVELOPMENT.md`

### Rationale
Previously, the background pipeline launched from `/graph/save/{job_id}` duplicated the orchestration logic that already existed in `brain_pipeline_service`, directly calling `detect_communities_and_assign`, `summarize_hierarchy`, and `embed_and_persist_brain`. This violated the intended design documented in the README ("implemented once in a shared service and reused by both code paths") and created a maintenance hazard where any future change to the pipeline steps needed to be applied in two places. Centralizing orchestration in `run_full_brain_pipeline_for_user` keeps behavior consistent while still allowing the background job to surface fine-grained progress updates.

### Breaking Changes
- None. The external API contracts and pipeline step semantics are unchanged; only internal wiring was refactored to remove duplication.

### Next Steps
- Add a small backend test that invokes `run_full_brain_pipeline_for_user` directly and via the background task to ensure both paths stay in sync and to catch regressions where the pipeline stages or step labels change.

---

## [2026-03-09 22:05] - BUGFIX: Prevent Stale Error Guard in addToBrain Hook

### Changes
- Fixed the `addToBrain` callback in the Next.js upload hook so it no longer reads the `error` state from a stale closure when deciding whether to overwrite an existing error message.
- Introduced a local `hasExplicitPipelineError` flag within `useUpload`'s `addToBrain` implementation to track whether the pipeline polling logic has already set a specific error; the outer catch block now only sets `state`, `error`, and `progress` if no explicit pipeline error was recorded.

### Files Modified
- `frontend-next/src/hooks/useUpload.ts`
- `DEVELOPMENT.md`

### Rationale
The previous implementation used `if (!error)` in the `catch` block of `addToBrain` while omitting `error` from the `useCallback` dependency array. This meant the guard captured whatever `error` was when the callback was first memoized (typically `null`), so it would happily overwrite more specific error messages set during pipeline polling. Using an explicit boolean flag avoids reliance on React state for this guard and ensures the most informative error message is preserved for the user.

### Breaking Changes
- None. The public hook API is unchanged; only internal error-handling semantics were corrected to avoid stale closures.

### Next Steps
- Consider adding a small unit or integration test around the `useUpload` hook to assert that pipeline errors surfaced during status polling are not overwritten by the outer catch block in `addToBrain`.

---

## [2026-03-09 22:30] - BUGFIX: Prevent Stale Graph After Add to Brain Reset

### Changes
- Fixed the upload hook’s `addToBrain` pipeline completion logic so that the enriched document graph is fetched from Neo4j and applied via `setGraph` **before** the promise resolves, instead of using a fire-and-forget async IIFE.
- Ensured that callers like `PdfUpload.handleAddToBrain` (which `await` `addToBrain()` and then call `reset()`) no longer risk having `reset()` clear the graph and then have a late async update re-apply a stale graph while the hook is back in the `idle` state.

### Files Modified
- `frontend-next/src/hooks/useUpload.ts`
- `README.md`

### Rationale
`addToBrain` previously resolved as soon as the backend pipeline reported `done`, while a detached async function fetched the enriched graph and called `setGraph` later. The `PdfUpload` component immediately called `reset()` after `await addToBrain()`, clearing `graph` to `null`; when the detached fetch later completed, it could overwrite the cleared state with a stale graph even though the upload panel had already returned to `idle`. Awaiting the enrichment fetch inside `addToBrain` removes this race.

### Breaking Changes
- None. The public hook API and user-facing behavior of the upload flow are unchanged; the internal timing of when `graph` is updated relative to `reset()` is now consistent.

### Next Steps
- Consider adding a small hook test to assert that `graph` is not mutated after `reset()` is called following a successful `addToBrain` invocation.

---

## [2026-03-09 22:45] - BUGFIX: Show Status Message Before First Brain Pipeline Poll

### Changes
- Updated the Next.js `ProcessingSteps` component to synthesize a minimal `ProcessingProgress` object when the upload state is one of the long-running brain pipeline stages (`saving_graph`, `detecting_communities`, `summarizing`, `embedding`) but the `progress` prop is still `null`, so the UI shows a contextual status message instead of an empty "Processing pipeline" header with a 0% bar and no text.
- Derived fallback messages from the current state (for example, "Saving graph to knowledge base…", "Starting brain pipeline…", "Summarizing communities…", "Embedding entities and summaries…") to match the semantics of the underlying pipeline while avoiding a flash of blank UI before the first status poll lands.

### Files Modified
- `frontend-next/src/components/upload/ProcessingSteps.tsx`
- `README.md`

### Rationale
Previously, if the processing state had advanced into the brain pipeline but no status snapshot had been received yet, the processing stepper rendered with the correct active stage but no descriptive text and an effectively 0% progress bar, which felt broken or stalled. Providing deterministic fallback messages for these states ensures users always see meaningful feedback, even in the brief window before the first `/graph/pipeline/status/{pipeline_job_id}` response populates real progress.

### Breaking Changes
- None. The hook and API contracts are unchanged; only the display behavior of `ProcessingSteps` has been improved for the null-progress case.
 
---

## [2026-03-09 23:05] - BUGFIX: Do Not Mark Brain Steps Complete in Preview

### Changes
- Updated the `ProcessingSteps` component so that when the upload flow is in the `preview` state (graph extracted but not yet saved to the brain), only the upload and extraction stages (Upload → Entities → Relationships) are marked as completed, and the downstream brain pipeline stages (Saving → Communities → Summaries → Embeddings) remain inactive.
- Ensured that the stepper now marks all stages as completed only once the brain pipeline has actually finished and the upload state reaches `done`, preventing the visual bug where every step appeared green as soon as the **Add to Brain** button became available.

### Files Modified
- `frontend-next/src/components/upload/ProcessingSteps.tsx`
- `README.md`

### Rationale
Previously, the stepper treated the `preview` state as if it were beyond the final defined stage, which caused every stage pill to be rendered as "completed" (green) as soon as the per‑document graph preview was ready, even though the brain pipeline had not yet been started or confirmed by the user. This change better reflects the actual pipeline: extraction is complete in `preview`, but the brain pipeline is only considered complete in the `done` state.

### Breaking Changes
- None. This is a purely visual/UX correction; the underlying upload and pipeline behavior is unchanged.

---

## [2026-03-10 00:10] - UX/PIPELINE: Make Brain Graph Auto-Load and Refresh Read-Only

### Changes
- Updated the `useBrain` hook so that its `refresh` function now performs a **read-only** fetch of the existing brain via `GET /community/brain` instead of calling the `POST /community/detect` endpoint that re-runs the full GraphRAG pipeline on demand.
- Adjusted the `BrainSection` component so the **Knowledge Brain** graph data is loaded automatically whenever a `UserBrain` is available (for example, on dashboard load or after a successful **Add to Brain**), removing the need for a manual **Load graph** button.
- Kept a single **Refresh** button in the brain panel that now simply re-fetches the latest persisted brain and associated document graphs, and added a lightweight "Loading graph data…" indicator while graphs are being (re)loaded.
- Clarified the README to document that the dashboard uses `GET /community/brain` for refreshes and that the `POST /community/detect` endpoint remains available for manual or programmatic full recomputations but is no longer used by the main UI.

### Files Modified
- `frontend-next/src/hooks/useBrain.ts`
- `frontend-next/src/components/brain/BrainSection.tsx`
- `README.md`

### Rationale
Running the full GraphRAG pipeline every time the user pressed a "Refresh" action in the dashboard was unnecessarily expensive for large brains and blurred the distinction between "show me the latest state" and "rebuild the brain." Making the dashboard refresh path read-only ensures the user can quickly update what they see without triggering a heavy recomputation, while still allowing background or manual runs of the pipeline when new documents are added.

### Breaking Changes
- None. The existing endpoints and upload flow remain intact; only the dashboard's refresh semantics and brain graph loading behavior have been made more efficient and user-friendly.

---

## [2026-03-10 00:25] - BUGFIX: Preserve Enriched Graph After Add to Brain Reset

### Changes
- Updated the Next.js upload hook `reset` helper to accept an optional `{ keepGraph?: boolean }` flag so callers can reset upload state without clearing the current `graph`.
- Changed `PdfUpload.handleAddToBrain` to call `reset({ keepGraph: true })` after `await addToBrain()` (and any `onSaveComplete` callback), ensuring the enriched document graph fetched from Neo4j at the end of `addToBrain` is not immediately nulled out by a subsequent reset.

### Files Modified
- `frontend-next/src/hooks/useUpload.ts`
- `frontend-next/src/components/upload/PdfUpload.tsx`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
With React 18 automatic batching, the `setGraph(enriched)` call at the end of `addToBrain` and the `reset()` call in `PdfUpload` were being batched into a single render pass, leaving `graph` as `null` and effectively turning the final enrichment fetch into dead code. Allowing a reset that preserves the graph keeps the UI behavior (upload panel returns to idle) while ensuring the enriched graph state is actually applied and available for downstream consumers.

### Breaking Changes
- None. Existing call sites that use `reset()` without arguments keep the previous behavior (including clearing `graph`); only the `Add to Brain` path now opts into preserving the enriched graph.

### Next Steps
- Consider wiring the preserved enriched graph into any components that display per-document previews after an `Add to Brain` action to take full advantage of the richer data.

---

## [2026-03-10 12:00] - BUGFIX: Validate Document Chunk Size and Overlap

### Changes
- Hardened document text chunking so `DOCUMENT_CHUNK_SIZE` and `DOCUMENT_CHUNK_OVERLAP` are parsed as integers with safe fallbacks and clamped to sane bounds before constructing `RecursiveCharacterTextSplitter`.
- Enforced `chunk_size >= 1` and `0 <= chunk_overlap <= chunk_size - 1` to prevent invalid configurations from causing runtime errors or pathological splitter behavior.

### Files Modified
- `backend/app/api/v1/endpoints/documents.py`
- `DEVELOPMENT.md`

### Rationale
Environment-driven chunking settings could previously be set to non-numeric, zero, or negative values, or overlaps greater than or equal to the chunk size, which could produce unexpected splitter behavior. Centralizing coercion and bounds checking in `_chunk_text` ensures robust defaults while still honoring valid custom settings.

### Breaking Changes
None. Existing default values continue to behave the same; only invalid or extreme configurations are now coerced into safe ranges.

### Next Steps
Optional: add focused tests around `_chunk_text` for edge-case settings (non-numeric, zero, negative, and oversized overlap) to prevent regressions.

---

## [2026-03-10 13:30] - BUGFIX: Reset Summarization Debouncer Per Community Level

### Changes
- Updated the background GraphRAG pipeline progress handler in `graph.py` so that the summarization debouncer tracks the last `CommunityLevel` seen and resets its `last_sent_completed` counter whenever the level changes.
- Kept the existing `debounce_every` threshold and pipeline status payload shape intact while ensuring per-level progress emits correctly for `leaf`, `mid`, and `root` summaries.

### Files Modified
- `backend/app/api/v1/endpoints/graph.py`
- `DEVELOPMENT.md`

### Rationale
The `_on_summarization_progress` callback previously shared a single `last_sent_completed` across all `CommunityLevel` values, so a large `leaf` run could suppress progress callbacks for subsequent `mid` and `root` levels because their completed-count deltas appeared too small. Resetting the debouncer whenever the hierarchy level changes allows completed counters to restart per level while preserving the existing debounce behavior.

### Breaking Changes
None. The GraphRAG pipeline status endpoint response schema is unchanged; only the internal debouncing behavior for summarization progress events has been corrected.

### Next Steps
Optional: add tests around the summarization progress callback to verify that each `CommunityLevel` starts with a fresh debouncer state and that `community_progress` progresses independently for leaf/mid/root phases.

---

## [2026-03-10 14:00] - PERF: Bulk Neo4j Document Counts for Admin Users

### Changes
- Added `Neo4jService.get_document_counts_for_user_ids` to fetch distinct document counts for multiple users in a single Neo4j query.
- Updated `admin_service.get_all_users` to use the new bulk method so the admin users list no longer issues one Neo4j query per user and instead falls back to `0` on Neo4j errors or missing entries.
- Documented the admin portal performance improvement in `README.md`.

### Files Modified
- `backend/app/services/neo4j_service.py`
- `backend/app/services/admin_service.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
The admin users endpoint previously triggered an N+1 pattern by calling `neo4j.get_user_document_count` once per user when building the paginated list, which is inefficient and can become a bottleneck as the number of users grows. Moving to a single bulk Neo4j query that returns a mapping of `user_id -> document_count` significantly reduces database round trips while preserving correct per-user document counts and safe fallback behavior when Neo4j is unavailable.

### Breaking Changes
None. The admin users API response shape is unchanged; only the underlying Neo4j access pattern has been optimized.

### Next Steps
Optional: add a small test around `get_all_users` that exercises the behavior when Neo4j is unavailable (ensuring document counts remain `0`) and when the bulk method returns partial results.

---

## [2026-03-10 14:10] - BUGFIX/UX: Prevent Self-Demotion in Admin Portal

### Changes
- Updated the Next.js admin users table so that the promote/demote button is disabled for the currently logged-in admin (`u.id === user?.id`) while still showing promote/demote controls for other users.
- Added an `aria-label` to the admin toggle button that provides clearer context for screen readers, including an explicit message when the current user’s own admin status cannot be changed from the UI.
- Hardened the client-side `handleToggleAdmin` helper to early-return when asked to toggle the current user’s own admin status, relying on the existing backend guard to prevent unsafe admin changes.

### Files Modified
- `frontend-next/src/app/admin/page.tsx`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Although the backend already prevents unsafe admin demotions (such as demoting the last remaining admin), the admin UI still allowed an admin to click a demote action on their own account, leading to confusing failures. Disabling self-demotion in the UI and clarifying the button semantics improves UX and reduces accidental or misleading interactions while keeping the backend security guarantees intact.

### Breaking Changes
None. Existing admin workflows continue to work; the only behavioral change is that admins can no longer attempt to change their own admin status from the portal UI.

---

## [2026-03-10 15:05] - DOCS: Clarify Versioned Admin API Paths

### Changes
- Updated the README admin endpoints section to show versioned paths using `{API_V1_PREFIX}` (for example, `{API_V1_PREFIX}/admin/stats` instead of `/admin/stats`).
- Added a short note explaining that the admin router is mounted at `f"{settings.API_V1_PREFIX}/admin"` in `backend/app/main.py` so that developers understand why missing the prefix causes 404s.

### Files Modified
- `README.md`
- `DEVELOPMENT.md`

### Rationale
The backend mounts the admin router under the versioned prefix defined by `settings.API_V1_PREFIX`, but the README previously documented unprefixed admin routes, which could lead to confusing 404s when calling the API directly or configuring external clients. Aligning the docs with the actual mount path reduces onboarding friction and avoids unnecessary debugging.

### Breaking Changes
None; this is a documentation-only update that reflects the existing behavior of the backend.

### Next Steps
- Consider adding a short "API base URL and versioning" subsection near the top of the README to centralize this information for all route groups.

---

## [2026-03-10 16:00] - BUGFIX: Surface Chunk-Level Entity Extraction Failures

### Changes
- Extended `ExtractionJobStatus` with `failed_chunks: List[int]`, `warnings: List[str]`, and `completed_successfully: bool` so clients can distinguish between fully successful jobs and those that completed with per-chunk errors.
- Updated the streamed entity extraction task in `entities.py` to record chunk indices and warning messages whenever `extract_entities_async` raises, instead of silently swallowing exceptions by only emitting empty `ExtractedEntities`.
- Left per-chunk caching semantics unchanged: entity results are cached only when the LLM extraction succeeds; chunks that fail are **not** written into the hash-based cache so transient errors do not poison future retries.
- Ensured the final job payload marks `completed_successfully = False` when any `failed_chunks` are present while still setting `status = "completed"` and returning a structurally complete `DocumentEntities` payload.

### Files Modified
- `backend/app/schemas/entities.py`
- `backend/app/api/v1/endpoints/entities.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Previously, chunk-level entity extraction exceptions were logged and replaced with empty `ExtractedEntities` while the overall job was still marked `completed`, giving no structured signal to the frontend that parts of the document failed to extract. Adding explicit `failed_chunks`/`warnings` metadata and a `completed_successfully` flag allows the UI to surface partial-failure states and enable retry UX, without changing how successful results are cached or how downstream aggregation and relationship extraction operate.

### Breaking Changes
- `GET /entities/extract/status/{job_id}` now returns additional, backward-compatible fields (`failed_chunks`, `warnings`, `completed_successfully`). Existing clients that ignore unknown fields continue to work; new clients can use these fields to distinguish fully successful jobs from partial failures.

### Next Steps
- Add targeted tests around `_run_extraction_task` to verify that chunk-level failures populate `failed_chunks`/`warnings`, that `completed_successfully` is `False` in those cases, and that only successful chunks are written to the entity chunk-hash cache.

---

## [2026-03-13 00:00] - BUGFIX: Arm Auth Refresh Timer on Login

### Changes
- Updated `AuthContext.setToken` to accept an optional `expiresInSeconds` value and arm the refresh timer whenever a token is set with an expiry.
- Propagated `expires_in` from the login API call through the login form so fresh logins schedule token refresh consistently (matching restore/refresh flows).
- Refactored restore-session and refresh-token paths in `AuthContext` to reuse `setToken(...)` for consistent state + refresh scheduling.

### Files Modified
- `frontend-next/src/contexts/AuthContext.tsx`
- `frontend-next/src/components/auth/LoginForm.tsx`
- `frontend-next/src/lib/api.ts`
- `DEVELOPMENT.md`

### Rationale
Previously, the refresh timer was only scheduled in the restore/refresh paths; the login path called `setToken(token, user)` which did not schedule a refresh. This could leave users authenticated but without automatic refresh until a full reload/session restore.

### Breaking Changes
None. This is an internal frontend typing change; runtime behavior is improved to match existing refresh semantics.

### Next Steps
Optional: add a small frontend test (or manual QA checklist) to confirm the refresh timer is scheduled immediately after login and after refresh-cookie session restore.

---

## [2026-03-13 12:00] - FEATURE: Admin Can Manually Deactivate/Activate Users

### Changes
- Added a new admin-only endpoint `PATCH /api/v1/admin/users/{user_id}/toggle-active` to allow administrators to activate or deactivate user accounts.
- Updated the admin portal Users table to include an **Activate/Deactivate** button per user, wired to the new endpoint and updating the `is_active` flag in real time.
- Enforced safeguards so an admin cannot change their own active status and the system prevents deactivating the last active admin user.
- Updated the README admin portal section to document manual account activation/deactivation and the associated safety checks.

### Files Modified
- `backend/app/api/v1/endpoints/admin.py`
- `frontend-next/src/app/admin/page.tsx`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Previously, there was no in-app mechanism for administrators to deactivate user accounts; the `is_active` flag could only be changed directly in the database. Adding a dedicated toggle endpoint and UI control makes it possible to suspend or re-enable users from the admin portal while preserving protections against locking out the last admin or disabling one's own account.

### Breaking Changes
None; this is an additive admin capability and a new endpoint that is only consumed by the admin frontend.

### Next Steps
- Optionally add audit logging and/or a dedicated admin audit view to show historical activation/deactivation events.
- Add backend tests around the new toggle-active endpoint, especially for the "cannot deactivate last active admin" and "cannot change own active status" constraints.

---

## [2026-03-10 16:30] - BUGFIX: Global Document Counts Use (user_id, document_name)

### Changes
- Updated Neo4j global graph statistics so `Neo4jService.get_global_counts` now computes `document_count` by counting distinct `(user_id, document_name)` pairs instead of relying on the global `list_documents` helper, which only de-duplicated by `document_name`.
- Left entity, relationship, and community counts unchanged, since they are already computed using simple label/relationship matches that are independent of document scoping.
- Documented in the README that platform-wide document statistics treat each `(user_id, document_name)` pair as a separate document to avoid collapsing identically named files across different users.

### Files Modified
- `backend/app/services/neo4j_service.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Previously, global document statistics used the `list_documents` helper that grouped by `document_name` alone, so documents with the same filename belonging to different users were collapsed into a single global document entry. Counting distinct `(user_id, document_name)` pairs in `get_global_counts` matches the intended multi-tenant semantics and keeps admin platform stats aligned with per-user document views.

### Breaking Changes
None. Only the computation for global `document_count` has changed; external API contracts and existing per-user document listing behavior are unchanged.

### Next Steps
Optional: add a small integration test around the admin stats endpoint to assert that two users with identically named documents are counted as two global documents.

---

## [2026-03-13 10:00] - BUGFIX: Refresh Cookie Lifetime Uses REFRESH_TOKEN_EXPIRE_DAYS

### Changes
- Updated the authentication endpoint cookie configuration so the refresh token HTTP-only cookie max-age now derives from `settings.REFRESH_TOKEN_EXPIRE_DAYS` instead of a hard-coded 7-day duration, keeping browser cookie lifetime aligned with the JWT refresh token expiry.

### Files Modified
- `backend/app/api/v1/endpoints/auth.py`
- `DEVELOPMENT.md`

### Rationale
Previously, the refresh token cookie was configured with a fixed 7-day `max_age` while the JWT refresh token expiry was controlled by the `REFRESH_TOKEN_EXPIRE_DAYS` environment variable, which could lead to premature sign-outs or a stale cookie sending already-expired tokens if the setting was changed. Tying the cookie lifetime directly to `REFRESH_TOKEN_EXPIRE_DAYS` ensures configuration changes affect both the token and cookie consistently.

### Breaking Changes
None. Behavior now matches the documented environment variable semantics; existing deployments that relied on the default 7-day lifetime will continue to see the same duration unless `REFRESH_TOKEN_EXPIRE_DAYS` is changed.

### Next Steps
Optional: add backend tests around the refresh endpoint to assert that the cookie `max_age` matches `REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600` and that changes to the environment variable are reflected in both the JWT expiry and cookie lifetime.

---

## [2026-03-13 11:15] - BUGFIX: Frontend Admin Toggle-Active Uses Direct Backend Endpoint

### Changes
- Updated the Next.js admin portal page to call the backend `PATCH /api/v1/admin/users/{user_id}/toggle-active` endpoint directly using `fetch` instead of the non-existent `api.toggleUserActive` helper, resolving the type error during `next build`.
- Improved error handling for toggling a user's active status so backend validation messages (e.g., preventing deactivation of the last active admin or changing one's own active status) surface to the admin UI.

### Files Modified
- `frontend-next/src/app/admin/page.tsx`
- `DEVELOPMENT.md`
- `README.md`

### Rationale
The admin UI already relied on the backend's `toggle-active` endpoint but referenced a missing `toggleUserActive` helper in the shared frontend API module, causing builds to fail at type-checking time. Calling the backend endpoint directly from the admin page restores the user activation feature without needing to modify the generated/shared API client file.

### Breaking Changes
None; the change only affects the admin frontend implementation and does not alter backend contracts.

### Next Steps
- Optionally add a dedicated `toggleUserActive` helper in the shared frontend API module if/when that file becomes directly editable, to centralize admin-related HTTP calls.

---

## [2026-03-13 12:00] - BUGFIX: Allow Re-registration After Stale Unverified Accounts Expire

### Changes
- Updated the FastAPI `/api/auth/register` endpoint to detect stale, unverified user accounts when a registration attempt uses an existing username or email, and automatically delete those stale records instead of returning a `400` error.
- Consider a user stale when their `email_verified` flag is `False` and `verification_token_expires` is either `NULL` or earlier than the current time; fresh or already-verified accounts still cause the usual duplicate-username/email validation error.

### Files Modified
- `backend/app/api/v1/endpoints/auth.py`
- `DEVELOPMENT.md`

### Rationale
Previously, if a user registered but never verified their email, their username and email remained permanently reserved in the `users` table, blocking any future attempts to register with the same credentials even after the verification link expired. Automatically deleting stale, unverified accounts at registration time matches modern UX expectations, avoids leaking unusable accounts in the database, and keeps the behavior intuitive for users retrying sign-up after a failed or lost verification email.

### Breaking Changes
None. Verified and active accounts remain fully protected from accidental deletion; only unverified accounts with expired or missing verification token expiries are eligible for cleanup.

### Next Steps
- Optionally add backend tests around the registration flow to cover re-registration after token expiry and ensure verified accounts continue to be rejected on duplicate username/email.

---

## [2026-03-13 13:15] - BUGFIX: Non-blocking Neo4j Document Count in Admin Toggles

### Changes
- Updated the admin `toggle-admin` and `toggle-active` endpoints to compute per-user Neo4j document counts using `run_in_threadpool` so the async handlers do not block on the synchronous `Neo4jService.get_user_document_count` call.
- Replaced the bare exception handlers around document-count lookups with Loguru `logger.warning` calls that record failures (including the target user id and error string) while keeping the returned `document_count` at a safe fallback of 0 when Neo4j is degraded or unavailable.

### Files Modified
- `backend/app/api/v1/endpoints/admin.py`
- `DEVELOPMENT.md`
- `README.md`

### Rationale
Previously, both admin toggle endpoints invoked the synchronous Neo4j document-count method directly from async route handlers and silently swallowed any exceptions, which could block the event loop under load and hide operational issues with Neo4j in production logs. Running the count in a threadpool and logging failures at warning level keeps the admin API responsive and aligned with the documented behavior that Neo4j errors are surfaced via logs while admin pages continue to function with zeroed counts.

### Breaking Changes
None. The admin API contracts and response shapes are unchanged; only the internal implementation of document-count retrieval and error handling has been hardened.

### Next Steps
- Optionally add backend tests around the admin toggle endpoints to assert that Neo4j document-count failures are logged and that the response continues to return `document_count=0` when the count lookup fails.

---

## [2026-03-13 14:05] - DOCS: Document Admin Toggle-Active Endpoint

### Changes
- Added README documentation for the `PATCH {API_V1_PREFIX}/admin/users/{user_id}/toggle-active` admin endpoint that toggles a user's active status (activate/deactivate), including the safeguards that prevent changing your own active status and deactivating the last active admin.

### Files Modified
- `README.md`
- `DEVELOPMENT.md`

### Rationale
The admin `toggle-active` endpoint was implemented in the backend but not yet reflected in the Admin Endpoints section of the README, which could confuse operators or frontend developers relying on the docs to understand available admin actions and their safety guarantees.

### Breaking Changes
None. This is a documentation-only update; the endpoint behavior and signatures are unchanged.

### Next Steps
- Consider adding explicit backend tests that cover the "cannot deactivate self" and "cannot deactivate last active admin" protections for the `toggle-active` endpoint to ensure future refactors preserve these safety checks.

---

## [2026-03-13 15:00] - DOCS: High-Level README Overview and Dashboard Snapshot

### Changes
- Rewrote the top of `README.md` to clearly explain the problem Ship of Theseus solves, how it helps users explore long-form documents as a knowledge brain, and to emphasize that the app is a continuous work in progress.
- Added a concise “Product snapshot” section that embeds the `assets/dashboard.png` screenshot to visually showcase the main dashboard UI.
- Introduced a brief “Tools and stack (at a glance)” section summarizing the main technologies used (FastAPI, Next.js, PostgreSQL, Redis, Neo4j, OpenAI, Docker, Loguru, Pytest, GraphRAG-inspired pipelines) without deep technical detail, while keeping the existing in-depth sections below for contributors.

### Files Modified
- `README.md`
- `DEVELOPMENT.md`

### Rationale
The existing README was highly detailed but did not quickly convey the core idea, value proposition, or visual feel of the app to new readers. Adding a short narrative, a dashboard screenshot, and a high-level tech overview makes the project easier to understand at a glance while preserving the full technical documentation further down.

### Breaking Changes
None; documentation-only update.

### Next Steps
- Optionally add a short “User journey” example in the README (upload → extract → build brain → ask questions) once the chat experience is fully wired end-to-end.

---

## [2026-03-13 15:30] - CONFIG: Restructured .cursor Folder with Rules and Skills

### Changes
- Rewrote `.cursor/rules/cursorrules.mdc` — removed outdated Streamlit references, corrected run commands, trimmed to essential always-apply standards (project overview, documentation workflow, logging, env vars).
- Added `.cursor/rules/backend.mdc` — FastAPI/Python conventions scoped to `backend/**/*.py`.
- Added `.cursor/rules/frontend.mdc` — Next.js 14 / TypeScript conventions scoped to `frontend-next/**/*.{ts,tsx}`.
- Added `.cursor/rules/graphrag-pipeline.mdc` — GraphRAG pipeline domain knowledge scoped to backend services and prompts.
- Created `.cursor/skills/graphrag-dev/SKILL.md` — project-level skill for pipeline development work.

### Files Modified
- `.cursor/rules/cursorrules.mdc`
- `.cursor/rules/backend.mdc` (new)
- `.cursor/rules/frontend.mdc` (new)
- `.cursor/rules/graphrag-pipeline.mdc` (new)
- `.cursor/skills/graphrag-dev/SKILL.md` (new)
- `DEVELOPMENT.md`

### Rationale
The single `cursorrules.mdc` file referenced a Streamlit frontend that no longer exists, included incorrect run commands, and mixed all concerns into one large file. Splitting by concern and adding a skill gives the AI assistant accurate, focused context for each type of work.

### Breaking Changes
None. Rule and skill files are AI context only and do not affect runtime behaviour.

### Next Steps
- Consider adding a `docker.mdc` rule if Docker Compose changes become frequent.
- The logging cleanup plan (`.cursor/plans/logging_cleanup_4c6e7ca3.plan.md`) is still pending.

---

## [2026-03-13 06:25] - FEATURE

### Changes
- Extended the admin system endpoint (`GET /api/v1/admin/system`) to return an `infra` block with storage/infra metrics.
- Added disk usage monitoring for configurable mount paths (used/free/total + warning/critical thresholds).
- Added PostgreSQL database size metric (`pg_database_size(current_database())`) and Redis memory usage metric (`INFO memory`).
- Added best-effort Neo4j store size metric via `dbms.queryJmx` when available; falls back gracefully when unsupported.
- Updated the Next.js admin portal (`/admin`) to display an “Infrastructure & storage” section (volumes + backing service sizes).
- Added a repo-root `.env.example` template including new disk monitoring variables.

### Files Modified
- `backend/app/schemas/admin.py`
- `backend/app/services/admin_service.py`
- `backend/app/services/infra_metrics_service.py`
- `backend/app/services/neo4j_service.py`
- `backend/app/core/config.py`
- `frontend-next/src/app/admin/page.tsx`
- `README.md`
- `.env.example`
- `DEVELOPMENT.md`

### Rationale
Hetzner production hosts often have tight disk constraints; adding storage visibility to the admin portal makes it easy to detect unhealthy growth (DB/cache/graph store) before outages.

### Breaking Changes
None. The admin system response is extended with an optional `infra` field; existing consumers remain compatible.

### Next Steps
- Consider enabling Neo4j JMX procedures/metrics in production if you want store size to always populate.

---

## [2026-03-13 07:05] - BUGFIX

### Changes
- Updated Neo4j store size computation in `infra_metrics_service` so that an invalid or unreadable `NEO4J_DATA_PATH` no longer short-circuits the best-effort Neo4j fallback.

### Files Modified
- `backend/app/services/infra_metrics_service.py`
- `DEVELOPMENT.md`

### Rationale
Previously, when `NEO4J_DATA_PATH` was set but pointed to a missing/non-directory path (or when a filesystem scan raised an unexpected error), the helper returned immediately and never attempted `neo4j.get_store_size_bytes()`, weakening the intended “try filesystem, then Neo4j helper” behaviour for admin infra metrics.

### Breaking Changes
None. Behaviour is strictly more robust; error messages now prefer filesystem details when present but still fall back cleanly to Neo4j-specific reasons.

### Next Steps
- Consider surfacing the combined filesystem/Neo4j error detail in the admin UI when store size is unavailable, to aid ops debugging.

---

## [2026-03-13 07:20] - BUGFIX

### Changes
- Fixed `get_disk_volumes` so that explicit `warn_percent` and `crit_percent` arguments take precedence over settings and correctly respect `0` as a valid threshold instead of treating it as falsy via `or`.

### Files Modified
- `backend/app/services/infra_metrics_service.py`
- `DEVELOPMENT.md`

### Rationale
The previous implementation always preferred `DISK_WARN_PERCENT`/`DISK_CRIT_PERCENT` from settings when defined and used `warn_percent or 80`/`crit_percent or 90`, causing passed-in thresholds (especially `0`) to be ignored or overridden unintentionally in admin infra metrics.

### Breaking Changes
None. Callers that relied on environment defaults are unaffected; callers that explicitly passed thresholds now get the intended behaviour.

### Next Steps
None.

---

## [2026-03-13 08:00] - BUGFIX

### Changes
- Normalised the `StorageVolume.status` field description in the admin schemas to use a standard ASCII hyphen-minus (`-`) instead of an en-dash in the phrase `critical - based on configured thresholds`, avoiding ambiguous characters when searching or copying text from OpenAPI docs.

### Files Modified
- `backend/app/schemas/admin.py`
- `DEVELOPMENT.md`

### Rationale
The previous description string used an en-dash character (`–`) which could cause subtle issues for search, copy/paste, and tooling that expects ASCII-only punctuation in status descriptions.

### Breaking Changes
None.

### Next Steps
None.

---

## [2026-03-13 09:15] - BUGFIX

### Changes
- Hardened admin infrastructure disk metrics so invalid or non-numeric `DISK_WARN_PERCENT` / `DISK_CRIT_PERCENT` settings no longer cause a `ValueError`; instead, threshold parsing now falls back to safe defaults and logs a warning.
- Wrapped disk volume enumeration in `get_infra_metrics` in a `try`/`except` block so failures in `get_disk_volumes()` result in an empty disk volumes list and a logged warning rather than breaking the entire `/admin/system` response.

### Files Modified
- `backend/app/services/infra_metrics_service.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Admin system health reporting is designed to be best-effort; disk threshold misconfiguration or disk enumeration failures should degrade gracefully and still return PostgreSQL/Neo4j/Redis metrics instead of surfacing uncaught exceptions to callers.

### Breaking Changes
None. The behaviour change is limited to more resilient error handling for disk threshold parsing and enumeration; valid configurations are unaffected.

### Next Steps
None.

---

## [2026-03-13 09:45] - BUGFIX

### Changes
- Updated Neo4j store size fallback error handling in `infra_metrics_service` so that filesystem scan errors (when `NEO4J_DATA_PATH` is set) are preserved and combined with Neo4j helper exceptions instead of being dropped, and ensured the warning log/returned error share the same combined message.

### Files Modified
- `backend/app/services/infra_metrics_service.py`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Previously, when `neo4j.get_store_size_bytes()` raised a non-`AttributeError`, the outer exception handler logged a generic message and returned only the Neo4j exception text, discarding any earlier filesystem error context collected while probing `NEO4J_DATA_PATH`, making admin infra store-size failures harder to diagnose.

### Breaking Changes
None. This is a stricter best-effort error reporting improvement; metrics remain optional and callers already treat `None` store size as a soft failure.

### Next Steps
- Consider surfacing the combined filesystem/Neo4j store-size error detail directly in the admin UI when store size is unavailable.

---

## [2026-03-16 10:15] - FEATURE

### Changes
- Constrained the authenticated dashboard layout to a fixed viewport height using `h-screen overflow-hidden` so the main grid and side panels (including chat) scroll internally instead of the whole page growing with long conversations.
- Refined the `ChatSection` UI with a fixed-height, scrollable message area, role labels on message bubbles, an animated typing indicator for the assistant, a unified rounded input bar with helper text, and a clear button that resets the current chat session and local history.
- Enhanced the chat empty state with a subtle grid background hint and explanatory copy to better communicate how the session behaves.

### Files Modified
- `frontend-next/src/app/dashboard/page.tsx`
- `frontend-next/src/components/chat/ChatSection.tsx`
- `README.md`

### Rationale
Longer chats in the dashboard were causing the right-hand chat panel to effectively stretch the entire page, making the overall layout feel less like a fixed console and more like a long-scrolling document. By fixing the dashboard height to the viewport and ensuring the chat panel scrolls internally with a more polished UI, the conversation experience feels more contained, modern, and usable for extended sessions.

### Breaking Changes
None. The changes are purely presentational; existing chat behavior, API calls, and session handling remain the same.

### Next Steps
- Consider adding persisted chat history retrieval per session so users can restore past conversations across browser reloads.

---

## [2026-03-16 19:45] - CONFIG

### Changes
- Updated the Docker Compose PostgreSQL service to use a Docker named volume (`postgres_data`) instead of a bind-mounted host directory so that `initdb` no longer fails with `chmod ... Operation not permitted` on macOS/Windows filesystems.
- Documented the new storage behaviour for Redis, Neo4j, and PostgreSQL data directories/volumes in the main `README.md`.

### Files Modified
- `docker-compose.yml`
- `README.md`
- `DEVELOPMENT.md`

### Rationale
Using a bind mount for the Postgres data directory caused permission errors when `initdb` attempted to change directory permissions on host filesystems that do not fully support Unix-style `chmod`, leading to an unhealthy `ship_postgres` container. A Docker named volume keeps the data inside Docker's managed storage where permissions are under Docker's control while still persisting across restarts, and avoids spurious permission failures on developer machines.

### Breaking Changes
Existing Postgres data stored under `./data/postgres` is no longer used by Docker Compose. A new `postgres_data` volume will be created the next time `docker compose up` runs. If you need to reset the database completely, run `docker compose down -v` to drop the volume.

### Next Steps
- Optionally add helper scripts or documentation for backing up and restoring the `postgres_data` volume for developers who want to persist or migrate local database state.

---
