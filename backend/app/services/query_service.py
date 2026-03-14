"""
GraphRAG query pipeline: Intent Router → Retrieval → Context Pruning → LLM Synthesis.

Uses LangChain for router and synthesis. Conversation history is persisted in Redis
and loaded each request, then passed to the synthesis LLM as context.
"""
import asyncio
import hashlib
import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.cache import (
    cache_get,
    cache_set,
    cache_key_chat_history,
    cache_key_query_answer,
)
from app.core.config import settings
from app.core.logger import logger
from app.core.prompt_manager import PromptManager
from app.schemas.query import QueryResponse, SourceAttribution


def _human_content_to_question(content: str) -> str:
    """If content is legacy 'Context:... Question: ...' format, return only the question part."""
    if not content or "Question:" not in content:
        return content
    parts = content.split("Question:", 1)
    if len(parts) == 2:
        return parts[1].strip()
    return content


def _router_output_parser(raw: str) -> Tuple[str, List[str]]:
    """Parse router LLM output to category and extracted_entities. Returns (category, entities)."""
    category = "hybrid"
    entities: List[str] = []
    raw = (raw or "").strip()
    if not raw:
        return category, entities
    try:
        # Try to extract JSON from the response (might be wrapped in markdown)
        if "```" in raw:
            start = raw.find("```")
            if start >= 0:
                raw = raw[start:].replace("```json", "").replace("```", "").strip()
        obj = json.loads(raw)
        category = (obj.get("category") or "hybrid").lower()
        if category not in ("global", "local", "hybrid"):
            category = "hybrid"
        entities = obj.get("extracted_entities") or []
        if not isinstance(entities, list):
            entities = [e for e in (entities,) if isinstance(e, str)]
        else:
            entities = [str(e).strip() for e in entities if e]
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Router output parse failed, using hybrid", raw=raw[:200], error=str(e))
    return category, entities


def _build_context_and_sources(
    communities: List[Dict[str, Any]],
    triplets: List[Dict[str, Any]],
    threshold: float,
) -> Tuple[str, List[SourceAttribution]]:
    """Prune by score, deduplicate, build context string and sources list."""
    lines: List[str] = []
    sources: List[SourceAttribution] = []
    seen_community: set = set()
    seen_entity: set = set()
    max_summary_chars = getattr(settings, "QUERY_MAX_SUMMARY_CHARS", 800)

    for c in communities:
        if c.get("score", 0) < threshold:
            continue
        cid = c.get("community_id") or ""
        if not cid or cid in seen_community:
            continue
        seen_community.add(cid)
        summary = c.get("summary") or ""
        level = c.get("level") or ""
        summary_text = summary[:max_summary_chars] + ("…" if len(summary) > max_summary_chars else "")
        lines.append(f"[Community {cid} (level: {level})]\n{summary_text}")
        sources.append(
            SourceAttribution(
                type="community",
                id=cid,
                level=level,
                excerpt=(summary[:200] + "…") if len(summary) > 200 else summary,
            )
        )

    for t in triplets:
        src = t.get("source_label") or ""
        rel = t.get("relation_type") or ""
        tgt = t.get("target_label") or ""
        ttype = t.get("target_entity_type") or ""
        if not (src and rel and tgt):
            continue
        key = (src, rel, tgt)
        if key in seen_entity:
            continue
        seen_entity.add(key)
        lines.append(f"- {src} --[{rel}]--> {tgt} ({ttype})")
        if not any(s.type == "entity" and s.label == src for s in sources):
            sources.append(
                SourceAttribution(type="entity", id=src, label=src)
            )

    context = "\n\n".join(lines) if lines else "(No relevant context retrieved.)"
    return context, sources


