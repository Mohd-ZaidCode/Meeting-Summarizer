"""OpenAI Whisper (or compatible) automatic speech recognition."""

from __future__ import annotations

import json
from pathlib import Path

from openai import OpenAI

from app.config import settings

ALLOWED_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".wav",
    ".webm",
    ".ogg",
    ".flac",
}


class TranscriptionResult:
    def __init__(
        self,
        text: str,
        segments: list[dict],
        language: str | None = None,
        duration: float | None = None,
    ):
        self.text = text
        self.segments = segments
        self.language = language
        self.duration = duration


DEMO_TRANSCRIPT = TranscriptionResult(
    text=(
        "Alex: Thanks everyone for joining the Q3 product planning call. Let's start with the "
        "launch date. Maya, any update from engineering?\n\n"
        "Maya: The authentication rewrite is done. If we freeze scope today we can ship the "
        "beta on September 12th. That assumes design signs off on the onboarding flow by Friday.\n\n"
        "Priya: Design can do Friday. We should drop the optional team-switcher from v1 though — "
        "it is adding a week.\n\n"
        "Alex: Agreed. Decision: we cut team-switcher from the beta. Maya, please file the "
        "scope change in Linear today. Priya, send the revised onboarding mockups by Friday noon.\n\n"
        "Jordan: Support still needs a help-center article before we invite the first ten customers. "
        "I can draft it by next Tuesday, September 2nd.\n\n"
        "Alex: Perfect. Also, marketing wants a 90-second demo video. Jordan, can you record a "
        "walkthrough after the mockups land?\n\n"
        "Jordan: Yes — I'll have a first cut the week of September 8th.\n\n"
        "Maya: One risk: the Whisper transcription vendor we planned to use has a 25 megabyte "
        "limit. For longer customer calls we should chunk audio. I'll spike that this sprint.\n\n"
        "Alex: Let's treat that as a must-have for GA, not beta. Wrap-up: beta September 12, "
        "scope frozen today, onboarding mockups Friday, help article September 2, demo video "
        "the week of the 8th. Thanks all."
    ),
    segments=[
        {"start": 0.0, "end": 8.4, "text": "Thanks everyone for joining the Q3 product planning call. Let's start with the launch date. Maya, any update from engineering?"},
        {"start": 8.4, "end": 18.2, "text": "The authentication rewrite is done. If we freeze scope today we can ship the beta on September 12th. That assumes design signs off on the onboarding flow by Friday."},
        {"start": 18.2, "end": 26.0, "text": "Design can do Friday. We should drop the optional team-switcher from v1 though — it is adding a week."},
        {"start": 26.0, "end": 36.5, "text": "Agreed. Decision: we cut team-switcher from the beta. Maya, please file the scope change in Linear today. Priya, send the revised onboarding mockups by Friday noon."},
        {"start": 36.5, "end": 45.8, "text": "Support still needs a help-center article before we invite the first ten customers. I can draft it by next Tuesday, September 2nd."},
        {"start": 45.8, "end": 54.0, "text": "Perfect. Also, marketing wants a 90-second demo video. Jordan, can you record a walkthrough after the mockups land?"},
        {"start": 54.0, "end": 59.5, "text": "Yes — I'll have a first cut the week of September 8th."},
        {"start": 59.5, "end": 70.2, "text": "One risk: the Whisper transcription vendor we planned to use has a 25 megabyte limit. For longer customer calls we should chunk audio. I'll spike that this sprint."},
        {"start": 70.2, "end": 82.0, "text": "Let's treat that as a must-have for GA, not beta. Wrap-up: beta September 12, scope frozen today, onboarding mockups Friday, help article September 2, demo video the week of the 8th. Thanks all."},
    ],
    language="en",
    duration=82.0,
)


def transcribe_audio(file_path: Path) -> TranscriptionResult:
    if settings.use_demo:
        return DEMO_TRANSCRIPT

    client = OpenAI(api_key=settings.openai_api_key)
    with file_path.open("rb") as audio_file:
        result = client.audio.transcriptions.create(
            model=settings.openai_transcribe_model,
            file=audio_file,
            response_format="verbose_json",
        )

    payload = result.model_dump() if hasattr(result, "model_dump") else json.loads(result)
    segments = []
    for segment in payload.get("segments") or []:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": float(segment.get("start") or 0),
                "end": float(segment.get("end") or 0),
                "text": text,
            }
        )

    text = (payload.get("text") or "").strip()
    if not text and segments:
        text = " ".join(item["text"] for item in segments)

    return TranscriptionResult(
        text=text,
        segments=segments,
        language=payload.get("language"),
        duration=payload.get("duration"),
    )
