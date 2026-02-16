"""
Entity extraction service using LangChain and LLM.
Supports parallel chunk processing with progress tracking via Redis.
"""
import asyncio
from datetime import datetime
from typing import List

from langchain_openai import ChatOpenAI
from langchain.output_parsers import PydanticOutputParser
from langchain.prompts import PromptTemplate

from app.core.config import settings
from app.core.logger import logger
from app.core.prompt_manager import PromptManager
from app.core.cache import (
    cache_get,
    cache_set,
    cache_key_extraction_job,
    EXTRACTION_JOB_TTL,
)
from app.schemas.entities import ExtractedEntities, DocumentEntities


class EntityExtractionService:
    """LangChain-based entity extraction with parallel and async support."""

    def __init__(self, api_key: str, model: str):
        self.llm = ChatOpenAI(
            model=model,
            temperature=0,
            openai_api_key=api_key,
        )
        self.parser = PydanticOutputParser(pydantic_object=ExtractedEntities)
        prompt_data = PromptManager.get_prompt("entity_extraction")
        self.prompt = PromptTemplate(
            template=prompt_data["template"],
            input_variables=prompt_data["input_variables"],
            partial_variables={
                "format_instructions": self.parser.get_format_instructions()
            },
        )
        self.chain = self.prompt | self.llm | self.parser

    def extract_entities(self, text: str, chunk_id: int = 0) -> ExtractedEntities:
        """Extract entities from a single chunk (sync)."""
        result = self.chain.invoke({"text": text})
        result.chunk_id = chunk_id
        return result

    async def extract_entities_async(
        self, text: str, chunk_id: int = 0
    ) -> ExtractedEntities:
        """Extract entities from a single chunk (async for parallel use)."""
        result = await self.chain.ainvoke({"text": text})
        result.chunk_id = chunk_id
        return result

    async def extract_from_chunks_parallel(
        self,
        chunks: List[str],
        job_id: str,
        user_id: str,
        filename: str,
    ) -> None:
        """
        Extract entities from all chunks in parallel batches.
        Progress is written to Redis under extraction:job:{job_id}.
        """
        key = cache_key_extraction_job(job_id)
        n = len(chunks)
        batch_size = getattr(
            settings, "ENTITY_EXTRACTION_BATCH_SIZE", 5
        ) or 5

        job_payload = {
            "status": "running",
            "user_id": user_id,
            "filename": filename,
            "total_chunks": n,
            "completed_chunks": 0,
            "result": None,
            "error": None,
            "created_at": datetime.utcnow().isoformat() + "Z",
        }
        await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
        logger.info(
            "Entity extraction job started",
            job_id=job_id,
            user_id=user_id,
            total_chunks=n,
            batch_size=batch_size,
        )

        results: List[ExtractedEntities] = []
        try:
            for i in range(0, n, batch_size):
                batch = chunks[i : i + batch_size]
                tasks = [
                    self.extract_entities_async(chunk, i + j)
                    for j, chunk in enumerate(batch)
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for j, res in enumerate(batch_results):
                    if isinstance(res, Exception):
                        logger.error(
                            "Chunk extraction failed",
                            chunk_id=i + j,
                            error=str(res),
                        )
                        results.append(
                            ExtractedEntities(
                                chunk_id=i + j,
                                people=[],
                                organizations=[],
                                dates=[],
                                locations=[],
                                key_terms=[],
                            )
                        )
                    else:
                        results.append(res)

                completed = min(i + len(batch), n)
                job_payload["completed_chunks"] = completed
                await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
                logger.debug(
                    "Extraction progress",
                    job_id=job_id,
                    completed=completed,
                    total=n,
                )

            doc_entities = DocumentEntities(
                filename=filename,
                chunk_entities=results,
                extracted_at=datetime.utcnow().isoformat() + "Z",
            )
            job_payload["status"] = "completed"
            job_payload["completed_chunks"] = n
            job_payload["result"] = doc_entities.model_dump()
            job_payload["error"] = None
            await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
            logger.success(
                "Entity extraction job completed",
                job_id=job_id,
                chunks=n,
            )
        except Exception as e:
            logger.exception("Entity extraction job failed", job_id=job_id)
            job_payload = await cache_get(key) or {}
            job_payload["status"] = "failed"
            job_payload["error"] = str(e)
            job_payload["result"] = None
            await cache_set(key, job_payload, ttl_seconds=EXTRACTION_JOB_TTL)
