from __future__ import annotations

from collections.abc import Iterable


def transcript_words_to_text(words: Iterable[object]) -> str:
    pieces: list[str] = []
    for word in words:
        text = word.get("text") if isinstance(word, dict) else getattr(word, "text", None)
        if not text:
            continue
        cleaned = str(text).strip()
        if cleaned:
            pieces.append(cleaned)
    return " ".join(pieces).strip()