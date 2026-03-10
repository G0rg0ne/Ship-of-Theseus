# Ship of Theseus 

Work in progress ...

As I continue building this project, you'll find below an overview of the features that are already implemented and supported, along with a summary of the system architecture.

## Graph RAG Architecture (Overview)

![Graph RAG flowchart: indexing and query phases](assets/BOARD.png)


The project follows a **Graph RAG** (Graph Retrieval-Augmented Generation) design:

- **Entity extraction:** For each entity (person, organization, location, key term) the LLM extracts a **description** from the surrounding text, forming an "Identity Card" (name + description) used later for embedding-based search.
- **Structural analysis (hierarchical phase):** Louvain community detection groups nodes into **leaf** communities; a meta-graph of leaf clusters is built and Louvain runs again to form **mid** and **root** levels (Leaf → Mid → Root tree).
- **Summarization:** An LLM writes a comprehensive report for every community at every level (prompt: `backend/app/prompts/community_summary.json`).
- **Vectorization (embedding phase):** Entity Identity Cards and community summaries are embedded with **text-embedding-3-small**; vectors are stored in Neo4j vector indexes for **local search** (entity-level) and **global search** (theme-level).
- **Query phase:** A user query can target entity embeddings (specific facts) or community summary embeddings (high-level themes); results are combined into a final response.

LLMs drive extraction, hierarchy building, and summary generation; Neo4j holds both the graph and the vector indexes.
### Example: Knowledge Graph Visualization

![Example of the knowledge graph extracted from one document](assets/graph_exmp.png)

**Legend:**

- **Blue circles** – *Person* entities
- **Green squares** – *Organization* entities
- **Orange diamonds** – *Location* entities
- **Purple hexagons** – *KeyTerm* or *Topic* nodes
- **Arrows** – *Relationship* types (labeled edges) extracted by LLM
- Each graph corresponds to a single document; nodes and relationships are isolated by document filename.

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
- **Admin portal**: Platform-wide statistics (users, documents, entities, relationships, communities), system health (PostgreSQL, Neo4j, Redis), and user management with optional admin promotion (admin-only; `/admin` in Next.js; `is_admin` on user model)

### Frontend UX Notes

- The multi-stage processing stepper in the upload flow now shows only the upload and extraction stages as completed while the UI is in the `preview` state, and marks all stages as completed only once the backend brain pipeline has finished and the UI reaches the `done` state, matching the 100% progress indicator.
- After entity and relationship extraction complete, the upload panel moves into a `preview` state that shows a per-document graph preview. Clicking **Add to Brain** from this state saves the graph to Neo4j and runs the full GraphRAG pipeline; when the pipeline finishes, the dashboard brain metrics/graph refresh and the upload panel returns to the idle state.
- When you navigate to the authenticated dashboard (or after a successful **Add to Brain**), the **Knowledge Brain** graph now loads automatically as soon as a brain exists; there is no longer a separate "Load graph" button. The **Refresh** action in the brain panel simply re-fetches the latest persisted brain and document graphs rather than re-running community detection.
 - The upload hook waits for the enriched per-document graph to be loaded from Neo4j before completing the **Add to Brain** action, so the preview state is not overwritten by stale graph data after the panel has been reset. This is implemented in a way that is safe with React 18 automatic batching, ensuring the final enrichment fetch is applied before the upload state is reset.
