"""
limes_outpost.api.schemas
~~~~~~~~~~~~~~~~~~~~~~
All Pydantic request/response models in one file for Phase 4.
Split into separate files per domain if they grow large.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, EmailStr, field_validator


# ─────────────────────────────────────────────────────────────
#  Auth
# ─────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:    EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"


class UserResponse(BaseModel):
    id:         uuid.UUID
    email:      str
    created_at: datetime


# ─────────────────────────────────────────────────────────────
#  Ventures
# ─────────────────────────────────────────────────────────────

class VentureCreateRequest(BaseModel):
    id: str
    name: str
    brand_profile: dict
    personal_profile: Optional[dict] = None
    workflow_schedule: Optional[dict] = None  # This fixes the AttributeError
    timezone: Optional[str] = "UTC"
    tts_voice_id: Optional[str] = "21m00Tcm4TlvDq8ikWAM" # Default to Rachel


class VenturePatchRequest(BaseModel):
    name:              Optional[str]  = None
    brand_profile:     Optional[dict] = None
    personal_profile:  Optional[dict] = None
    workflow_schedule: Optional[dict] = None
    timezone:          Optional[str]  = None
    status:            Optional[str]  = None
    tts_voice_id:      Optional[str]  = None


class VentureResponse(BaseModel):
    id:                str
    name:              str
    brand_profile:     dict
    personal_profile:  dict
    status:            str
    workflow_schedule: dict
    timezone:          str
    tts_voice_id:      str
    role:              str  # "operator" or "viewer"


class MemberInviteRequest(BaseModel):
    email: EmailStr
    role:  str = "operator"

    @field_validator("role")
    @classmethod
    def valid_role(cls, v):
        if v not in ("operator", "viewer"):
            raise ValueError("Role must be 'operator' or 'viewer'.")
        return v


# ─────────────────────────────────────────────────────────────
#  Pipeline
# ─────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    topic:       Optional[str] = None
    campaign_id: Optional[int] = None


class PipelineRunResponse(BaseModel):
    campaign_id: Optional[int]
    task_id:     str
    status:      str = "queued"


class PipelineStepResponse(BaseModel):
    step_id:    str
    topic:      str
    status:     str
    created_at: datetime
    updated_at: Optional[datetime] = None


class PipelineProgressResponse(BaseModel):
    campaign_id: int
    venture_id:  str
    steps:       list[PipelineStepResponse]
    overall:     str           # pending / running / completed / failed


# ─────────────────────────────────────────────────────────────
#  Queue
# ─────────────────────────────────────────────────────────────

class QueueItemResponse(BaseModel):
    id:          uuid.UUID
    venture_id:  str
    platform:    str
    status:      str
    title:       Optional[str]
    description: Optional[str]
    tags:        Optional[list[str]]
    created_at:  datetime
    scheduled_for: Optional[datetime] = None


class QueuePatchRequest(BaseModel):
    action:       str                   # approve / reject / edit
    title:        Optional[str] = None
    description:  Optional[str] = None
    tags:         Optional[list[str]] = None
    scheduled_for: Optional[datetime] = None
    reason:       Optional[str] = None  # rejection reason

    @field_validator("action")
    @classmethod
    def valid_action(cls, v):
        if v not in ("approve", "reject", "edit"):
            raise ValueError("action must be approve, reject, or edit.")
        return v


# ─────────────────────────────────────────────────────────────
#  Publish
# ─────────────────────────────────────────────────────────────

class PublishTriggerRequest(BaseModel):
    platform: str = "youtube"


class PublishTriggerResponse(BaseModel):
    task_id:  str
    platform: str
    status:   str = "queued"


# ─────────────────────────────────────────────────────────────
#  Analytics
# ─────────────────────────────────────────────────────────────

class AnalyticsSummaryResponse(BaseModel):
    venture_id:   str
    platform:     str
    total_views:  Optional[float]
    total_likes:  Optional[float]
    avg_ctr:      Optional[float]
    top_asset_id: Optional[uuid.UUID]
    as_of:        Optional[datetime]


class AnalyticsFeedItem(BaseModel):
    id:           uuid.UUID
    asset_id:     Optional[uuid.UUID]
    platform:     str
    metric_type:  str
    metric_value: Optional[float]
    recorded_at:  datetime


class AnalyticsFeedResponse(BaseModel):
    venture_id: str
    page:       int
    page_size:  int
    items:      list[AnalyticsFeedItem]


# ─────────────────────────────────────────────────────────────
#  Pulse
# ─────────────────────────────────────────────────────────────

class PulseResponse(BaseModel):
    venture_id: str
    task_id:    str
    status:     str = "queued"