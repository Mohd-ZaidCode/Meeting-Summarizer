from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Thread

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import apply_openai_key, settings
from app.database import get_db
from app.models import ActionItem, Meeting
from app.schemas import (
    ActionItemUpdate,
    HealthOut,
    MeetingDetail,
    MeetingListItem,
    OpenAIKeyIn,
    OpenAIKeyOut,
)
from app.services.pipeline import delete_audio_file, process_meeting
from app.services.transcription import ALLOWED_EXTENSIONS

router = APIRouter(prefix="/api")


def _meeting_detail(meeting: Meeting) -> MeetingDetail:
    segments = []
    transcript_out = None
    if meeting.transcript:
        try:
            segments = json.loads(meeting.transcript.segments_json or "[]")
        except json.JSONDecodeError:
            segments = []
        transcript_out = {
            "full_text": meeting.transcript.full_text,
            "segments": segments,
        }

    summary_out = None
    if meeting.summary:
        try:
            decisions = json.loads(meeting.summary.key_decisions_json or "[]")
        except json.JSONDecodeError:
            decisions = []
        try:
            topics = json.loads(meeting.summary.topics_json or "[]")
        except json.JSONDecodeError:
            topics = []
        summary_out = {
            "overview": meeting.summary.overview,
            "key_decisions": decisions,
            "topics": topics,
        }

    return MeetingDetail(
        id=meeting.id,
        title=meeting.title,
        original_filename=meeting.original_filename,
        content_type=meeting.content_type,
        file_size=meeting.file_size,
        status=meeting.status,
        duration_seconds=meeting.duration_seconds,
        language=meeting.language,
        error_message=meeting.error_message,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
        transcript=transcript_out,
        summary=summary_out,
        action_items=[
            {
                "id": item.id,
                "task": item.task,
                "owner": item.owner,
                "due": item.due,
                "done": bool(item.done),
            }
            for item in meeting.action_items
        ],
        demo_mode=settings.use_demo,
    )


def _health_payload() -> HealthOut:
    return HealthOut(
        status="ok",
        demo_mode=settings.use_demo,
        has_api_key=settings.has_api_key,
        key_hint=settings.key_hint,
        transcribe_model=settings.openai_transcribe_model,
        summary_model=settings.openai_summary_model,
        max_upload_mb=settings.max_upload_mb,
    )


@router.get("/health", response_model=HealthOut)
def health():
    return _health_payload()


@router.post("/settings/openai-key", response_model=OpenAIKeyOut)
def save_openai_key(payload: OpenAIKeyIn):
    key = payload.api_key.strip()
    if len(key) < 20:
        raise HTTPException(status_code=400, detail="That does not look like an OpenAI API key.")

    verified = False
    try:
        from openai import AuthenticationError, OpenAI

        client = OpenAI(api_key=key, timeout=20.0)
        client.models.list()
        verified = True
    except AuthenticationError:
        raise HTTPException(status_code=400, detail="OpenAI rejected this API key.")
    except Exception:
        # Network / quota issues: still save so the next upload can use it.
        verified = False

    apply_openai_key(key)
    return OpenAIKeyOut(
        demo_mode=settings.use_demo,
        has_api_key=settings.has_api_key,
        key_hint=settings.key_hint,
        verified=verified,
    )


@router.delete("/settings/openai-key", response_model=OpenAIKeyOut)
def clear_openai_key():
    apply_openai_key("")
    return OpenAIKeyOut(
        demo_mode=settings.use_demo,
        has_api_key=settings.has_api_key,
        key_hint=settings.key_hint,
        verified=False,
    )


@router.get("/meetings", response_model=list[MeetingListItem])
def list_meetings(db: Session = Depends(get_db)):
    meetings = db.scalars(
        select(Meeting)
        .options(selectinload(Meeting.action_items))
        .order_by(Meeting.created_at.desc())
    ).all()
    return [
        MeetingListItem(
            id=meeting.id,
            title=meeting.title,
            original_filename=meeting.original_filename,
            status=meeting.status,
            duration_seconds=meeting.duration_seconds,
            language=meeting.language,
            error_message=meeting.error_message,
            created_at=meeting.created_at,
            action_item_count=len(meeting.action_items),
        )
        for meeting in meetings
    ]


@router.get("/meetings/{meeting_id}", response_model=MeetingDetail)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = _load_meeting(db, meeting_id)
    return _meeting_detail(meeting)


@router.get("/meetings/{meeting_id}/audio")
def get_audio(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    path = settings.upload_path / meeting.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file is no longer on disk")
    return FileResponse(
        path,
        media_type=meeting.content_type or "application/octet-stream",
        filename=meeting.original_filename,
    )


@router.post("/meetings", response_model=MeetingDetail, status_code=201)
async def create_meeting(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    original = file.filename or "recording"
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Use {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )

    stored_name = f"{uuid.uuid4().hex}{suffix}"
    dest = settings.upload_path / stored_name

    size = 0
    try:
        with dest.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.max_upload_mb}MB upload limit.",
                    )
                buffer.write(chunk)
    finally:
        await file.close()

    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    meeting = Meeting(
        title=Path(original).stem.replace("_", " ").replace("-", " ").title() or "Untitled meeting",
        original_filename=original,
        stored_filename=stored_name,
        content_type=file.content_type or "application/octet-stream",
        file_size=size,
        status="queued",
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)

    Thread(target=process_meeting, args=(meeting.id,), daemon=True).start()
    return _meeting_detail(meeting)


@router.patch("/meetings/{meeting_id}/actions/{action_id}", response_model=MeetingDetail)
def toggle_action(
    meeting_id: int,
    action_id: int,
    payload: ActionItemUpdate,
    db: Session = Depends(get_db),
):
    item = db.get(ActionItem, action_id)
    if not item or item.meeting_id != meeting_id:
        raise HTTPException(status_code=404, detail="Action item not found")
    item.done = 1 if payload.done else 0
    db.commit()
    return _meeting_detail(_load_meeting(db, meeting_id))


@router.delete("/meetings/{meeting_id}", status_code=204)
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    stored = meeting.stored_filename
    db.delete(meeting)
    db.commit()
    delete_audio_file(stored)
    return None


def _load_meeting(db: Session, meeting_id: int) -> Meeting:
    meeting = db.scalars(
        select(Meeting)
        .options(
            selectinload(Meeting.transcript),
            selectinload(Meeting.summary),
            selectinload(Meeting.action_items),
        )
        .where(Meeting.id == meeting_id)
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting
