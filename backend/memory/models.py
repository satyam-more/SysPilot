"""
Pydantic models for activity events.

EventCreate  — what a collector sends in (no id/timestamps)
Event        — the stored record (adds id, timestamps, privacy_status)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    source: Literal["filesystem", "terminal", "shell"]
    event_type: str = Field(min_length=1, max_length=64)
    evidence_type: Literal["observed", "inferred"] = "observed"
    file_path: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=512)
    content_excerpt: Optional[str] = Field(default=None, max_length=2048)
    metadata: Optional[dict[str, Any]] = None


class Event(EventCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    privacy_status: Literal["permitted", "redacted"] = "permitted"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    model_config = {"from_attributes": True}
