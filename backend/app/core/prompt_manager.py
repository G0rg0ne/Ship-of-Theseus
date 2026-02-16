"""
Centralized prompt manager for loading and caching LLM prompt templates from JSON files.
"""
import json
from pathlib import Path
from typing import Any, Dict

from app.core.logger import logger

_REQUIRED_KEYS = ("template", "input_variables")
_PROMPTS_DIR_NAME = "prompts"


class PromptManager:
    """
    Loads and caches prompt definitions from JSON files under app/prompts/.
    Uses in-memory caching to avoid repeated file I/O.
    """

    _cache: Dict[str, Dict[str, Any]] = {}
    _base_path: Path | None = None

    @classmethod
    def _get_prompts_dir(cls) -> Path:
        """Resolve prompts directory relative to app package."""
        if cls._base_path is None:
            # app/core/prompt_manager.py -> app/prompts
            cls._base_path = Path(__file__).resolve().parent.parent / _PROMPTS_DIR_NAME
        return cls._base_path

    @classmethod
    def _load_from_file(cls, prompt_name: str) -> Dict[str, Any]:
        """Load and validate a single prompt from disk."""
        safe_name = prompt_name.strip().lower().replace(" ", "_")
        if not safe_name.replace("_", "").isalnum():
            raise ValueError(f"Invalid prompt name: {prompt_name}")

        path = cls._get_prompts_dir() / f"{safe_name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in prompt file", path=str(path), error=str(e))
            raise ValueError(f"Invalid JSON in {path}: {e}") from e

        for key in _REQUIRED_KEYS:
            if key not in data:
                raise ValueError(f"Prompt '{prompt_name}' missing required key: {key}")
        if not isinstance(data["input_variables"], list):
            raise ValueError(
                f"Prompt '{prompt_name}' input_variables must be a list"
            )

        return data

    @classmethod
    def get_prompt(cls, prompt_name: str) -> Dict[str, Any]:
        """
        Return full prompt definition (cached). Raises on missing/invalid prompt.
        """
        if prompt_name in cls._cache:
            return cls._cache[prompt_name].copy()

        data = cls._load_from_file(prompt_name)
        cls._cache[prompt_name] = data
        logger.debug("Prompt loaded and cached", prompt_name=prompt_name)
        return data.copy()

    @classmethod
    def get_template(cls, prompt_name: str) -> str:
        """Return only the template string for the given prompt."""
        data = cls.get_prompt(prompt_name)
        return data["template"]

    @classmethod
    def reload_prompt(cls, prompt_name: str) -> Dict[str, Any]:
        """Reload prompt from disk and update cache."""
        if prompt_name in cls._cache:
            del cls._cache[prompt_name]
        return cls.get_prompt(prompt_name)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached prompts."""
        cls._cache.clear()
        logger.debug("Prompt cache cleared")
