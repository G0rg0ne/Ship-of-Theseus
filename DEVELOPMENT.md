# Development Log

This file tracks all development changes, features, bug fixes, and architectural decisions for the Ship of Theseus project.

**Format**: Each entry should include date, type, changes, files modified, rationale, and any breaking changes.

---

## [2026-02-19] - FEATURE (Streamlit UX refresh)

### Changes
- **Layout**: Switched from centered narrow (640px) to **wide** responsive layout; max-width ~1100px, improved vertical rhythm and spacing; button styling aligned so `use_container_width` works.
- **Header**: Refined authenticated header (title, tagline, user chip, secondary logout); added collapsible "What happens next?" expander. Login form: clearer title/subtitle ("Sign in", caption).
- **Upload and processing**: Upload section as single card with file name/size; **stable session-state flow**: `processing_state` (idle | uploading | extracting_entities | extracting_relationships | done | error), `processing_job_id`, `processing_progress`. Process button only when idle; after starting job, rerun to show **st.status()** with step-by-step progress until done. "Try again" on extraction error (resets state, increments uploader key). **Clear document**: moved into expander with confirmation checkbox "I want to clear the current document" then secondary Clear button.
- **Knowledge graph explorer**: Toolbar above cards: **Search** (entity labels, relationship type, context), **Entity type** and **Relationship type** multiselect filters, **Sort by** (Original, Source entity, Relationship type). Relationship context moved into per-card **Context** expanders. **Relationships** and **Entities** tabs; Entities tab shows type badges with counts and search. **Download graph JSON** button. Keys support multiple instances (e.g. Knowledge Base viewer) via `key_prefix`.
- **Knowledge Base browser**: Collapsible expander "Knowledge Base — browse saved graphs": list saved documents via `list_neo4j_documents`, select document, "Load graph" loads via `get_graph_from_neo4j` and renders in same explorer with `key_prefix="kb"`. No backend changes.

### Files Modified
- `frontend/app.py` – `layout="wide"`, CSS max-width 1100px, vertical rhythm, button min-width only
- `frontend/components/welcome_page.py` – header columns, user chip, logout type="secondary", "What happens next?" expander
- `frontend/components/login_form.py` – "Sign in" header, caption subtitle
- `frontend/components/pdf_section.py` – processing state machine, upload card, st.status() polling, Try again, clear-document expander + confirm; _render_knowledge_graph_section refactor (toolbar, filters, sort, context expanders, Entities tab, JSON download, key_prefix); _render_entities_tab(); Knowledge Base expander with list/load/view
- `README.md` – Features (graph explorer, KB browser, layout/processing/clear-document); Development frontend line
- `DEVELOPMENT.md` – this entry

### Rationale
- Plan: improve UX with wider layout, stable processing feedback, easier graph exploration (search/filter/sort), optional KB browser; cards-only (no new graph-viz dependency).

### Breaking Changes
None. Session state extended with processing_*, kb_loaded_*; existing flows unchanged.

### Next Steps
- None.

---

## [2026-02-19 19:05] - BUGFIX

### Changes
- Fixed Streamlit runtime error in Knowledge Base viewer: removed nested expander usage by switching the outer Knowledge Base container from an expander to a toggle-controlled section (graph explorer contains expanders for Context and Entities).

### Files Modified
- `frontend/components/pdf_section.py`
- `DEVELOPMENT.md`

### Rationale
Streamlit does not allow expanders nested inside other expanders.

### Breaking Changes
None.

### Next Steps
- None.

---

## [2026-02-19] - FEATURE (UI modernization)

