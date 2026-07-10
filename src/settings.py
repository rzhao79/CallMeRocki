from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from os import getenv


def _get_bool(name: str, default: bool = False) -> bool:
    raw_value = getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    port: int = int(getenv("PORT", "8787"))
    host: str = getenv("HOST", "0.0.0.0")

    recall_base_url: str = getenv("RECALL_BASE_URL", "https://us-east-1.recall.ai/api/v1")
    recall_api_key: str = getenv("RECALL_API_KEY", "")
    recall_workspace_verification_secret: str = getenv("RECALL_WORKSPACE_VERIFICATION_SECRET", "")
    recall_public_base_url: str = getenv("RECALL_PUBLIC_BASE_URL", "")
    recall_webhook_path: str = getenv("RECALL_WEBHOOK_PATH", "/recall/webhook")
    recall_automatic_audio_b64_mp3: str = getenv("RECALL_AUTOMATIC_AUDIO_B64_MP3", "")

    roc_agent_url: str = getenv("ROC_AGENT_URL", "http://localhost:8080/invoke")
    roc_agent_prompt_field: str = getenv("ROC_AGENT_PROMPT_FIELD", "prompt")

    bot_name: str = getenv("BOT_NAME", "CallMeRocki")
    transcript_language_code: str = getenv("TRANSCRIPT_LANGUAGE_CODE", "auto")

    verify_recall_requests: bool = _get_bool("VERIFY_RECALL_REQUESTS", True)
    output_audio_replay_on_join: bool = _get_bool("OUTPUT_AUDIO_REPLAY_ON_PARTICIPANT_JOIN", False)

    def require_public_base_url(self) -> str:
        if not self.recall_public_base_url:
            raise RuntimeError("RECALL_PUBLIC_BASE_URL is required to create Recall webhooks")
        return self.recall_public_base_url.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()