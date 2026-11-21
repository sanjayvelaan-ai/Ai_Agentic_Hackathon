"""Typed tool contracts for the six bounded, auditable workflow roles.

Offline operation uses deterministic tools and is labeled accordingly.
Model-enabled scouting/copywriting may reason over bounded evidence; approval
and side effects always remain deterministic server responsibilities.
"""
from typing import Literal
from pydantic import BaseModel, Field

class ScoutProposal(BaseModel):
    first: int = Field(ge=0)
    last: int = Field(ge=0)
    title: str = Field(min_length=1,max_length=120)
    reason: str = Field(min_length=1,max_length=500)

class ScoutResult(BaseModel):
    clips: list[ScoutProposal] = Field(max_length=6)

class Rubric(BaseModel):
    clarity: float = Field(ge=0,le=5)
    usefulness: float = Field(ge=0,le=5)
    opening_hook: float = Field(ge=0,le=5)
    brand_relevance: float = Field(ge=0,le=5)

class Candidate(BaseModel):
    id: str
    source_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    headline: str
    topical_hook: str
    rubric: Rubric
    evidence_segment_ids: list[int]
    exact_quote: str
    selection_reason: str

class CopyProposal(BaseModel):
    platform: Literal['instagram','youtube','linkedin']
    angle: Literal['Teach It','Tell It','Challenge It']
    text: str = Field(min_length=3,max_length=2500)

class CopyResult(BaseModel):
    copies: list[CopyProposal] = Field(min_length=9,max_length=9)

class AgentEvent(BaseModel):
    agent: str
    tool: str
    status: str
    provider: str = 'deterministic'
    job_id: str | None = None
    summary: str = Field(max_length=1000)

ROLES = [
    ('Ingestion Agent','probe_media / align_transcript / transcribe_media'),
    ('Content Scout','get_transcript_segments / validate_clip_proposal / rank_candidates'),
    ('Remix Director','render_video_clip'),
    ('Platform Copywriter','get_brand_rules / generate_platform_copy'),
    ('Brand Memory Curator','suggest_brand_rule / request_human_approval'),
    ('Calendar + Feedback','save_calendar_entry / import_metrics / compute_engagement_summary'),
]
