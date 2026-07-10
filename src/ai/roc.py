from __future__ import annotations

import json
from typing import Any

import httpx

from settings import Settings


def _decode_response_body(payload: bytes) -> str:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return payload.decode("utf-8", errors="replace")

    if isinstance(parsed, dict):
        for key in ("result", "output", "response", "content", "text"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return json.dumps(parsed, ensure_ascii=False)


async def ask_roc(prompt: str, settings: Settings, client: httpx.AsyncClient | None = None) -> str:
    payload: dict[str, Any] = {settings.roc_agent_prompt_field: prompt}

    if client is not None:
        response = await client.post(settings.roc_agent_url, json=payload)
        response.raise_for_status()
        return _decode_response_body(response.content)

    async with httpx.AsyncClient(timeout=120.0) as ephemeral_client:
        response = await ephemeral_client.post(settings.roc_agent_url, json=payload)
        response.raise_for_status()
        return _decode_response_body(response.content)