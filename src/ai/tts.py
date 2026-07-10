from __future__ import annotations

from io import BytesIO

from gtts import gTTS

from settings import Settings


async def synthesize_audio(text: str, settings: Settings) -> bytes:
    spoken_text = text.strip() or "I do not have a response."
    buffer = BytesIO()
    tts = gTTS(text=spoken_text, lang="en")
    tts.write_to_fp(buffer)
    return buffer.getvalue()