async def run_query_pipeline(
    user_id: str,
    question: str,
    mode: str,
    session_id: Optional[str],
    neo4j_service: Any,
    embedding_service: Any,
) -> QueryResponse:
    """
    Run the full 4-stage GraphRAG query pipeline and return the synthesized answer with sources.

    mode: "auto" (use router), "global", "local", or "hybrid"
    session_id: optional; generated if not provided. Used for conversation history.
    """
    session_id = session_id or str(uuid.uuid4())
    router_model = getattr(settings, "QUERY_ROUTER_MODEL", "gpt-4o-mini")
    synthesis_model = getattr(settings, "QUERY_SYNTHESIS_MODEL", "gpt-4o-mini")
    entity_top_k = getattr(settings, "QUERY_ENTITY_TOP_K", 15)
    community_top_k = getattr(settings, "QUERY_COMMUNITY_TOP_K", 10)
    threshold = getattr(settings, "QUERY_SIMILARITY_THRESHOLD", 0.7)
    ttl = getattr(settings, "CHAT_HISTORY_TTL_SECONDS", 86400)
    history_window = getattr(settings, "CHAT_HISTORY_WINDOW", 6)
    answer_cache_ttl = getattr(settings, "QUERY_ANSWER_CACHE_TTL", 3600)

    # --- 0. Answer cache (skip pipeline for repeated identical questions) ---
    cache_fingerprint = f"{mode}|{session_id or ''}|{question}".encode("utf-8")
    question_hash = hashlib.sha256(cache_fingerprint).hexdigest()
    answer_cache_key = cache_key_query_answer(user_id, question_hash)
    cached_response = await cache_get(answer_cache_key)
    if isinstance(cached_response, dict):
        try:
            response = QueryResponse(
                answer=cached_response.get("answer", ""),
                mode_used=cached_response.get("mode_used", "hybrid"),
                session_id=session_id,
                sources=cached_response.get("sources") or [],
            )
            # Append this Q&A to chat history so conversation stays consistent
            cache_key = cache_key_chat_history(user_id, session_id)
            raw_history = await cache_get(cache_key)
            history_list = list(raw_history) if isinstance(raw_history, list) else []
            history_list.append({"role": "user", "content": question})
            history_list.append({"role": "assistant", "content": response.answer})
            await cache_set(cache_key, history_list[-(history_window * 2) :], ttl_seconds=ttl)
            return response
        except Exception as e:
            logger.opt(exception=True).debug(
                "Cache hit parse failed, running full pipeline: {}", e
            )

    # --- 1. Intent Router (when mode is auto) ---
    if mode == "auto":
        router_prompt_data = PromptManager.get_prompt("query_router")
        router_template = router_prompt_data["template"]
        router_input_vars = router_prompt_data["input_variables"]
        from langchain.prompts import PromptTemplate
        from langchain_openai import ChatOpenAI as RouterLLM
        router_prompt = PromptTemplate(
            template=router_template,
            input_variables=router_input_vars,
        )
        router_llm = RouterLLM(
            model=router_model,
            temperature=0,
            openai_api_key=settings.OPENAI_API_KEY or "",
        )
        router_chain = router_prompt | router_llm
        router_result = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: router_chain.invoke({"query": question}),
        )
        router_text = router_result.content if hasattr(router_result, "content") else str(router_result)
        category, _ = _router_output_parser(router_text)
    else:
        category = mode if mode in ("global", "local", "hybrid") else "hybrid"

    mode_used = category

    # --- 2. Embed query and run retrieval ---
    loop = asyncio.get_running_loop()
    query_vectors = await loop.run_in_executor(
        None,
        lambda: embedding_service.embed_texts([question]),
    )
    query_vector = query_vectors[0] if query_vectors else []

    communities: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    triplets: List[Dict[str, Any]] = []

    if category in ("global", "hybrid"):
        communities = await loop.run_in_executor(
            None,
            lambda: neo4j_service.vector_search_communities(
                user_id, query_vector, community_top_k
            ),
        )
    if category in ("local", "hybrid"):
        entities = await loop.run_in_executor(
            None,
            lambda: neo4j_service.vector_search_entities(
                user_id, query_vector, entity_top_k
            ),
        )
        if entities:
            entity_keys = [
                {"user_id": e["user_id"], "document_name": e["document_name"], "id": e["id"]}
                for e in entities
                if e.get("id") and e.get("user_id") is not None and e.get("document_name") is not None
            ]
            if entity_keys:
                triplets = await loop.run_in_executor(
                    None,
                    lambda: neo4j_service.get_entity_neighborhood(entity_keys),
                )

    # --- 3. Context pruning and source list ---
    context, sources = _build_context_and_sources(communities, triplets, threshold)

    # --- 4. Load chat history from Redis and prepare for synthesis ---
    cache_key = cache_key_chat_history(user_id, session_id)
    raw_history = await cache_get(cache_key)
    history_messages: List[Any] = []
    if isinstance(raw_history, list):
        for item in raw_history:
            if not isinstance(item, dict):
                continue
            role = (item.get("role") or "").lower()
            content = item.get("content") or ""
            if role in ("human", "user"):
                # Strip legacy "Context:... Question: ..." to just the question for token savings
                content = _human_content_to_question(content)
                history_messages.append(HumanMessage(content=content))
            elif role in ("ai", "assistant"):
                history_messages.append(AIMessage(content=content))
        # Keep only the last N turns to cap token usage
        history_messages = history_messages[-history_window:]

    synthesis_prompt_data = PromptManager.get_prompt("query_synthesis")
    system_text = synthesis_prompt_data.get("system") or "Answer using only the provided context. Cite sources."
    human_template = synthesis_prompt_data.get("template") or "Context:\n\n{context}\n\nQuestion: {question}\n\nAnswer:"
    current_human_content = human_template.format(context=context, question=question)

    # Build message list: system + conversation history + current turn (human message)
    messages_for_llm: List[Any] = [
        SystemMessage(content=system_text),
        *history_messages,
        HumanMessage(content=current_human_content),
    ]
    synthesis_llm = ChatOpenAI(
        model=synthesis_model,
        temperature=0.2,
        openai_api_key=settings.OPENAI_API_KEY or "",
    )
    result = await synthesis_llm.ainvoke(messages_for_llm)
    answer = result.content if hasattr(result, "content") else str(result)

    # Append current turn to history and persist to Redis (store only bare question for human to save tokens)
    history = InMemoryChatMessageHistory()
    for m in history_messages:
        history.add_message(m)
    history.add_message(HumanMessage(content=question))
    history.add_message(AIMessage(content=answer))
    to_save = []
    for m in history.messages:
        role = "user" if getattr(m, "type", None) == "human" else "assistant"
        content = getattr(m, "content", str(m))
        to_save.append({"role": role, "content": content})
    await cache_set(cache_key, to_save, ttl_seconds=ttl)

    response = QueryResponse(
        answer=answer.strip(),
        mode_used=mode_used,
        session_id=session_id,
        sources=sources,
    )
    await cache_set(answer_cache_key, response.model_dump(), ttl_seconds=answer_cache_ttl)
    return response


