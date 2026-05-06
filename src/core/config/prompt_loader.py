"""Workbench의 prompts.yaml에서 프롬프트를 읽어오는 로더.

yaml 파일이 없거나 해당 키가 없으면 None을 반환하여
호출부에서 하드코딩 fallback을 사용하도록 한다.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis_core.prompt_loader")

_PROMPTS_YAML_ENV = "JARVIS_PROMPTS_YAML"

# 기본 경로: jarvis_core 기준으로 workbench의 config/prompts.yaml
_DEFAULT_PATH = (
    Path(__file__).resolve().parents[4]          # jarvis_core/
    / "jarvis_ai_workbench" / "config" / "prompts.yaml"
)


def _get_prompts_path() -> Path:
    env_path = os.environ.get(_PROMPTS_YAML_ENV)
    if env_path:
        return Path(env_path)
    return _DEFAULT_PATH.resolve()


def load_prompt(key: str) -> str | None:
    """prompts.yaml에서 특정 프롬프트를 읽는다.

    Args:
        key: 프롬프트 키 (base_system, deepthink_planning, etc.)

    Returns:
        프롬프트 content 문자열. 파일이나 키가 없으면 None.
    """
    path = _get_prompts_path()
    if not path.exists():
        logger.debug("prompts.yaml not found at %s, using hardcoded fallback", path)
        return None

    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        prompt = data.get("prompts", {}).get(key)
        if prompt is None:
            logger.debug("prompt key '%s' not found in prompts.yaml", key)
            return None

        content = prompt.get("content")
        if content:
            logger.info("prompt loaded from yaml key=%s len=%d", key, len(content))
        return content

    except Exception as exc:
        logger.warning("failed to load prompt '%s' from yaml: %s", key, exc)
        return None


def load_all_prompts() -> dict[str, str]:
    """모든 프롬프트를 dict[key, content]로 반환한다."""
    path = _get_prompts_path()
    if not path.exists():
        return {}

    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        result: dict[str, str] = {}
        for key, val in data.get("prompts", {}).items():
            if isinstance(val, dict) and val.get("content"):
                result[key] = val["content"]
        return result

    except Exception as exc:
        logger.warning("failed to load prompts from yaml: %s", exc)
        return {}
