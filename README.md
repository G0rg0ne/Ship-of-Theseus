## Ship of Theseus

Ship of Theseus is a **knowledge brain for long-form documents**.
You upload PDFs, and the app builds an interactive knowledge graph so you can
**see how ideas connect** and ask focused questions instead of re‑reading hundreds
of pages.

This README is intentionally **high level**. For deep technical and operational
details, see the links in **Where to learn more**.

---

## What you can do

- **Upload PDFs** and extract their content into a structured knowledge graph.
- **See the important entities** (people, organisations, places, key concepts) in each document.
- **Explore relationships** between entities as an interactive graph.
- **Build a personal “knowledge brain”** that merges graphs across all your documents.
- **Ask targeted questions** to the brain (GraphRAG‑style retrieval and LLM answers).
- **Manage your account** with email‑based registration, login, and an admin portal.

---

## How it works (conceptual)

At a high level, Ship of Theseus:

1. **Extracts entities and relationships** from document text using LLMs.
2. **Builds a graph** in Neo4j where nodes are entities and communities of related ideas.
3. **Summarises communities** (leaf → mid → root) to capture higher‑level themes.
4. **Embeds entities and summaries** into vector indexes so queries can retrieve
   both specific facts and broad topics.

You can think of it as a **GraphRAG pipeline** wrapped in a user‑friendly web app.

---

## Architecture at a glance

- **Frontend**: Next.js 14 (TypeScript, Tailwind, shadcn/ui)
  - Dark nautical dashboard with:
    - PDF upload and processing flow
    - Per‑document graph preview
    - “Knowledge Brain” view (merged graph & metrics)
    - Auth pages and admin portal
- **Backend**: FastAPI
  - REST API for auth, document upload, extraction, graph persistence, and admin
  - GraphRAG pipeline orchestration (community detection, summarisation, embeddings)
- **Data & infra**
  - **PostgreSQL** for users and auth
  - **Redis** for caching jobs and brain state
  - **Neo4j** for the graph and vector indexes
  - **OpenAI** for extraction, summarisation, and embeddings
  - **Docker Compose** for local orchestration

---

## Visual snapshot

![Dashboard screenshot: knowledge brain view](assets/dashboard.png)

The dashboard shows your documents, the merged knowledge brain graph, and a
panel for asking questions to the brain.


## Where to learn more

Use these documents when you need more detail:

- **Changelog & development history**: `DEVELOPMENT.md`
- **Full project standards & deep docs**: `.cursor/rules/README.mdc`
- **Cursor AI rules for this repo**: `.cursor/rules/cursorrules.mdc`
- **Testing guide**: `tests/README.md`
- **Shared utilities guide**: `shared/README.md`
- **Backend API details**: FastAPI interactive docs at `http://localhost:8000/docs`

These resources cover:

- Exact API endpoints and schemas
- Environment variables and deployment details
- Internal pipeline design, logging, and testing strategy


## License

MIT

# Technical Documentation

## Graph RAG Architecture (Overview)

![Graph RAG flowchart: indexing and query phases](assets/BOARD.png)


The project follows a **Graph RAG** (Graph Retrieval-Augmented Generation) design:

- **Entity extraction:** For each entity (person, organization, location, key term) the LLM extracts a **description** from the surrounding text, forming an "Identity Card" (name + description) used later for embedding-based search.
- **Structural analysis (hierarchical phase):** Louvain community detection groups nodes into **leaf** communities; a meta-graph of leaf clusters is built and Louvain runs again to form **mid** and **root** levels (Leaf → Mid → Root tree).
- **Summarization:** An LLM writes a comprehensive report for every community at every level (prompt: `backend/app/prompts/community_summary.json`).
- **Vectorization (embedding phase):** Entity Identity Cards and community summaries are embedded with **text-embedding-3-small**; vectors are stored in Neo4j vector indexes for **local search** (entity-level) and **global search** (theme-level).
- **Query phase:** A user query can target entity embeddings (specific facts) or community summary embeddings (high-level themes); results are combined into a final response.

LLMs drive extraction, hierarchy building, and summary generation; Neo4j holds both the graph and the vector indexes.

## Features