- While the long-running brain pipeline is starting (e.g. `saving_graph`, `detecting_communities`, `summarizing`, `embedding`) but before the first backend poll has populated numeric progress, the processing stepper shows a contextual status message (\"Saving graph to knowledge base…\", \"Starting brain pipeline…\", etc.) instead of an empty header with a 0% bar.

### Backend Pipeline Notes

- The full GraphRAG brain pipeline (hierarchical community detection, summarization, embedding, brain persistence, and cache warming) is implemented once in a shared service (`brain_pipeline_service`) and reused by both the manual trigger endpoint and the background job started after saving a document graph, avoiding drift between the two code paths.

## 📁 Project Structure

```
Ship-of-Theseus/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app initialization
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── endpoints/   # API route handlers
│   │   │       │   ├── auth.py
│   │   │       │   ├── documents.py
│   │   │       │   ├── entities.py   # Entity extraction (parallel, progress)
│   │   │       │   ├── graph.py     # Neo4j graph persistence; triggers full GraphRAG pipeline on save + pipeline status
│   │   │       │   ├── community.py # Community detection / knowledge brain endpoints (manual full pipeline trigger)
│   │   │       │   └── admin.py     # Admin-only: stats, users list, system health, toggle admin
│   │   │       └── deps.py      # Dependencies
│   │   ├── core/
│   │   │   ├── config.py        # Settings & configuration
│   │   │   ├── cache.py        # Redis cache manager
│   │   │   ├── prompt_manager.py  # LLM prompt loader (JSON, cached)
│   │   │   ├── security.py     # JWT & password utilities
│   │   │   └── logger.py        # Loguru logging configuration
│   │   ├── prompts/             # LLM prompt templates (JSON)
│   │   │   ├── entity_extraction.json   # Entities + Identity Card (description)
│   │   │   ├── relationship_extraction.json
│   │   │   └── community_summary.json   # Per-community report (leaf/mid/root)
│   │   ├── models/              # ORM models
│   │   │   └── user.py          # User model (PostgreSQL; is_admin for admin portal)
│   │   ├── schemas/             # Pydantic schemas
│   │   │   ├── auth.py
│   │   │   ├── entities.py
│   │   │   ├── relationships.py
│   │   │   ├── community.py     # UserBrain, CommunityInfo, HierarchicalCommunity, CommunityLevel
│   │   │   └── admin.py         # PlatformStats, UserAdminView, SystemHealth, ServiceHealth
│   │   ├── services/            # Business logic
│   │   │   ├── user_service.py
│   │   │   ├── admin_service.py # Platform stats, user list with doc counts, system health
│   │   │   ├── entity_extraction_service.py
│   │   │   ├── relationship_extraction_service.py
│   │   │   ├── neo4j_service.py   # Graph persistence, vector indexes, community nodes, entity embeddings
│   │   │   ├── community_detection_service.py  # Hierarchical Louvain (leaf/mid/root)
│   │   │   ├── summarization_service.py       # LLM community summaries
│   │   │   └── embedding_service.py           # text-embedding-3-small (entities + summaries)
│   │   └── db/                  # PostgreSQL (async engine, session, init_tables)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend-next/               # Next.js 14 frontend (primary UI)
│   ├── src/
│   │   ├── app/                 # App Router: page.tsx (welcome + auth), dashboard/page.tsx, admin/page.tsx
│   │   ├── components/          # auth/, upload/, brain/, documents/, NodeConstellation (animated canvas)
│   │   ├── hooks/               # useAuth, useUpload, useBrain (upload hook drives extraction + preview and then, on Add to Brain, saves + runs the background brain pipeline)
│   │   └── lib/                 # api.ts (backend client), utils
│   ├── package.json
│   ├── next.config.ts
│   └── Dockerfile
├── shared/                      # Shared utilities (ready for expansion)
├── tests/                       # Test files
│   └── backend/
├── logs/                        # Application logs (auto-generated)
│   ├── app_YYYY-MM-DD.log      # Backend daily logs
│   └── errors_YYYY-MM-DD.log   # Backend error logs
├── scripts/                     # Helper scripts
│   ├── ensure-data-dirs.ps1    # Create .data dirs (PowerShell)
│   └── ensure-data-dirs.sh     # Create .data dirs (Bash/WSL)
├── .data/                       # Local Docker data (gitignored): redis_data, neo4j_data, postgres_data
├── .env.example                 # Environment variables template
├── .gitignore
├── docker-compose.yml
└── README.md                    # This file
```

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose

### Setup

1. **Create `.env` file**:
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Generate a secure secret key (Linux/Mac)
   SECRET_KEY=$(openssl rand -hex 32)
   
   # Or manually edit .env with your values:
   # - SECRET_KEY: Use a strong random string
   # - DATABASE_URL: Optional; default works with docker-compose (PostgreSQL)
   ```

2. **Create local data directories** (Redis, Neo4j, PostgreSQL data are stored under `.data/` in the repo):
   ```bash
   # PowerShell (Windows)
   ./scripts/ensure-data-dirs.ps1

   # Bash / WSL / Git Bash
   ./scripts/ensure-data-dirs.sh
   ```
   Optional: set `DATA_DIR` to a different path (e.g. absolute) in `.env` if you need data elsewhere; the scripts and Compose use it.

3. **Start services**:
   ```bash
   docker-compose up -d
   ```

4. **Access the application**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Neo4j Browser (optional): http://localhost:7474 (Bolt: localhost:7687)
   - Health check: http://localhost:8000/

   **If you see "Cannot reach the server"**: ensure the backend is running. With Docker, all services start together. For local frontend dev, start the backend first: `cd backend && uvicorn app.main:app --reload --port 8000`. The frontend uses `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`); set it in `.env.local` or `.env` if your API is at a different URL.

## ⚙️ Environment Variables

See `.env.example` (project root) for a template. **If upgrading from the previous single-user auth:** remove `USERNAME`, `USER_EMAIL`, and `USER_PASSWORD` from your `.env`; user accounts are now stored in PostgreSQL.

### Required Variables (app will not start without these):
- `SECRET_KEY` - JWT secret key (generate with `openssl rand -hex 32`) - **REQUIRED**

### Optional Variables (have defaults):
- `DATA_DIR` - Local directory for Docker data (Redis, Neo4j, PostgreSQL); default `.data`. Used by `docker-compose.yml` and the `scripts/ensure-data-dirs.*` scripts.
- `DATABASE_URL` - PostgreSQL connection URL for user registration/auth (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/shipoftheseus`). **When using Docker Compose, this is overridden automatically** so the backend connects to the `postgres` service; no need to set it in `.env` for Docker.
- `ALLOWED_ORIGINS` - CORS origins (comma-separated). Default `http://localhost:3000,http://127.0.0.1:3000`. For additional origins add them comma-separated (e.g. `http://localhost:3000,http://localhost:8000`)
- `NEXT_PUBLIC_API_URL` - Backend API base URL for the Next.js frontend (e.g. `http://localhost:8000` when running frontend locally). **In production, this MUST be set to a browser-accessible public URL (for example `https://api.yourdomain.com`) and MUST NOT use Docker-internal hostnames like `http://backend:8000`, because this value is baked into the client-side bundle at build time.**
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiration in minutes (default: `30`)
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

