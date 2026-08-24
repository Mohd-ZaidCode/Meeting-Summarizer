from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import ActionItem, Meeting, Summary, Transcript, utcnow
from app.services.summarization import summarize_transcript
from app.services.transcription import transcribe_audio


def process_meeting(meeting_id: int) -> None:
    """Transcribe audio then generate minutes. Runs in a background thread."""
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if not meeting:
            return

        file_path = settings.upload_path / meeting.stored_filename
        if settings.use_demo:
            time.sleep(1.2)

        _set_status(db, meeting, "transcribing")
        result = transcribe_audio(file_path)

        meeting.language = result.language
        meeting.duration_seconds = result.duration
        meeting.transcript = Transcript(
            full_text=result.text,
            segments_json=json.dumps(result.segments),
        )
        db.commit()

        if settings.use_demo:
            time.sleep(0.8)

        _set_status(db, meeting, "summarizing")
        summary_data = summarize_transcript(result.text)

        meeting.title = summary_data["title"]
        meeting.summary = Summary(
            overview=summary_data["overview"],
            key_decisions_json=json.dumps(summary_data["key_decisions"]),
            topics_json=json.dumps(summary_data["topics"]),
        )
        meeting.action_items = [
            ActionItem(
                task=item["task"],
                owner=item.get("owner"),
                due=item.get("due"),
            )
            for item in summary_data["action_items"]
        ]
        meeting.status = "completed"
        meeting.error_message = None
        meeting.updated_at = utcnow()
        db.commit()
    except Exception as exc:
        db.rollback()
        meeting = db.get(Meeting, meeting_id)
        if meeting:
            meeting.status = "failed"
            meeting.error_message = str(exc)
            meeting.updated_at = utcnow()
            db.commit()
        traceback.print_exc()
    finally:
        db.close()


def _set_status(db: Session, meeting: Meeting, status: str) -> None:
    meeting.status = status
    meeting.updated_at = utcnow()
    db.commit()
    db.refresh(meeting)


def delete_audio_file(stored_filename: str) -> None:
    path = settings.upload_path / stored_filename
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