- 🔐 Registration and JWT-based authentication (PostgreSQL-backed user accounts; sign up and sign in)
- 📄 PDF document upload and text extraction
- 🔍 **Knowledge graph extraction**: "Process Document" runs entity then relationship extraction; shows entity + relationship counts. If extraction fails or times out, the user sees a clear error and a **Try again** option.
- 🔗 Relationship extraction (auto-triggered after entities); constrained to extracted entities only; graph-ready output (nodes + edges)
- 📦 Redis cache (documents, extraction jobs, relationship jobs, community brain); in-memory fallback when Redis is not set or when Redis is unavailable, with per-key in-memory fallback on Redis misses
- 🗄️ **Neo4j graph database**: Persist extracted knowledge graphs per document. After processing, the user first sees a **per‑document graph preview** (with entity + relationship counts and community colouring when the pipeline has finished) and can then choose to keep it in the brain. Nodes are tagged with `user_id` and `document_name`. Entity embeddings and community summary embeddings are **fingerprint-aware**: a stable hash of each entity's Identity Card and each community's summary text is stored alongside the embedding so re-running the pipeline only re-embeds items whose content actually changed, avoiding unnecessary OpenAI calls.
- 🧠 **Community Detection / Knowledge Brain (GraphRAG):** Saving a document graph now automatically triggers the **full GraphRAG pipeline** in the background: hierarchical community detection (Leaf → Mid → Root), LLM summarization per community, and entity + summary embedding with **text-embedding-3-small**. Pipeline progress is tracked in Redis and surfaced in the UI (community detection → summarization → embedding). The merged knowledge brain across all documents is stored in Neo4j and cached in Redis with `communities_by_level` summaries. Derived `:Community` nodes in Neo4j are keyed by `community_id` and tagged with `derived_user_id` so they remain separate from the per-user source graph queried via `user_id`, and entity embeddings are written to nodes scoped by `(user_id, document_name, id)` so entities with the same id in different documents remain isolated. Refreshing the brain view in the dashboard now uses a **read-only** fetch of the existing brain state instead of re-running the full pipeline on demand.
- 🚀 FastAPI backend with modular architecture
- 🎨 **Next.js 14** frontend (TypeScript, Tailwind CSS, shadcn/ui): **Nautical + Scholarly** dark UI — warm amber/gold accents on deep navy; Crimson Pro serif headings; **welcome page** with asymmetric split: animated **node constellation** canvas (amber/teal particles + connecting lines) and horizontal journey strip (Upload → Extract → Build → Explore) on the left; auth panel with left accent bar on the right; **dashboard** with dot-grid background, anchor branding; **3-panel layout**: left sidebar (upload + document list), center (**Knowledge Brain** — metrics, force-directed graph, slide-in community panel), right panel (**Ask your brain** chat with document-context badges and message input; bot backend not yet wired)
- 🐳 Docker Compose orchestration (backend, frontend, Redis, Neo4j, PostgreSQL)
- 📝 Loguru-based logging with automatic rotation and compression
- 📁 Well-organized project structure
- **Admin portal**: Platform-wide statistics (users, documents, entities, relationships, communities), system health (PostgreSQL, Neo4j, Redis), and user management with optional admin promotion and manual account activation/deactivation (admin-only; `/admin` in Next.js; `is_admin`/`is_active` on user model). The UI prevents an admin from toggling their own admin or active status; the backend API also guards against demoting or deactivating the last remaining active admin. Neo4j errors encountered while computing platform stats, per-user document counts (including those recomputed after toggling a user's admin or active status), or global node/edge/community counts are logged via Loguru at warning level while the admin API continues to return safe fallback zeros so the portal remains usable when Neo4j is degraded.
  - Admin user list now uses a single bulk Neo4j query to compute per-user document counts, avoiding N+1 Neo4j calls when paginating over many users.
  - Global Neo4j document counts used for admin platform statistics treat each `(user_id, document_name)` pair as a distinct document, so two users with identically named files are counted separately and never collapsed into a single global document.

### Frontend UX Notes

- The multi-stage processing stepper in the upload flow now shows only the upload and extraction stages as completed while the UI is in the `preview` state, and marks all stages as completed only once the backend brain pipeline has finished and the UI reaches the `done` state, matching the 100% progress indicator.
- After entity and relationship extraction complete, the upload panel moves into a `preview` state that shows a per-document graph preview. Clicking **Add to Brain** from this state saves the graph to Neo4j and runs the full GraphRAG pipeline; when the pipeline finishes, the dashboard brain metrics/graph refresh and the upload panel returns to the idle state.
- When you navigate to the authenticated dashboard (or after a successful **Add to Brain**), the **Knowledge Brain** graph now loads automatically as soon as a brain exists; there is no longer a separate "Load graph" button. The **Refresh** action in the brain panel simply re-fetches the latest persisted brain and document graphs rather than re-running community detection.
 - The upload hook waits for the enriched per-document graph to be loaded from Neo4j before completing the **Add to Brain** action, so the preview state is not overwritten by stale graph data after the panel has been reset. This is implemented in a way that is safe with React 18 automatic batching, ensuring the final enrichment fetch is applied before the upload state is reset.
- While the long-running brain pipeline is starting (e.g. `saving_graph`, `detecting_communities`, `summarizing`, `embedding`) but before the first backend poll has populated numeric progress, the processing stepper shows a contextual status message (\"Saving graph to knowledge base…\", \"Starting brain pipeline…\", etc.) instead of an empty header with a 0% bar.

### Backend Pipeline Notes

- The full GraphRAG brain pipeline (hierarchical community detection, summarization, embedding, brain persistence, and cache warming) is implemented once in a shared service (`brain_pipeline_service`) and reused by both the manual trigger endpoint and the background job started after saving a document graph, avoiding drift between the two code paths.

## ⚙️ Environment Variables

See `.env.example` (project root) for a template. **If upgrading from the previous single-user auth:** remove `USERNAME`, `USER_EMAIL`, and `USER_PASSWORD` from your `.env`; user accounts are now stored in PostgreSQL.

### Required Variables (app will not start without these):
- `SECRET_KEY` - JWT secret key (generate with `openssl rand -hex 32`) - **REQUIRED**

### Optional Variables (have defaults):
- `DATA_DIR` - Local directory for Docker data (Redis, Neo4j, PostgreSQL); default `.data`. Used by `docker-compose.yml` and the `scripts/ensure-data-dirs.*` scripts.
- `DATABASE_URL` - PostgreSQL connection URL for user registration/auth (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/shipoftheseus`). **When using Docker Compose, this is overridden automatically** so the backend connects to the `postgres` service; no need to set it in `.env` for Docker.
- `ALLOWED_ORIGINS` - CORS origins (comma-separated). Default `http://localhost:3000,http://127.0.0.1:3000`. For additional origins add them comma-separated (e.g. `http://localhost:3000,http://localhost:8000`)
- `NEXT_PUBLIC_API_URL` - Backend API base URL for the Next.js frontend (e.g. `http://localhost:8000` when running frontend locally). **In production, this MUST be set to a browser-accessible public URL (for example `https://api.yourdomain.com`) and MUST NOT use Docker-internal hostnames like `http://backend:8000`, because this value is baked into the client-side bundle at build time.**
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Access token expiration in minutes (default: `15`)
- `REFRESH_TOKEN_EXPIRE_DAYS` - Refresh token expiration in days (default: `7`). Refresh token is stored in a **httpOnly cookie**.
- `FRONTEND_URL` - Public frontend URL used when building email verification links (default: `http://localhost:3000`)
- **SMTP (email verification)**:
  - `SMTP_HOST` - SMTP server hostname (default: `localhost`; in Docker Compose it's set to `mailhog`)
  - `SMTP_PORT` - SMTP port (default: `1025`)
  - `SMTP_USER` - SMTP username (default: empty)
  - `SMTP_PASSWORD` - SMTP password (default: empty)
  - `SMTP_FROM` - From address for verification emails (default: `noreply@shipoftheseus.local`)
- `DEBUG` - Debug mode (default: `False`)
- `REDIS_URL` - Redis connection URL (e.g. `redis://localhost:6379/0`). If unset, in-memory cache is used. **When using Docker Compose, this is overridden to `redis://redis:6379/0`** so the backend reaches the Redis service.
- `OPENAI_API_KEY` - Required for entity extraction; if unset, extraction endpoints return 503.
- `ENTITY_EXTRACTION_MODEL` - LLM model for extraction (default: `gpt-4o-mini`)
- `DOCUMENT_CHUNK_SIZE` - Document chunk size (default: `800`)
- `DOCUMENT_CHUNK_OVERLAP` - Document chunk overlap (default: `150`)
- `ENTITY_EXTRACTION_BATCH_SIZE` - Chunks processed per batch (default: `10`)
- `ENTITY_EXTRACTION_CONCURRENCY` - Max concurrent entity LLM calls (default: `20`)
- `RELATIONSHIP_EXTRACTION_BATCH_SIZE` - Chunks processed per batch for relationship extraction (default: `10`)
- `RELATIONSHIP_EXTRACTION_CONCURRENCY` - Max concurrent relationship LLM calls (default: `20`)
- `AUTO_EXTRACT_RELATIONSHIPS` - Auto-trigger relationship extraction after entity extraction (default: `true`)
- `LLM_RETRY_MAX_ATTEMPTS` - Retries for transient LLM failures (default: `3`)
- `LLM_RETRY_BASE_DELAY_MS` - Base backoff delay in ms (default: `500`)
- `LLM_RETRY_MAX_DELAY_MS` - Max backoff delay in ms (default: `5000`)
- **Neo4j** (optional; graph persistence disabled if unavailable):
  - `NEO4J_URI` - Bolt URL. **When using Docker Compose, this is overridden to `bolt://neo4j:7687`**; use `bolt://localhost:7687` for local dev.
  - `NEO4J_USER` - Neo4j username (set in `.env`; no default in compose)
  - `NEO4J_PASSWORD` - Neo4j password (set in `.env` only; no password appears in docker-compose)
  - `NEO4J_DATABASE` - Database name (default: `neo4j`)
- **GraphRAG (community summarization and embedding):**
  - `EMBEDDING_MODEL` - OpenAI embedding model (default: `text-embedding-3-small`). Neo4j vector index dimensions are derived from this model at runtime so index configuration always matches the active embedding model.
  - `COMMUNITY_SUMMARIZATION_MODEL` - LLM for community reports (default: `gpt-4o-mini`)
  - `COMMUNITY_SUMMARIZATION_CONCURRENCY` - Max concurrent community-summary LLM calls per hierarchy level (default: `50`). Tune down if you hit rate limits; tune up for faster summarization.
n example knowledge brain on the welcome page.


## 📡 API Endpoints

### Authentication Endpoints
- `POST /auth/register` - Create a new user account and queue a verification email (username, email, password)
- `GET /auth/verify-email?token=...` - Verify email address using the **verification token in the query string** (this is the link users click from the email; the frontend verify page calls this)
- *(No `POST /auth/verify-email` route)* - Email verification is intentionally performed via the GET link token; to request a new email, use `POST /auth/resend-verification` with `{ email }`
- `POST /auth/resend-verification` - Queue resend verification email (`{ email }`)
- `POST /auth/login` - Login (returns access token JSON; sets refresh token cookie)
- `POST /auth/refresh` - Rotate refresh cookie and return a new access token (frontend calls this automatically)
- `POST /auth/logout` - Clear refresh token cookie
- `GET /auth/me` - Get current user info (requires auth)
- `GET /auth/verify` - Verify token validity (requires auth)

**Frontend auth safety:** The Next.js auth context uses a session generation guard so stale in-flight refresh calls cannot rehydrate token/user state after logout.

**Email sending behavior:** Verification emails are scheduled via FastAPI background tasks (best-effort) so the API response is not blocked by SMTP. Delivery failures will be visible in backend logs rather than as synchronous HTTP errors.

### Document Management Endpoints
- `POST /documents/upload` - Upload PDF and extract text (requires auth, max 10MB); stored in Redis under the authenticated user's stable UUID (`str(current_user.id)`)
- `GET /documents/current` - Get currently stored document for the authenticated user (keyed by stable UUID)
- `DELETE /documents/current` - Clear stored document for the authenticated user (keyed by stable UUID)

### Entity Extraction Endpoints (parallel, progress via Redis)
- `POST /entities/extract` - Start entity extraction on current document; returns `job_id` (requires auth). Jobs and per-chunk caches are scoped by the user's stable UUID (`str(current_user.id)`). When complete, relationship extraction is auto-started with job_id `{job_id}_rel`.
- `GET /entities/extract/status/{job_id}` - Get extraction progress: status, `completed_chunks`/`total_chunks`, and any `failed_chunks`/`warnings` recorded during extraction (requires auth). The `completed_successfully` flag is `false` when one or more chunks failed even if the overall job status is `completed`. Progress and final status snapshots are written to Redis on a **best-effort** basis: failures in `cache_set` are logged via Loguru but never abort the extraction job.
- `GET /entities/extract/result/{job_id}` - Get extraction result when completed (requires auth; 202 if still running)

### Relationship Extraction Endpoints (graph-ready: nodes + edges)
- `GET /entities/extract/relationships/status/{job_id}` - Get relationship extraction progress (use `{entity_job_id}_rel` as job_id) (requires auth)
- `GET /entities/extract/relationships/result/{job_id}` - Get graph result (nodes + edges) when relationship extraction completed (requires auth; 202 if still running)
- `GET /entities/extract/graph/{job_id}` - Get complete graph for an entity job (uses entity job_id; returns graph when relationship extraction has completed) (requires auth)

### Graph Persistence (Neo4j) Endpoints
- `POST /graph/save/{job_id}` - Save extracted graph to Neo4j and trigger the **full GraphRAG pipeline** in the background (community detection → summarization → embedding). Returns `{ ok, message, document_name, pipeline_job_id }` (uses entity job_id; requires auth).
- `GET /graph/list` - List **current user's** documents in Neo4j with node/edge counts (requires auth)
- `GET /graph/{document_name}` - Get **current user's** graph from Neo4j by document name (requires auth; returns 404 if not found/owned)
- `DELETE /graph/{document_name}` - Delete **current user's** document graph from Neo4j (requires auth; returns 404 if not found/owned)
- `GET /graph/health` - Neo4j connectivity check (requires auth)
- `GET /graph/pipeline/status/{pipeline_job_id}` - Get status of a long‑running graph pipeline job; returns the current `step` (`community_detection`, `summarizing`, `embedding`), `step_index`, `total_steps`, `status` (`running|done|failed`), and `message`. During `summarizing`, the response also includes `community_progress` with `{ completed, total }` so the UI can show per-community progress (requires auth)

### Community Detection / Knowledge Brain Endpoints (GraphRAG)
- `GET /community/brain` - Get current user's knowledge brain (includes `communities_by_level` with summaries when full pipeline has run; cache: Redis → Neo4j Brain node → recompute fallback; requires auth). Returns **200** with an empty brain (`status="empty"`, zeros) when the user has no graph yet. The dashboard **Refresh** button uses this read-only endpoint to update what is shown to the user.
- `POST /community/detect` - Run full GraphRAG pipeline: hierarchical detection (Leaf → Mid → Root), LLM summarization per community, entity and summary embedding (text-embedding-3-small), persist to Neo4j (assignments, community nodes, vector indexes); returns enriched brain (requires auth). This endpoint is available for manual or programmatic re-computation but is no longer called from the main dashboard UI.
- `DELETE /community/brain` - Permanently delete the user's brain, community nodes, and all document graphs from Neo4j; clear Redis cache (requires auth)

### Admin Endpoints (require admin user; 403 if not admin)
- `GET {API_V1_PREFIX}/admin/stats` - Platform statistics: total/active/new (7d) users, total documents, entities, relationships, communities, avg docs per user
- `GET {API_V1_PREFIX}/admin/users` - Paginated user list with document counts (query: `page`, `limit`; default limit 20, max 100)
- `GET {API_V1_PREFIX}/admin/system` - System health: PostgreSQL, Neo4j, Redis status plus global Neo4j node/edge/community counts
- `PATCH {API_V1_PREFIX}/admin/users/{user_id}/toggle-admin` - Promote or demote a user's admin status; prevents demoting the last remaining admin
- `PATCH {API_V1_PREFIX}/admin/users/{user_id}/toggle-active` - Toggle a user's active status (activate/deactivate); prevents changing your own active status and deactivating the last active admin
- `DELETE {API_V1_PREFIX}/admin/users/{user_id}` - Permanently delete a user and all of their knowledge brain data (Neo4j graphs, community brain) and cached documents; prevents deleting your own account and the last remaining admin

**Note:** The admin router is mounted at `f"{settings.API_V1_PREFIX}/admin"` in the backend (see `backend/app/main.py`), so be sure to include the API version prefix in all admin requests to avoid 404s.

**Note:** Users have an `is_admin` flag (default `false`). Set it in the database for the first admin; thereafter use the Admin portal to promote/demote others.