## 🏃 Running Locally (Development)

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Logs will be automatically created in the `logs/` directory with automatic rotation and compression.

### Frontend (Next.js)
```bash
cd frontend-next
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```
The app runs at http://localhost:3000 (dark theme by default). Add a `brain-example.png` image under `frontend-next/public/` to show an example knowledge brain on the welcome page.

## 🧪 Testing

```bash
# Backend tests
cd backend
pytest

# Run with coverage
pytest --cov=app --cov-report=html
```

## 📡 API Endpoints

### Base URL
`http://localhost:8000/api`

### Authentication Endpoints
- `POST /auth/register` - Create a new user account (username, email, password)
- `POST /auth/login` - Login and get JWT token
- `GET /auth/me` - Get current user info (requires auth)
- `GET /auth/verify` - Verify token validity (requires auth)

### Document Management Endpoints
- `POST /documents/upload` - Upload PDF and extract text (requires auth, max 10MB); stored in Redis
- `GET /documents/current` - Get currently stored document (requires auth)
- `DELETE /documents/current` - Clear stored document (requires auth)

### Entity Extraction Endpoints (parallel, progress via Redis)
- `POST /entities/extract` - Start entity extraction on current document; returns `job_id` (requires auth). When complete, relationship extraction is auto-started with job_id `{job_id}_rel`.
- `GET /entities/extract/status/{job_id}` - Get extraction progress: status, `completed_chunks`/`total_chunks` (requires auth)
- `GET /entities/extract/result/{job_id}` - Get extraction result when completed (requires auth; 202 if still running)

### Relationship Extraction Endpoints (graph-ready: nodes + edges)
- `GET /entities/extract/relationships/status/{job_id}` - Get relationship extraction progress (use `{entity_job_id}_rel` as job_id) (requires auth)
- `GET /entities/extract/relationships/result/{job_id}` - Get graph result (nodes + edges) when relationship extraction completed (requires auth; 202 if still running)
- `GET /entities/extract/graph/{job_id}` - Get complete graph for an entity job (uses entity job_id; returns graph when relationship extraction has completed) (requires auth)