### Changes
- **Streamlit upgrade**: Bumped frontend from Streamlit 1.28.1 to 1.41.1 for latest features and performance.
- **Theme**: Updated `.streamlit/config.toml` with modern color palette (primary #4285F4, improved contrast backgrounds).
- **Knowledge graph display**: Replaced entity/relationship lists with a card-based **entity → relationship → entity** view. Each relationship is shown in a single card with color-coded entities (Person blue, Organization green, Location orange, Key Term purple, Other gray) and optional context. Summary metrics (entity count, relationship count) shown above the cards.
- **Document content removed**: Removed the "View extracted text" expander and raw PDF content display; UI now shows only the document filename and the extracted knowledge graph for cleaner UX.
- **Welcome page**: Header layout with title + caption and user/logout in a column layout; streamlined logout button.
- **CSS**: Added modern styling in `app.py` for knowledge graph cards (`.kg-card`, `.kg-entity`, `.kg-rel`, `.kg-context`), button hover effects, layout spacing, and file uploader appearance. Page title set to "Ship of Theseus" with wide layout.

### Files Modified
- `frontend/requirements.txt` – streamlit==1.41.1
- `frontend/.streamlit/config.toml` – theme colors
- `frontend/components/pdf_section.py` – `_render_knowledge_graph_section()` with entity-style map and card HTML; removed content display block; call `_render_knowledge_graph_section` instead of `_render_entities_with_relationships_section`
- `frontend/app.py` – page config (title, icon, wide layout); expanded custom CSS
- `frontend/components/welcome_page.py` – header columns, caption, logout in header
- `README.md` – feature description and Streamlit version
- `DEVELOPMENT.md` – this entry

### Rationale
- User request for modern Streamlit UI, result-only display (entity = relationship = entity), and removal of document content section for better UX.
- Color-coded cards make entity types and relationships easy to scan.

### Breaking Changes
None. Existing API and session state unchanged; only frontend presentation changed.

### Next Steps
- None.

---

## [2026-02-16] - FEATURE (Neo4j graph persistence)

### Changes
- **Neo4j integration**: Extracted knowledge graphs can be persisted to a Neo4j graph database. Each document's graph is stored separately and isolated by document filename.
- **Docker**: Added Neo4j 5.15 community service to `docker-compose.yml` with ports 7474 (HTTP) and 7687 (Bolt), persistent volume `neo4j_data`, and health check. Backend depends on Neo4j being healthy.
- **Backend**: New `Neo4jService` in `backend/app/services/neo4j_service.py` with `save_document_graph`, `get_document_graph`, `list_documents`, `delete_document_graph`, and `health_check`. Nodes use entity-type labels (Person, Organization, Location, KeyTerm) and `document_name` property; relationships use `RELATES` with `type` and `document_name`.
- **API**: New graph router at `/api/graph`: `POST /graph/save/{job_id}` (save extraction result to Neo4j), `GET /graph/list`, `GET /graph/{document_name}`, `DELETE /graph/{document_name}`, `GET /graph/health`. All require authentication.
- **Frontend**: "Add to Knowledge Base" button in the PDF section; shown when extraction is complete; calls `save_graph_to_neo4j(job_id)`; shows success message or error. API client methods: `save_graph_to_neo4j`, `get_graph_from_neo4j`, `list_neo4j_documents`, `delete_graph_from_neo4j`.
- **Config**: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` in `backend/app/core/config.py`. Created `backend/.env.example` with Neo4j and other backend variables.

### Files Modified
- `docker-compose.yml` – Added neo4j service, neo4j_data volume, backend depends_on neo4j
- `backend/requirements.txt` – Added neo4j>=5.15.0
- `backend/app/core/config.py` – Added NEO4J_* settings
- `backend/app/main.py` – Registered graph router; startup/shutdown Neo4j lifecycle (app.state.neo4j_service)
- `backend/app/services/neo4j_service.py` – Created
- `backend/app/api/v1/endpoints/graph.py` – Created
- `frontend/services/api_client.py` – Added Neo4j methods
- `frontend/components/pdf_section.py` – Store extraction_job_id; "Add to Knowledge Base" button; graph_saved_to_kb state; clear KB state on clear document and on new process
- `backend/.env.example` – Created
- `README.md` – Neo4j feature, project structure, env vars, API endpoints, Docker/Neo4j section
- `DEVELOPMENT.md` – This entry

### Rationale
- Users need to persist extracted graphs for later use; Redis cache is short-lived (1h TTL). Neo4j provides persistent graph storage. Document isolation by filename allows future fusion of graphs to be handled separately.

### Breaking Changes
None. Neo4j is optional; if unavailable, graph persistence endpoints return 503 and the UI button still works but save will fail with a clear error.

### Next Steps
- Optional: Knowledge Base page to list/visualize/delete saved graphs.
- Future: Separate process for merging/fusing multiple document graphs.

---

## [2026-02-16] - REFACTOR (Frontend)

### Changes
- **Removed entity-only fallback**: When relationship extraction fails or times out, the app no longer shows a minimal graph (nodes only, no edges). The app is used exclusively for knowledge graph extraction, so partial results are not shown.
- **Explicit error messaging**: If graph extraction fails, the user sees "Couldn't extract the knowledge graph." plus the specific reason (backend error, timeout, job expired, status check failure).
- **Error tracking**: `extraction_error_reason` captures failure causes during polling; `st.session_state.extraction_error` persists the message after rerun. Error is cleared when starting a new process or clearing the document.
- **Display**: When `extraction_error` is set, the PDF section shows only the error (no Entities & Relationships section). Graph results are shown only when extraction succeeds.

### Files Modified
- `frontend/components/pdf_section.py` – Removed fallback block that built minimal graph from entity-only result; added extraction_error_reason and extraction_error; display extraction_error in document section; clear extraction_error on clear document and on new process.

### Rationale
- App is for knowledge graph extraction only; entity-only output is not useful.
- Users should see a clear failure message and reason instead of misleading partial data.

### Breaking Changes
- If graph extraction previously failed, users used to see entities without relationships. They now see an error message and no graph output.

### Next Steps
- None.

---

## [2026-02-16] - REFACTOR

### Changes
- **Prompt management system**: Extracted hardcoded LLM prompts from services into JSON files and added a centralized PromptManager utility.
- **New directory**: `backend/app/prompts/` with `entity_extraction.json` and `relationship_extraction.json` (name, description, version, template, input_variables, metadata).
- **New module**: `backend/app/core/prompt_manager.py` – loads prompts from JSON, validates required fields, caches in memory; methods: `get_prompt(name)`, `get_template(name)`, `reload_prompt(name)`, `clear_cache()`.
- **Services updated**: `EntityExtractionService` and `RelationshipExtractionService` now use `PromptManager.get_prompt(...)` instead of inline template strings.

### Files Modified
- `backend/app/prompts/entity_extraction.json` – Created
- `backend/app/prompts/relationship_extraction.json` – Created
- `backend/app/core/prompt_manager.py` – Created
- `backend/app/services/entity_extraction_service.py` – Use PromptManager
- `backend/app/services/relationship_extraction_service.py` – Use PromptManager
- `README.md` – Project structure (prompts/, prompt_manager.py), new "Prompt Management" section
- `DEVELOPMENT.md` – This entry

### Rationale
- Prompts can be edited without touching Python code; better for iteration and non-developers.
- Single place to load and validate prompts; caching avoids repeated file I/O.
- Version and metadata in JSON support future prompt versioning or A/B testing.

### Breaking Changes
None. Behavior unchanged; prompts are loaded from files with same content as before.

### Next Steps
- None.

---

## [2026-02-16] - FEATURE

### Changes
- **Relationship extraction service**: New service that extracts relationships (Entity A, Relation, Entity B) from text, constrained to use only previously extracted entities. Source and target of every relationship must match existing nodes.
- **Automatic trigger**: After entity extraction completes, relationship extraction is automatically started (configurable via `AUTO_EXTRACT_RELATIONSHIPS`). Relationship job id is `{entity_job_id}_rel`.
- **Graph-ready output**: Results are returned as nodes (entities) and edges (relationships), suitable for graph DBs (e.g. Neo4j). Validation and deduplication of edges applied.
- **Parallel processing**: Relationship extraction runs in parallel batches with progress tracking in Redis (`RELATIONSHIP_EXTRACTION_BATCH_SIZE`).
- **New API endpoints**: `GET /entities/extract/relationships/status/{job_id}`, `GET /entities/extract/relationships/result/{job_id}`, `GET /entities/extract/graph/{job_id}` (graph uses entity job_id and returns when relationship job has completed).
- **New schemas**: `Relationship`, `ExtractedRelationships`, `GraphNode`, `GraphEdge`, `DocumentGraph`, `RelationshipJobStatus` in `backend/app/schemas/relationships.py`.
- **Cache**: New cache key `cache_key_relationship_job(job_id)` for relationship jobs.
- **Config**: `RELATIONSHIP_EXTRACTION_BATCH_SIZE`, `AUTO_EXTRACT_RELATIONSHIPS` in settings; documented in `.env.example`.

### Files Modified
- `backend/app/schemas/relationships.py` – Created
- `backend/app/services/relationship_extraction_service.py` – Created
- `backend/app/core/cache.py` – Added `cache_key_relationship_job`
- `backend/app/core/config.py` – Added `RELATIONSHIP_EXTRACTION_BATCH_SIZE`, `AUTO_EXTRACT_RELATIONSHIPS`
- `backend/app/api/v1/endpoints/entities.py` – Auto-trigger relationship task after entity extraction; added `_run_relationship_task`; added relationship status, result, and graph endpoints
- `.env.example` – Created/updated with relationship extraction variables
- `README.md` – Features, project structure, env vars, API endpoints, Redis keys
- `DEVELOPMENT.md` – This entry

### Rationale
- Graph RAG indexing requires both entities and relationships; constraining relationships to extracted entities keeps the graph consistent.
- Single flow: user starts entity extraction once; relationship extraction follows automatically.
- Graph-ready format (nodes + edges) supports downstream use (e.g. Neo4j, visualization).

### Breaking Changes
None. New endpoints and optional config; existing entity extraction flow unchanged.

### Next Steps
- None (frontend now polls graph and displays entities with relationships).

---

## [2026-02-16] - FEATURE (Frontend)

### Changes
- **Replaced "Extracted Entities" with "Entities & Relationships"**: The PDF section now shows entities (nodes) with their relationships (edges) in a single expander. Entities are grouped by type (Person, Organization, Location, Key term); relationships are listed as **Source** — *relation_type* → **Target** with optional context.
- **Process flow**: After entity extraction completes, the frontend polls `GET /entities/extract/graph/{job_id}` until the graph is ready (relationship extraction runs automatically on the backend). Progress shows "Extracting entities" then "Extracting relationships..." then "Entities and relationships ready."
- **Fallback**: If the graph is not ready before timeout, a minimal graph is built from the entity extraction result (nodes only, no edges) so the section still displays.
- **API client**: Added `get_extraction_graph(job_id, token)` to fetch the graph (nodes + edges).

### Files Modified
- `frontend/services/api_client.py` – Added `get_extraction_graph`
- `frontend/components/pdf_section.py` – Replaced `_aggregate_entities` / `_render_entities_section` with `_render_entities_with_relationships_section`; process flow now waits for graph after entity extraction; session state `extraction_results` stores graph data (nodes, edges)
- `README.md` – Feature description updated

### Rationale
- User request to show entities together with their relationships in one place.
- Aligns UI with backend graph output (nodes + edges).

### Breaking Changes
None. Section title and content changed; session state key `extraction_results` now holds graph-shaped data instead of raw entity chunks.

---

## [2026-02-14] - FEATURE

### Changes
- **Entity extraction after upload**: Clicking "Process Document" now uploads the PDF and immediately starts entity extraction. The UI polls extraction status and shows a progress bar until completion (timeout 5 minutes).
- **API client**: Added `start_entity_extraction`, `get_extraction_status`, and `get_extraction_result` to the frontend `APIClient` for the existing entity endpoints.
- **Extracted entities section**: When extraction completes, results are stored in session state and displayed in an expandable "📊 Extracted Entities" section (People, Organizations, Locations, Dates, Key terms). Entities are aggregated and deduplicated across chunks.
- **Session state**: `extraction_results` is set when extraction completes, cleared when the user clears the document or processes a new document.

### Files Modified
- `frontend/services/api_client.py` – Added three entity extraction API methods
- `frontend/components/pdf_section.py` – New process flow (upload → start extraction → poll with progress → fetch result → display); added `_aggregate_entities` and `_render_entities_section`; clear extraction_results on document clear
- `README.md` – Feature list updated for Process Document + entity display
- `DEVELOPMENT.md` – This entry

### Rationale
- Single action for the user: one click to upload and extract entities.
- Progress feedback improves UX for long-running extraction.
- Entities in a separate expander keep the page organized.

### Breaking Changes
None

### Next Steps
None

---

## [2026-02-14] - FEATURE

### Changes
- **Redis cache**: Added Redis as project-wide cache (Docker Compose service). Cache layer in `backend/app/core/cache.py` with `cache_get`, `cache_set`, `cache_delete`; falls back to in-memory when `REDIS_URL` is not set.
- **Documents in Redis**: Document upload/current/delete now use Redis (key `documents:{user_id}`, TTL 24h). Removed in-memory `_documents_cache`.
- **Entity extraction parallel + progress**: Entity extraction runs in parallel batches (`ENTITY_EXTRACTION_BATCH_SIZE`, default 5). Progress and result stored in Redis (`extraction:job:{job_id}`, TTL 1h). New endpoints:
  - `POST /api/entities/extract` – start extraction, returns `job_id`
  - `GET /api/entities/extract/status/{job_id}` – progress (status, completed_chunks, total_chunks)
  - `GET /api/entities/extract/result/{job_id}` – result when completed (202 if still running)
- **Background task**: Extraction runs in FastAPI `BackgroundTasks`; clients poll status/result.

### Files Modified
- `docker-compose.yml` – Added `redis` service; backend `depends_on` redis, env `REDIS_URL`
- `backend/app/core/config.py` – `REDIS_URL`, `ENTITY_EXTRACTION_BATCH_SIZE`
- `backend/app/core/cache.py` – New: Redis + in-memory cache abstraction
- `backend/app/api/v1/endpoints/documents.py` – Use cache for document storage
- `backend/app/api/v1/endpoints/entities.py` – Rewritten: POST extract (job_id), GET status, GET result
- `backend/app/services/entity_extraction_service.py` – Added `extract_entities_async`, `extract_from_chunks_parallel` with Redis progress updates
- `backend/app/schemas/entities.py` – Added `ExtractionJobStatus`, `ExtractionJobStarted`
- `backend/app/main.py` – Registered entities router
- `backend/requirements.txt` – Added `langchain-openai`, `redis`
- `README.md` – Features, project structure, API endpoints, env vars, Docker/Redis section
- `DEVELOPMENT.md` – This entry

### Rationale
- Single cache backend (Redis) for documents and extraction jobs; persistence across restarts when using Docker.
- Parallel extraction reduces latency for large documents; progress tracking improves UX.
- Optional Redis allows local dev without Docker (in-memory fallback).

### Dependencies Added
- `langchain-openai==0.2.0`
- `redis>=5.0.0`

### Breaking Changes
- Document storage is no longer in-process memory. With Redis, documents are in Redis; without Redis, they are in a new in-memory cache (lost on restart as before). API contract unchanged.
- Entity extraction is now async (job-based). Old synchronous `POST /extract` returning `DocumentEntities` is replaced by POST → `job_id`, then GET status/result.

---

## [2026-02-13] - CONFIG

### Changes
- Console logger now includes `{extra}` (structured log fields) when `DEBUG` is True
- Enables viewing keyword-argument data (e.g. `chunks`, `user`) directly in the terminal during development

### Files Modified
- `backend/app/core/logger.py` - Conditional console format with `{extra}` in DEBUG mode

### Rationale
- Best for dev: see structured log data in the console without parsing files or JSON
- Only in DEBUG to avoid noisy output in production

### Breaking Changes
None

---

## [2026-02-13 20:15] - FEATURE

### Changes
- Integrated Loguru as the logging solution for the entire project
- Added `loguru==0.7.2` to both backend and frontend requirements
- Created logger configuration modules:
  - `backend/app/core/logger.py` - Backend logging configuration
  - `frontend/utils/logger.py` - Frontend logging configuration
- Updated FastAPI main.py to initialize logging on startup
- Added comprehensive logging section to cursor rules (`.cursor/rules/cursorrules.mdc`)
- Configured automatic log rotation at midnight
- Set up log retention policies (30 days for general logs, 90 days for errors)
- Enabled automatic compression of old logs
- Implemented colored console output for better readability
- Created separate log files for backend and frontend in `logs/` directory

### Files Modified
- `backend/requirements.txt` - Added loguru==0.7.2
- `frontend/requirements.txt` - Added loguru==0.7.2
- `backend/app/core/logger.py` - Created (58 lines)
- `frontend/utils/logger.py` - Created (43 lines)
- `backend/app/main.py` - Imported logger and added startup logging
- `.cursor/rules/cursorrules.mdc` - Added comprehensive Loguru logging section (150+ lines)
- `README.md` - Added logging documentation and features
- `DEVELOPMENT.md` - Added this entry

### Rationale
- Loguru provides a modern, simple, and powerful logging solution
- No complex configuration needed compared to standard Python logging
- Beautiful colored console output improves debugging experience
- Automatic file rotation and compression reduces maintenance
- Thread-safe by default, important for FastAPI async operations
- Unique features like `logger.success()` and `@logger.catch` decorator
- Consistent logging approach across backend and frontend
- Better developer experience with less boilerplate

### Technical Details
- **Log Levels:**
  - Console: DEBUG (if DEBUG=True), INFO (if DEBUG=False)
  - File: DEBUG (all messages)
  - Error file: ERROR and above
- **Log Format:**
  - Console: Colored with timestamp, level, module, function, line, and message
  - File: Same information without colors
- **Rotation:** Daily at midnight
- **Retention:** 30 days (general), 90 days (errors)
- **Compression:** ZIP format for old logs
- **Thread-safe:** Enabled with `enqueue=True`

### Dependencies Added
- `loguru==0.7.2` (backend and frontend)

### Breaking Changes
None - this is a new addition to the project

### Usage Examples
```python
# Backend
from app.core.logger import logger

logger.info("User logged in", user_id=user.id)
logger.success("Document uploaded successfully")
logger.error("Failed to process request", error=str(e))

# Frontend
from utils.logger import logger

logger.info("Page navigation", page="dashboard")
logger.warning("API request failed")
```

### Next Steps
- Add logging to existing endpoints and functions
- Implement request/response logging middleware
- Add structured logging for API requests with request IDs
- Consider log aggregation service for production
- Add log monitoring and alerting

---

## [2026-02-12 22:54] - FEATURE

### Changes
- Added PDF document upload and retrieval functionality
- Implemented document management endpoints in backend:
  - `POST /api/documents/upload` - Upload PDF and extract text
  - `GET /api/documents/current` - Retrieve stored document
  - `DELETE /api/documents/current` - Clear stored document
- Created PDF upload section component in frontend
- Integrated PDF section into welcome page for authenticated users
- Implemented in-memory document storage (per-user)
- Added PDF text extraction using PyPDF2
- Enhanced API client with document management methods

### Files Modified
- `backend/app/api/v1/endpoints/documents.py` - New document endpoints (117 lines)
- `backend/app/main.py` - Added documents router
- `frontend/components/pdf_section.py` - PDF upload UI component (91 lines)
- `frontend/components/welcome_page.py` - Integrated PDF section
- `frontend/services/api_client.py` - Added upload_pdf(), get_current_document(), clear_current_document() methods (83 lines added)

### Rationale
- Enables users to upload and process PDF documents through the web interface
- Text extraction allows for future features like search, analysis, or AI processing
- In-memory storage provides quick access without database complexity for MVP
- Per-user storage ensures document privacy and separation
- File size limit (10MB) and type validation prevent abuse

### Technical Details
- Uses PyPDF2 library for PDF text extraction
- Maximum file size: 10MB
- Only PDF content type accepted
- Document stored per user (keyed by email)
- Stateful session management in Streamlit for UI updates

### Dependencies Added
- `PyPDF2` - PDF text extraction library

### Breaking Changes
None

### Next Steps
- Consider persistent storage (database or file system) for production
- Add document history/versioning
- Implement document search and filtering
- Add support for other document formats (DOCX, TXT)
- Add document sharing between users
- Implement document processing/analysis features

---

## [2026-02-13 19:50] - DOCS

### Changes
- Updated DEVELOPMENT.md with entry for PDF upload feature (commit e3cae60)
- Updated README.md to document PDF upload functionality:
  - Added PDF document upload to features list
  - Documented document management API endpoints
  - Updated project structure to show new files (documents.py, pdf_section.py)
- Ensured documentation consistency across the project

### Files Modified
- `DEVELOPMENT.md` - Added detailed entry for PDF upload feature from Feb 12 commit
- `README.md` - Added PDF features, endpoints, and updated project structure

### Rationale
- Following project documentation standards that require updating both DEVELOPMENT.md and README.md
- Ensures all features are properly documented for future developers
- Maintains accurate project structure representation
- Provides clear API endpoint documentation for users

### Breaking Changes
None - documentation updates only

### Next Steps
- Continue documenting all future features immediately after implementation
- Keep DEVELOPMENT.md synchronized with git commits

---

## [2026-02-13 19:45] - CONFIG

### Changes
- Restructured Cursor configuration to use `.cursor/rules/` directory
- Moved cursor rules to `.mdc` format for better organization
- Created comprehensive rule files:
  - `context.mdc` - Project context for AI assistant
  - `cursorrules.mdc` - Main cursor rules
  - `DEVELOPMENT.mdc` - Development guidelines
  - `README.mdc` - Project documentation standards
- Created root-level `DEVELOPMENT.md` for tracking project changes
- Created `.env.example` template file
- Updated README.md to reflect new documentation structure

### Files Modified
- `README.md` - Updated documentation links
- `.cursor/rules/context.mdc` - Created
- `.cursor/rules/cursorrules.mdc` - Created
- `.cursor/rules/DEVELOPMENT.mdc` - Created
- `.cursor/rules/README.mdc` - Created
- `DEVELOPMENT.md` - Created (this file)
- `.env.example` - Created

### Rationale
- Improved organization of cursor rules using dedicated directory
- Better separation of concerns with multiple focused rule files
- Using `.mdc` extension for markdown files specific to cursor
- Root-level DEVELOPMENT.md makes changelog more accessible
- .env.example provides clear template for environment configuration

### Breaking Changes
None - this is organizational restructuring

### Next Steps
- Continue development following the new cursor rules structure
- Update DEVELOPMENT.md after each significant change
- Keep README.md in sync with project changes

---

## [2026-02-16 18:50] - BUGFIX

### Changes
- Fixed Neo4j connectivity issue in Docker environment
- Updated `.env.example` with correct Neo4j configuration for Docker
- Clarified Neo4j connection URI documentation in README.md
- Added emphasis on using service name `neo4j` instead of `localhost` when running in Docker

### Files Modified
- `.env.example` - Created with proper Neo4j Docker configuration
- `README.md` - Enhanced Neo4j environment variable documentation with Docker-specific notes

### Rationale
The backend container was trying to connect to Neo4j at `bolt://localhost:7687`, which failed because in Docker's internal network, the backend must use the service name `bolt://neo4j:7687` (from docker-compose.yml). This caused:
- Neo4j health check failures on startup
- 503 Service Unavailable errors when trying to save graphs
- Authentication failures logged by Neo4j container

The fix ensures proper service-to-service communication within Docker's network by using the correct service name in the connection URI.

### Breaking Changes
None - only affects configuration. Existing users need to update their `.env` file with `NEO4J_URI=bolt://neo4j:7687` and restart backend container.

### Next Steps
- Users should update their `.env` file with the correct `NEO4J_URI=bolt://neo4j:7687`
- Restart backend container with `docker-compose restart backend`
- Verify Neo4j connectivity with `GET /api/graph/health` endpoint

---

## Previous Development

The project was initialized with:
- FastAPI backend with JWT authentication
- Streamlit frontend with login components
- Docker Compose orchestration
- Modular architecture with clean separation of concerns
- Component-based frontend design
- Comprehensive test structure

For detailed guidelines on maintaining this file, see [.cursor/rules/DEVELOPMENT.mdc](.cursor/rules/DEVELOPMENT.mdc).
