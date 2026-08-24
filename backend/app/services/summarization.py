"""LLM summarization: key decisions + action items from a transcript."""

from __future__ import annotations

import json
import re

from openai import OpenAI

from app.config import settings

SUMMARY_SYSTEM_PROMPT = """You are an expert meeting analyst. You turn raw transcripts into
precise, action-oriented minutes.

Return a single JSON object with this exact shape:
{
  "title": "short meeting title, 5-10 words",
  "overview": "2-4 sentence executive summary of what happened",
  "key_decisions": ["decision that was actually agreed, not a suggestion"],
  "action_items": [
    {"task": "specific, actionable task", "owner": "person name or null", "due": "date/time mentioned or null"}
  ],
  "topics": ["short topic labels"]
}

Rules:
- Summarize this meeting transcript into key decisions and action items.
- Only list decisions that were clearly made. Do not invent agreement.
- Action items must be concrete (verb + outcome). Infer owner only if named or clearly implied.
- If a due date was not mentioned, set due to null. Do not fabricate dates.
- Do not add facts that are not in the transcript.
- If the audio was unclear or the transcript is empty, say so in the overview and return empty lists.
"""

DEMO_SUMMARY = {
    "title": "Q3 product planning — beta freeze",
    "overview": (
        "The team locked scope for the September 12 beta: authentication is complete, "
        "the team-switcher is cut from v1, and design will finish onboarding mockups by Friday. "
        "Support will publish a help-center article before the first customer invites, and "
        "marketing will get a 90-second walkthrough video the following week. Audio chunking "
        "for long transcriptions is deferred to GA."
    ),
    "key_decisions": [
        "Ship the product beta on September 12 if scope is frozen today.",
        "Remove the optional team-switcher from the beta / v1 release.",
        "Treat long-audio transcription chunking as a GA requirement, not a beta blocker.",
    ],
    "action_items": [
        {
            "task": "File the team-switcher scope cut in Linear",
            "owner": "Maya",
            "due": "today",
        },
        {
            "task": "Send revised onboarding mockups",
            "owner": "Priya",
            "due": "Friday noon",
        },
        {
            "task": "Draft the help-center article for the first ten customers",
            "owner": "Jordan",
            "due": "Tuesday, September 2",
        },
        {
            "task": "Record a 90-second product walkthrough demo video",
            "owner": "Jordan",
            "due": "week of September 8",
        },
        {
            "task": "Spike audio chunking for files over the 25MB transcription limit",
            "owner": "Maya",
            "due": "this sprint (GA, not beta)",
        },
    ],
    "topics": ["Beta launch", "Scope freeze", "Onboarding", "Support content", "Transcription risk"],
}


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def summarize_transcript(transcript: str) -> dict:
    if settings.use_demo:
        return DEMO_SUMMARY

    if not transcript.strip():
        return {
            "title": "Empty transcript",
            "overview": "No speech was detected in the uploaded audio.",
            "key_decisions": [],
            "action_items": [],
            "topics": [],
        }

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_summary_model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Summarize this meeting transcript into key decisions and action items.\n\n"
                    f"TRANSCRIPT:\n{transcript}"
                ),
            },
        ],
    )
    content = response.choices[0].message.content or "{}"
    data = _extract_json(content)

    action_items = []
    for item in data.get("action_items") or []:
        if isinstance(item, str):
            action_items.append({"task": item, "owner": None, "due": None})
            continue
        task = (item.get("task") or "").strip()
        if not task:
            continue
        owner = item.get("owner")
        due = item.get("due")
        action_items.append(
            {
                "task": task,
                "owner": owner if owner and str(owner).lower() not in {"null", "none", "unassigned"} else None,
                "due": due if due and str(due).lower() not in {"null", "none"} else None,
            }
        )

    return {
        "title": (data.get("title") or "Meeting minutes").strip()[:255],
        "overview": (data.get("overview") or "").strip(),
        "key_decisions": [str(item).strip() for item in (data.get("key_decisions") or []) if str(item).strip()],
        "action_items": action_items,
        "topics": [str(item).strip() for item in (data.get("topics") or []) if str(item).strip()][:8],
    }