async def run_query_pipeline_stream(
    user_id: str,
    question: str,
    mode: str,
    session_id: Optional[str],
    neo4j_service: Any,
    embedding_service: Any,
) -> AsyncIterator[Dict[str, Any]]:
    """
    Same as run_query_pipeline but streams synthesis tokens. Yields {"type": "chunk", "content": "..."}
    then {"type": "done", "answer": "...", "mode_used": "...", "session_id": "...", "sources": [...]}.
    On cache hit yields a single "done" event.
    """
    session_id = session_id or str(uuid.uuid4())
    router_model = getattr(settings, "QUERY_ROUTER_MODEL", "gpt-4o-mini")
    synthesis_model = getattr(settings, "QUERY_SYNTHESIS_MODEL", "gpt-4o-mini")
    entity_top_k = getattr(settings, "QUERY_ENTITY_TOP_K", 15)
    community_top_k = getattr(settings, "QUERY_COMMUNITY_TOP_K", 10)
    threshold = getattr(settings, "QUERY_SIMILARITY_THRESHOLD", 0.7)
    ttl = getattr(settings, "CHAT_HISTORY_TTL_SECONDS", 86400)
    history_window = getattr(settings, "CHAT_HISTORY_WINDOW", 6)
    answer_cache_ttl = getattr(settings, "QUERY_ANSWER_CACHE_TTL", 3600)

    cache_fingerprint = f"{mode}|{session_id or ''}|{question}".encode("utf-8")
    question_hash = hashlib.sha256(cache_fingerprint).hexdigest()
    answer_cache_key = cache_key_query_answer(user_id, question_hash)
    cached_response = await cache_get(answer_cache_key)
    if isinstance(cached_response, dict):
        try:
            response = QueryResponse(
                answer=cached_response.get("answer", ""),
                mode_used=cached_response.get("mode_used", "hybrid"),
                session_id=session_id,
                sources=cached_response.get("sources") or [],
            )
            cache_key = cache_key_chat_history(user_id, session_id)
            raw_history = await cache_get(cache_key)
            history_list = list(raw_history) if isinstance(raw_history, list) else []
            history_list.append({"role": "user", "content": question})
            history_list.append({"role": "assistant", "content": response.answer})
            await cache_set(cache_key, history_list[-(history_window * 2) :], ttl_seconds=ttl)
            yield {
                "type": "done",
                "answer": response.answer,
                "mode_used": response.mode_used,
                "session_id": response.session_id,
                "sources": [s.model_dump() if hasattr(s, "model_dump") else s for s in response.sources],
            }
            return
        except Exception as e:
            logger.opt(exception=True).debug(
                "Cache hit parse failed (streaming), running full pipeline: {}", e
            )

    loop = asyncio.get_running_loop()
    if mode == "auto":
        router_prompt_data = PromptManager.get_prompt("query_router")
        router_template = router_prompt_data["template"]
        router_input_vars = router_prompt_data["input_variables"]
        from langchain.prompts import PromptTemplate
        from langchain_openai import ChatOpenAI as RouterLLM
        router_prompt = PromptTemplate(
            template=router_template,
            input_variables=router_input_vars,
        )
        router_llm = RouterLLM(
            model=router_model,
            temperature=0,
            openai_api_key=settings.OPENAI_API_KEY or "",
        )
        router_chain = router_prompt | router_llm
        router_result = await loop.run_in_executor(
            None,
            lambda: router_chain.invoke({"query": question}),
        )
        router_text = router_result.content if hasattr(router_result, "content") else str(router_result)
        category, _ = _router_output_parser(router_text)
    else:
        category = mode if mode in ("global", "local", "hybrid") else "hybrid"

    mode_used = category

    query_vectors = await loop.run_in_executor(
        None,
        lambda: embedding_service.embed_texts([question]),
    )
    query_vector = query_vectors[0] if query_vectors else []

    communities: List[Dict[str, Any]] = []
    entities: List[Dict[str, Any]] = []
    triplets: List[Dict[str, Any]] = []

    if category in ("global", "hybrid"):
        communities = await loop.run_in_executor(
            None,
            lambda: neo4j_service.vector_search_communities(
                user_id, query_vector, community_top_k
            ),
        )
    if category in ("local", "hybrid"):
        entities = await loop.run_in_executor(
            None,
            lambda: neo4j_service.vector_search_entities(
                user_id, query_vector, entity_top_k
            ),
        )
        if entities:
            entity_keys = [
                {"user_id": e["user_id"], "document_name": e["document_name"], "id": e["id"]}
                for e in entities
                if e.get("id") and e.get("user_id") is not None and e.get("document_name") is not None
            ]
            if entity_keys:
                triplets = await loop.run_in_executor(
                    None,
                    lambda: neo4j_service.get_entity_neighborhood(entity_keys),
                )

    context, sources = _build_context_and_sources(communities, triplets, threshold)

    cache_key = cache_key_chat_history(user_id, session_id)
    raw_history = await cache_get(cache_key)
    history_messages = []
    if isinstance(raw_history, list):
        for item in raw_history:
            if not isinstance(item, dict):
                continue
            role = (item.get("role") or "").lower()
            content = item.get("content") or ""
            if role in ("human", "user"):
                content = _human_content_to_question(content)
                history_messages.append(HumanMessage(content=content))
            elif role in ("ai", "assistant"):
                history_messages.append(AIMessage(content=content))
        history_messages = history_messages[-history_window:]

    synthesis_prompt_data = PromptManager.get_prompt("query_synthesis")
    system_text = synthesis_prompt_data.get("system") or "Answer using only the provided context. Cite sources."
    human_template = synthesis_prompt_data.get("template") or "Context:\n\n{context}\n\nQuestion: {question}\n\nAnswer:"
    current_human_content = human_template.format(context=context, question=question)

    messages_for_llm: List[Any] = [
        SystemMessage(content=system_text),
        *history_messages,
        HumanMessage(content=current_human_content),
    ]
    synthesis_llm = ChatOpenAI(
        model=synthesis_model,
        temperature=0.2,
        openai_api_key=settings.OPENAI_API_KEY or "",
    )

    full_answer = ""
    async for chunk in synthesis_llm.astream(messages_for_llm):
        piece = chunk.content if hasattr(chunk, "content") else str(chunk)
        if piece:
            full_answer += piece
            yield {"type": "chunk", "content": piece}

    answer = full_answer.strip()

    history = InMemoryChatMessageHistory()
    for m in history_messages:
        history.add_message(m)
    history.add_message(HumanMessage(content=question))
    history.add_message(AIMessage(content=answer))
    to_save = []
    for m in history.messages:
        role = "user" if getattr(m, "type", None) == "human" else "assistant"
        content = getattr(m, "content", str(m))
        to_save.append({"role": role, "content": content})
    await cache_set(cache_key, to_save, ttl_seconds=ttl)

    response = QueryResponse(
        answer=answer,
        mode_used=mode_used,
        session_id=session_id,
        sources=sources,
    )
    await cache_set(answer_cache_key, response.model_dump(), ttl_seconds=answer_cache_ttl)

    yield {
        "type": "done",
        "answer": response.answer,
        "mode_used": response.mode_used,
        "session_id": response.session_id,
        "sources": [s.model_dump() for s in response.sources],
    }
