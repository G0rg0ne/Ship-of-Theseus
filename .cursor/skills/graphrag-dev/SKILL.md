---
name: graphrag-dev
description: Guides development work on the Ship of Theseus GraphRAG pipeline — adding or modifying entity extraction, community detection, summarisation, embedding, or Neo4j persistence. Use when the user wants to change the knowledge-brain pipeline, add a new pipeline step, tune LLM prompts, modify Neo4j graph schema, or debug extraction/embedding issues.
---

# GraphRAG Dev Workflow

## Before touching pipeline code

1. Read `graphrag-pipeline.mdc` rule (`.cursor/rules/graphrag-pipeline.mdc`) for the canonical pipeline overview and data-scoping rules.
2. Identify which service owns the change (see service table in that rule).
3. Check `brain_pipeline_service.py` — all steps must flow through it.

## Changing a Prompt

Edit the JSON in `backend/app/prompts/`:

```bash
# hot-reload without restart (from a Python shell or test)
from app.core.prompt_manager import PromptManager
PromptManager.reload_prompt("entity_extraction")
```

- Keep `input_variables` in sync with the template placeholders.
- Bump the `version` field in the JSON after meaningful changes.

## Adding a New Pipeline Step

```
1. Write service in backend/app/services/my_step_service.py
2. Import and call it from brain_pipeline_service.py
3. Add Redis progress write:  await cache.set(f"pipeline:{job_id}:step", "my_step")
4. Add the step name to GET /graph/pipeline/status/{id} response schema
5. Add a label to ProcessingSteps.tsx in the frontend
6. Update graphrag-pipeline.mdc with the new step
```

## Modifying Neo4j Schema

- Always scope nodes by `user_id` (source graph) or `derived_user_id` (community nodes).
- New node labels → add to `neo4j_service.py`; check existing Cypher queries for `MATCH` patterns that may need updating.
- Vector index dimensions are derived from `EMBEDDING_MODEL` at runtime — never hard-code `1536`.

## Debugging Pipeline Failures

```bash
# Watch backend logs live
docker compose logs -f backend

# Inspect a job's Redis state
docker compose exec redis redis-cli get "extraction:job:<job_id>"
docker compose exec redis redis-cli get "community:brain:<user_id>"

# Check Neo4j directly
# Open http://localhost:7474 → run Cypher
MATCH (n {user_id: "<uuid>"}) RETURN n LIMIT 25
```

Common failure points:
- `OPENAI_API_KEY` not set → extraction returns 503
- Neo4j Bolt port wrong in `.env` when using Docker (`bolt://neo4j:7687` not `localhost`)
- Rate-limit burst during summarisation → lower `COMMUNITY_SUMMARIZATION_CONCURRENCY`

## Testing Pipeline Changes

```bash
cd backend
pytest tests/backend/ -v

# Run just pipeline-related tests
pytest tests/backend/ -k "pipeline or extraction or community"
```

Mock OpenAI and Neo4j calls in unit tests; reserve integration tests for local runs with live services.

## Checklist After Pipeline Changes

- [ ] `brain_pipeline_service.py` is the single code path (no duplicate logic in endpoints)
- [ ] New env vars documented in `README.md` and `.env.example`
- [ ] `graphrag-pipeline.mdc` updated if architecture changed
- [ ] `DEVELOPMENT.md` entry added
