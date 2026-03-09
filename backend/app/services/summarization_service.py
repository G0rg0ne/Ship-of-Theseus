"""
LLM-based summarization service for knowledge graph communities.

Generates a comprehensive report for each community at every hierarchy level
using the prompt template in community_summary.json.

Within each hierarchy level all communities are independent, so they are
summarized concurrently using a thread pool (one LLM client per thread to
avoid lazy-init races). Levels are still processed in order: leaf → mid → root,
because mid/root summaries depend on their children's summaries.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.core.prompt_manager import PromptManager
from app.schemas.community import CommunityLevel

MAX_SUMMARIZATION_WORKERS = 10


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
