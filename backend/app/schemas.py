from datetime import datetime

from pydantic import BaseModel, Field


class ActionItemOut(BaseModel):
    id: int
    task: str
    owner: str | None = None
    due: str | None = None
    done: bool = False

    model_config = {"from_attributes": True}


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptOut(BaseModel):
    full_text: str
    segments: list[TranscriptSegment] = Field(default_factory=list)


class SummaryOut(BaseModel):
    overview: str
    key_decisions: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)


class MeetingListItem(BaseModel):
    id: int
    title: str
    original_filename: str
    status: str
    duration_seconds: float | None = None
    language: str | None = None
    error_message: str | None = None
    created_at: datetime
    action_item_count: int = 0

    model_config = {"from_attributes": True}


class MeetingDetail(BaseModel):
    id: int
    title: str
    original_filename: str
    content_type: str
    file_size: int
    status: str
    duration_seconds: float | None = None
    language: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    transcript: TranscriptOut | None = None
    summary: SummaryOut | None = None
    action_items: list[ActionItemOut] = Field(default_factory=list)
    demo_mode: bool = False

    model_config = {"from_attributes": True}


class ActionItemUpdate(BaseModel):
    done: bool


class HealthOut(BaseModel):
    status: str
    demo_mode: bool
    has_api_key: bool = False
    key_hint: str | None = None
    transcribe_model: str
    summary_model: str
    max_upload_mb: int


class OpenAIKeyIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


class OpenAIKeyOut(BaseModel):
    demo_mode: bool
    has_api_key: bool
    key_hint: str | None = None
    verified: bool = False
