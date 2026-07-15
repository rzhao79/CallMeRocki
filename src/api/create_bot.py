from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ai.roc import ask_roc
from ai.stt import transcript_words_to_text
from ai.tts import synthesize_audio
from recall.audio import encode_mp3_bytes
from recall.events import RecallRealtimeEvent, verify_request_from_recall
from settings import Settings, get_settings


router = APIRouter(prefix="/recall", tags=["recall"])
logger = logging.getLogger("uvicorn.error")

class CreateBotRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    meeting_url: str
    bot_name: str | None = None
    join_at: datetime | None = None
    language_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreateBotResponse(BaseModel):
    bot_id: str
    response: dict[str, Any]


class WebhookAck(BaseModel):
    accepted: bool = True
    event: str | None = None


def _build_recall_headers(settings: Settings) -> dict[str, str]:
    if not settings.recall_api_key:
        raise RuntimeError("RECALL_API_KEY is required")

    return {
        "Authorization": settings.recall_api_key,
        "accept": "application/json",
        "content-type": "application/json",
    }


def _build_create_bot_payload(request_body: CreateBotRequest, settings: Settings) -> dict[str, Any]:
    webhook_url = f"{settings.require_public_base_url()}{settings.recall_webhook_path}"

    if not settings.recall_automatic_audio_b64_mp3:
        raise RuntimeError("RECALL_AUTOMATIC_AUDIO_B64_MP3 is required to use Recall output_audio")

    payload: dict[str, Any] = {
        "meeting_url": request_body.meeting_url,
        "bot_name": request_body.bot_name or settings.bot_name,
        "recording_config": {
            "transcript": {
                "provider": {
                    "recallai_streaming": {
                         "language_code": "en",
                    }
                },
                "diarization": {"use_separate_streams_when_available": True},
            },
            "realtime_endpoints": [
                {
                    "type": "webhook",
                    "url": webhook_url,
                    "events": ["transcript.data"],
                }
            ],
        },
        "metadata": request_body.metadata,
    }

    if request_body.join_at is not None:
        join_at = request_body.join_at
        if join_at.tzinfo is None:
            join_at = join_at.replace(tzinfo=timezone.utc)
        payload["join_at"] = join_at.astimezone(timezone.utc).isoformat()

    if settings.recall_automatic_audio_b64_mp3:
        payload["automatic_audio_output"] = {
            "in_call_recording": {
                "data": {
                    "kind": "mp3",
                    "b64_data": settings.recall_automatic_audio_b64_mp3,
                }
            }
        }

        if settings.output_audio_replay_on_join:
            payload["automatic_audio_output"]["in_call_recording"]["replay_on_participant_join"] = {
                "debounce_mode": "trailing",
                "debounce_interval": 10,
                "disable_after": 60,
            }

    return payload


async def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


async def _output_audio(bot_id: str, audio_bytes: bytes, settings: Settings) -> None:
    if not settings.recall_api_key:
        raise RuntimeError("RECALL_API_KEY is required")

    encoded_audio = encode_mp3_bytes(audio_bytes)
    url = f"{settings.recall_base_url.rstrip('/')}/bot/{bot_id}/output_audio/"
    headers = _build_recall_headers(settings)
    payload = {"kind": encoded_audio.kind, "b64_data": encoded_audio.b64_data}

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()


