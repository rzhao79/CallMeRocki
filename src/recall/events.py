from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field


class RecallWord(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    start_timestamp: dict[str, Any] | None = None
    end_timestamp: dict[str, Any] | None = None


class RecallParticipant(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | str | None = None
    name: str | None = None
    is_host: bool | None = None
    platform: str | None = None
    email: str | None = None


class RecallTranscriptPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    words: list[RecallWord] = Field(default_factory=list)
    language_code: str | None = None
    participant: RecallParticipant | None = None


class RecallArtifactRef(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecallRealtimeTranscriptData(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: RecallTranscriptPayload
    realtime_endpoint: RecallArtifactRef | None = None
    transcript: RecallArtifactRef | None = None
    recording: RecallArtifactRef | None = None
    bot: RecallArtifactRef | None = None


class RecallRealtimeEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str
    data: RecallRealtimeTranscriptData | dict[str, Any]


def normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def verify_request_from_recall(secret: str, headers: Mapping[str, str], payload: str | bytes | None) -> None:
    normalized_headers = normalize_headers(headers)
    message_id = normalized_headers.get("webhook-id") or normalized_headers.get("svix-id")
    message_timestamp = normalized_headers.get("webhook-timestamp") or normalized_headers.get("svix-timestamp")
    message_signature = normalized_headers.get("webhook-signature") or normalized_headers.get("svix-signature")

    if not secret or not secret.startswith("whsec_"):
        raise ValueError("Verification secret is missing or invalid")
    if not message_id or not message_timestamp or not message_signature:
        raise ValueError("Missing webhook ID, timestamp, or signature")

    payload_text = ""
    if payload:
        payload_text = payload.decode("utf-8") if isinstance(payload, bytes) else payload

    secret_bytes = base64.b64decode(secret.removeprefix("whsec_"))
    signed_message = f"{message_id}.{message_timestamp}.{payload_text}".encode("utf-8")
    expected_signature = base64.b64encode(hmac.new(secret_bytes, signed_message, hashlib.sha256).digest()).decode("utf-8")

    for versioned_signature in message_signature.split(" "):
        version, _, signature = versioned_signature.partition(",")
        if version != "v1" or not signature:
            continue

        try:
            expected_bytes = base64.b64decode(expected_signature)
            signature_bytes = base64.b64decode(signature)
        except Exception as exc:  # pragma: no cover - defensive path
            raise ValueError("Invalid signature encoding") from exc

        if len(expected_bytes) == len(signature_bytes) and hmac.compare_digest(expected_bytes, signature_bytes):
            return

    raise ValueError("No matching signature found")