"""
LLM-based summarization service for knowledge graph communities.

Generates a comprehensive report for each community at every hierarchy level
using the prompt template in community_summary.json.

Within each hierarchy level all communities are independent, so they are
summarized concurrently using a thread pool (one LLM client per thread to
avoid lazy-init races). Levels are still processed in order: leaf → mid → root,
because mid/root summaries depend on their children's summaries.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Awaitable, Callable, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.core.prompt_manager import PromptManager
from app.schemas.community import CommunityLevel

MAX_SUMMARIZATION_WORKERS = 10
DEFAULT_ASYNC_CONCURRENCY = 50


def _format_entities(nodes: List[Dict[str, Any]]) -> str:
    """Format node list for the prompt (label, type, optional description)."""
    lines: List[str] = []
    for n in nodes:
        label = n.get("label") or n.get("id") or ""
        etype = n.get("entity_type") or "entity"
        desc = (n.get("description") or (n.get("properties") or {}).get("description") or "")
        if desc:
            lines.append(f"- {label} ({etype}): {desc}")
        else:
            lines.append(f"- {label} ({etype})")
    return "\n".join(lines) if lines else "(No entities)"


def _format_relationships(edges: List[Dict[str, Any]]) -> str:
    """Format edge list for the prompt."""
    lines = [
        f"- {e.get('source', '')} — {e.get('relation_type', '')} — {e.get('target', '')}"
        for e in edges
    ]
    return "\n".join(lines) if lines else "(No relationships)"


class SummarizationService:
    """Generates LLM summaries for communities at leaf, mid, and root levels."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key or settings.OPENAI_API_KEY
        self._model = model or getattr(
            settings, "COMMUNITY_SUMMARIZATION_MODEL", "gpt-4o-mini"
        )
        self._llm: Optional[ChatOpenAI] = None

    def _get_llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=self._model,
                temperature=0.2,
                openai_api_key=self._api_key or "",
            )
        return self._llm

    def summarize_community(
        self,
        community_id: str,
        level: CommunityLevel,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        child_summaries: Optional[List[str]] = None,
    ) -> str:
        """
        Generate a text summary for a single community.

        Args:
            community_id: Community identifier.
            level: leaf, mid, or root.
            nodes: Entity nodes in this community (dicts with id, label, entity_type, etc.).
            edges: Relationships in this community (dicts with source, target, relation_type).
            child_summaries: For mid/root, optional list of sub-community summary texts.

        Returns:
            LLM-generated summary string.
        """
        prompt_data = PromptManager.get_prompt("community_summary")
        template = prompt_data["template"]
        input_vars = prompt_data["input_variables"]

        entities_text = _format_entities(nodes)
        relationships_text = _format_relationships(edges)

        child_section = ""
        if child_summaries:
            child_section = "Summaries of sub-communities (synthesize these in your report):\n\n"
            for i, s in enumerate(child_summaries, 1):
                child_section += f"Sub-community {i}:\n{s}\n\n"

        prompt = PromptTemplate(
            template=template,
            input_variables=input_vars,
        )
        chain = prompt | self._get_llm()
        result = chain.invoke({
            "level": level.value,
            "community_id": community_id,
            "entities_text": entities_text,
            "relationships_text": relationships_text,
            "child_summaries_section": child_section or "(N/A)",
        })
        summary = result.content if hasattr(result, "content") else str(result)
        logger.debug(
            "Community summary generated",
            community_id=community_id,
            level=level.value,
        )
        return summary.strip()

    async def summarize_community_async(
        self,
        community_id: str,
        level: CommunityLevel,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        child_summaries: Optional[List[str]] = None,
    ) -> str:
        """Async version of summarize_community (uses chain.ainvoke)."""
        prompt_data = PromptManager.get_prompt("community_summary")
        template = prompt_data["template"]
        input_vars = prompt_data["input_variables"]

        entities_text = _format_entities(nodes)
        relationships_text = _format_relationships(edges)

        child_section = ""
        if child_summaries:
            child_section = "Summaries of sub-communities (synthesize these in your report):\n\n"
            for i, s in enumerate(child_summaries, 1):
                child_section += f"Sub-community {i}:\n{s}\n\n"

        prompt = PromptTemplate(
            template=template,
            input_variables=input_vars,
        )
        chain = prompt | self._get_llm()
        result = await chain.ainvoke(
            {
                "level": level.value,
                "community_id": community_id,
                "entities_text": entities_text,
                "relationships_text": relationships_text,
                "child_summaries_section": child_section or "(N/A)",
            }
        )
        summary = result.content if hasattr(result, "content") else str(result)
        logger.debug(
            "Community summary generated (async)",
            community_id=community_id,
            level=level.value,
        )
        return summary.strip()

    def summarize_level(
        self,
        communities: List[Dict[str, Any]],
        level: CommunityLevel,
        node_map: Dict[str, Dict[str, Any]],
        all_edges: List[Dict[str, Any]],
        summaries_by_cid: Dict[str, str],
        *,
        max_workers: int = MAX_SUMMARIZATION_WORKERS,
    ) -> None:
        """
        Summarize all communities at *level* in parallel, writing results into
        each community dict's ``"summary"`` key and into *summaries_by_cid*.

        Communities at the same level have no inter-dependency, so they are
        submitted to a ThreadPoolExecutor concurrently.  Each worker creates
        its own LLM client instance to avoid shared-state races.

        Args:
            communities: Full hierarchical community list (all levels).
            level: The level to process in this call.
            node_map: node_id → node dict lookup.
            all_edges: All graph edges (used to find intra-community edges).
            summaries_by_cid: Mutable dict; child summaries must already be
                present before calling this for mid/root levels.
            max_workers: Thread pool size (default 10, capped by community count).
        """
        targets = [c for c in communities if c.get("level") == level.value]
        if not targets:
            return

        def _summarize_one(c: Dict[str, Any]) -> tuple[str, str]:
            node_ids = set(c.get("node_ids") or [])
            c_nodes = [node_map[nid] for nid in node_ids if nid in node_map]
            c_edges = [
                e for e in all_edges
                if e.get("source") in node_ids and e.get("target") in node_ids
            ]
            child_ids = c.get("child_community_ids") or []
            child_summaries = [summaries_by_cid[cid] for cid in child_ids if cid in summaries_by_cid]
            # Each thread gets a fresh service instance to avoid ChatOpenAI lazy-init races
            svc = SummarizationService(api_key=self._api_key, model=self._model)
            summary = svc.summarize_community(
                c["community_id"],
                level,
                c_nodes,
                c_edges,
                child_summaries=child_summaries if child_summaries else None,
            )
            return c["community_id"], summary

        workers = min(max_workers, len(targets))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_summarize_one, c): c for c in targets}
            for future in as_completed(futures):
                cid, summary = future.result()
                summaries_by_cid[cid] = summary
                futures[future]["summary"] = summary

        logger.info(
            "Level summarization complete",
            level=level.value,
            count=len(targets),
            workers=workers,
        )

    async def summarize_level_async(
        self,
        communities: List[Dict[str, Any]],
        level: CommunityLevel,
        node_map: Dict[str, Dict[str, Any]],
        all_edges: List[Dict[str, Any]],
        summaries_by_cid: Dict[str, str],
        *,
        max_concurrency: Optional[int] = None,
        on_progress: Optional[Callable[[int, int], Awaitable[None]]] = None,
    ) -> None:
        """
        Summarize all communities at *level* concurrently (async), mutating:
        - each community dict with a ``"summary"`` field
        - *summaries_by_cid* with community_id → summary
        """
        targets = [c for c in communities if c.get("level") == level.value]
        if not targets:
            return

        total = len(targets)
        completed = 0
        completed_lock = asyncio.Lock()

        effective_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else getattr(settings, "COMMUNITY_SUMMARIZATION_CONCURRENCY", DEFAULT_ASYNC_CONCURRENCY)
        )
        semaphore = asyncio.Semaphore(max(1, min(effective_concurrency, total)))

        async def _summarize_one(c: Dict[str, Any]) -> tuple[str, str]:
            node_ids = set(c.get("node_ids") or [])
            c_nodes = [node_map[nid] for nid in node_ids if nid in node_map]
            c_edges = [
                e
                for e in all_edges
                if e.get("source") in node_ids and e.get("target") in node_ids
            ]
            child_ids = c.get("child_community_ids") or []
            child_summaries = [
                summaries_by_cid[cid] for cid in child_ids if cid in summaries_by_cid
            ]

            async with semaphore:
                summary = await self.summarize_community_async(
                    c["community_id"],
                    level,
                    c_nodes,
                    c_edges,
                    child_summaries=child_summaries if child_summaries else None,
                )

            nonlocal completed
            async with completed_lock:
                completed += 1
                if on_progress is not None:
                    await on_progress(completed, total)

            return c["community_id"], summary

        results = await asyncio.gather(*(_summarize_one(c) for c in targets))
        for cid, summary in results:
            summaries_by_cid[cid] = summary
        for c in targets:
            cid = c.get("community_id")
            if cid in summaries_by_cid:
                c["summary"] = summaries_by_cid[cid]

        logger.info(
            "Level summarization complete (async)",
            level=level.value,
            count=len(targets),
            concurrency=max(1, min(effective_concurrency, total)),
        )