async def _handle_transcript_event(event_payload: dict[str, Any], settings: Settings) -> None:
    try:
        event = RecallRealtimeEvent.model_validate(event_payload)
    except Exception:
        logger.exception("Webhook transcript handler: event validation failed")
        return

    if event.event != "transcript.data":
        logger.warning("Webhook transcript handler: ignoring event=%s", event.event)
        return

    data = event.data if isinstance(event.data, dict) else event.data.model_dump()
    transcript_data = data.get("data", {}) if isinstance(data, dict) else {}
    words = transcript_data.get("words", []) if isinstance(transcript_data, dict) else []
    transcript_text = transcript_words_to_text(words)
    logger.warning(
        "Webhook transcript handler: words=%d transcript_chars=%d",
        len(words) if isinstance(words, list) else 0,
        len(transcript_text),
    )

    if not transcript_text:
        logger.warning("Webhook transcript handler: empty transcript text, skipping")
        return

    roc_response = await ask_roc(transcript_text, settings)
    audio_bytes = await synthesize_audio(roc_response, settings)

    bot = data.get("bot", {}) if isinstance(data, dict) else {}
    bot_id = bot.get("id") if isinstance(bot, dict) else None
    if not bot_id:
        logger.warning("Webhook transcript handler: missing bot.id in payload")
        return

    logger.warning("Webhook transcript handler: sending output audio for bot_id=%s", bot_id)
    await _output_audio(str(bot_id), audio_bytes, settings)
    logger.warning("Webhook transcript handler: output audio sent for bot_id=%s", bot_id)

async def _get_json(
    url: str,
    headers: dict[str, str],
) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

        if response.is_error:
            raise RuntimeError(
                f"Recall returned {response.status_code}: {response.text}"
            )

        return response.json()


@router.post(
    "/bot",
    response_model=CreateBotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bot(request_body: CreateBotRequest) -> CreateBotResponse:
    settings = get_settings()

    try:
        payload = _build_create_bot_payload(request_body, settings)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    url = f"{settings.recall_base_url.rstrip('/')}/bot/"

    try:
        response_json = await _post_json(
            url,
            _build_recall_headers(settings),
            payload,
        )

    except httpx.HTTPStatusError as exc:
        response = exc.response

        try:
            recall_error = response.json()
        except ValueError:
            recall_error = response.text

        # Recall received the request but rejected the payload.
        if 400 <= response.status_code < 500:
            raise HTTPException(
                status_code=response.status_code,
                detail={
                    "message": "Recall rejected the bot creation request.",
                    "recall_error": recall_error,
                },
            ) from exc

        # Recall returned an upstream server error.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Recall failed to create the bot.",
                "recall_status": response.status_code,
                "recall_error": recall_error,
            },
        ) from exc

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Recall timed out while creating the bot.",
        ) from exc

    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not connect to Recall: {exc}",
        ) from exc

    bot_id = str(response_json.get("id", ""))

    if not bot_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": "Recall returned a successful response without a bot ID.",
                "recall_response": response_json,
            },
        )

    return CreateBotResponse(
        bot_id=bot_id,
        response=response_json,
    )

@router.get("/bot/{bot_id}")
async def get_bot(bot_id: str) -> dict:
    settings = get_settings()
    url = f"{settings.recall_base_url.rstrip('/')}/bot/{bot_id}/"

    return await _get_json(
        url,
        _build_recall_headers(settings),
    )

@router.post("/webhook", response_model=WebhookAck)
async def recall_webhook(request: Request, background_tasks: BackgroundTasks) -> WebhookAck:
    settings = get_settings()
    raw_body = await request.body()
    logger.warning(
        "Webhook request received: body_bytes=%d verify_recall_requests=%s",
        len(raw_body),
        settings.verify_recall_requests,
    )

    if settings.verify_recall_requests:
        try:
            verify_request_from_recall(settings.recall_workspace_verification_secret, request.headers, raw_body)
            logger.warning("Webhook signature verification: passed")
        except ValueError as exc:
            logger.warning("Webhook signature verification: failed detail=%s", str(exc))
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        event_payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if not isinstance(event_payload, dict):
        logger.warning(
            "Webhook received non-object payload type=%s",
            type(event_payload).__name__,
        )
        return WebhookAck(event=None)

    event_name = event_payload.get("event")
    logger.warning(
        "Webhook received event=%s payload_keys=%s",
        event_name,
        sorted(event_payload.keys()),
    )

    if event_name == "transcript.data":
        logger.warning("Webhook scheduling transcript handler")
        background_tasks.add_task(_handle_transcript_event, event_payload, settings)
    else:
        logger.warning("Webhook ignoring unsupported event=%s", event_name)

    return WebhookAck(event=event_name)