### Graph Persistence (Neo4j) Endpoints
- `POST /graph/save/{job_id}` - Save extracted graph to Neo4j and trigger the **full GraphRAG pipeline** in the background (community detection → summarization → embedding). Returns `{ ok, message, document_name, pipeline_job_id }` (uses entity job_id; requires auth).
- `GET /graph/list` - List documents in Neo4j with node/edge counts (requires auth)
- `GET /graph/{document_name}` - Get graph from Neo4j by document name (requires auth)
- `DELETE /graph/{document_name}` - Delete document graph from Neo4j (requires auth)
- `GET /graph/health` - Neo4j connectivity check (requires auth)
- `GET /graph/pipeline/status/{pipeline_job_id}` - Get status of a long‑running graph pipeline job; returns the current `step` (`community_detection`, `summarizing`, `embedding`), `step_index`, `total_steps`, `status` (`running|done|failed`), and `message`. During `summarizing`, the response also includes `community_progress` with `{ completed, total }` so the UI can show per-community progress (requires auth)

### Community Detection / Knowledge Brain Endpoints (GraphRAG)
- `GET /community/brain` - Get current user's knowledge brain (includes `communities_by_level` with summaries when full pipeline has run; cache: Redis → Neo4j Brain node → recompute fallback; requires auth). The dashboard **Refresh** button uses this read-only endpoint to update what is shown to the user.
- `POST /community/detect` - Run full GraphRAG pipeline: hierarchical detection (Leaf → Mid → Root), LLM summarization per community, entity and summary embedding (text-embedding-3-small), persist to Neo4j (assignments, community nodes, vector indexes); returns enriched brain (requires auth). This endpoint is available for manual or programmatic re-computation but is no longer called from the main dashboard UI.
- `DELETE /community/brain` - Permanently delete the user's brain, community nodes, and all document graphs from Neo4j; clear Redis cache (requires auth)

### Admin Endpoints (require admin user; 403 if not admin)
- `GET /admin/stats` - Platform statistics: total/active/new (7d) users, total documents, entities, relationships, communities, avg docs per user
- `GET /admin/users` - Paginated user list with document counts (query: `page`, `limit`; default limit 20, max 100)
- `GET /admin/system` - System health: PostgreSQL, Neo4j, Redis status plus global Neo4j node/edge/community counts
- `PATCH /admin/users/{user_id}/toggle-admin` - Promote or demote a user's admin status

**Note:** Users have an `is_admin` flag (default `false`). Set it in the database for the first admin; thereafter use the Admin portal to promote/demote others.

Example (Docker Compose + PostgreSQL):

```bash
docker compose exec postgres psql -U postgres -d shipoftheseus -c "UPDATE users SET is_admin = true WHERE username = 'admin-dev';"
```

**Implementation detail:** Neo4j nodes are scoped by `user_id` using the user's **PostgreSQL UUID** (not email/username). If you have older Neo4j data created before this change, per-user stats may show 0 until you re-save/reprocess documents or migrate existing Neo4j nodes to the UUID-based `user_id`.

## 🐳 Docker, Redis, PostgreSQL, and Neo4j

With Docker Compose, the backend uses **Redis** for caching, **PostgreSQL** for user accounts (registration/login), and **Neo4j** for persistent graph storage:
- **Documents**: Stored under `documents:{user_id}` (TTL 24h)
- **Extraction jobs**: Status and result under `extraction:job:{job_id}` (TTL 1h)
- **Relationship jobs**: Status and graph result under `extraction:relationships:job:{job_id}` (TTL 1h)
- **Community brain**: Per-user knowledge brain under `community:brain:{user_id}` (TTL 24h; rebuilt on each document save)

- **Redis** runs as service `redis`; data is stored **locally** in `.data/redis_data/` (or `$DATA_DIR/redis_data` if set). The backend gets `REDIS_URL=redis://redis:6379/0` when using Docker. For local runs, set `REDIS_URL` (e.g. `redis://localhost:6379/0`) or leave unset to use in-memory cache.
- **PostgreSQL** runs as service `postgres` (PostgreSQL 16). Data is stored **locally** in `.data/postgres_data/` (or `$DATA_DIR/postgres_data` if set). The backend connects via `DATABASE_URL` (injected by docker-compose). Users register and log in via the frontend; credentials are stored in PostgreSQL.
- **Neo4j** runs as service `neo4j`. Data is stored **locally** in `.data/neo4j_data/` (or `$DATA_DIR/neo4j_data` if set). **IMPORTANT**: Set `NEO4J_URI=bolt://neo4j:7687` in `.env` when using Docker (not `localhost`). The authentication credentials (`NEO4J_USER` and `NEO4J_PASSWORD`) must match those in `docker-compose.yml` (default: `neo4j/password123`). Each document's graph is stored separately (isolated by document filename). Use the **Add to Brain** action in the PDF upload panel to save the extracted graph to Neo4j and start the brain pipeline.

