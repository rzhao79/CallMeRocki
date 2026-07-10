from __future__ import annotations

import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class EncodedAudio:
    kind: str
    b64_data: str


def encode_mp3_bytes(audio_bytes: bytes) -> EncodedAudio:
    return EncodedAudio(kind="mp3", b64_data=base64.b64encode(audio_bytes).decode("utf-8"))