Create the local data directories before first run (Setup step 2), or run `scripts/ensure-data-dirs.ps1` (PowerShell) or `scripts/ensure-data-dirs.sh` (Bash/WSL).

### If you see: "error while creating mount source path ... file exists" (Docker Desktop + WSL2)

This is a known Docker Desktop bug with bind mounts when the project is on a Windows path. **Recommended fix: run Docker from inside WSL** so the project path is a Linux path:

1. Open **WSL** (e.g. Ubuntu) and go to the project:
   ```bash
   cd /mnt/e/repos/Ship-of-Theseus
   ```
   (Use the path that matches your drive; `e` → your repo drive letter.)

2. Create data dirs and start:
   ```bash
   ./scripts/ensure-data-dirs.sh
   docker compose up -d
   ```

Data will still live in `.data/` under the repo (visible in both WSL and Windows at the same path).

**Alternative:** From Windows, run `docker compose down`, **restart Docker Desktop**, then run `./scripts/ensure-data-dirs.ps1` and `docker compose up -d` again. If it still fails, use the WSL method above.

## 🐳 Docker Commands

```bash
# View logs
docker-compose logs -f [service_name]

# Rebuild service
docker-compose build [service_name]
docker-compose up -d [service_name]

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v
```

## 📚 Documentation

- [DEVELOPMENT.md](DEVELOPMENT.md) - Development log and changelog
- [.cursor/rules/README.mdc](.cursor/rules/README.mdc) - Complete project documentation and standards
- [.cursor/rules/cursorrules.mdc](.cursor/rules/cursorrules.mdc) - Cursor AI assistant rules
- [.cursor/rules/context.mdc](.cursor/rules/context.mdc) - Project context for AI assistant
- [.cursor/rules/DEVELOPMENT.mdc](.cursor/rules/DEVELOPMENT.mdc) - Development guidelines
- [tests/README.md](tests/README.md) - Testing guide
- [shared/README.md](shared/README.md) - Shared utilities guide

## 🔧 Development

The project follows a modular architecture:

- **Backend**: FastAPI with clean separation of concerns (routes, services, schemas, core)
- **Frontend**: Next.js 14 (TypeScript, Tailwind CSS, shadcn/ui) with a dark nautical UI; welcome page with animated node constellation, auth panel, and a 3-panel dashboard (upload/documents, Knowledge Brain force-directed graph, Ask your brain chat)
- **Shared**: Common utilities that can be used by both services
- **Tests**: Comprehensive test coverage for both services
- **Logging**: Loguru-based logging with automatic rotation, compression, and colored console output

### Logging

This project uses [Loguru](https://github.com/Delgan/loguru) for all logging needs.

**Backend logging:**
```python
from app.core.logger import logger

logger.info("General information")
logger.success("Operation succeeded")
logger.warning("Warning message")
logger.error("Error message")
logger.exception("Exception with traceback")
```

**Features:**
- Automatic file rotation at midnight
- Log retention: 30 days (general), 90 days (errors)
- Automatic compression of old logs
- Colored console output for better readability
- Thread-safe logging
- Debug level logging in files, INFO level in console

See [.cursor/rules/README.mdc](.cursor/rules/README.mdc) for detailed development guidelines and project standards.

### Prompt Management

LLM prompts for entity and relationship extraction are stored as JSON files in `backend/app/prompts/`. The **PromptManager** (`app.core.prompt_manager`) loads and caches these prompts so you can edit prompt text without changing Python code.

- **Location**: `backend/app/prompts/*.json`
- **Format**: Each file has `name`, `description`, `version`, `template`, `input_variables`, and optional `metadata`.
- **Usage**: Services call `PromptManager.get_prompt("entity_extraction")` or `PromptManager.get_prompt("relationship_extraction")` to get the template and input variables.
- **Customization**: Edit the JSON files to change prompt wording; the app uses cached copies until restarted (or call `PromptManager.reload_prompt(name)` / `PromptManager.clear_cache()` to refresh).

## License

MIT
