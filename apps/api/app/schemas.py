"""API request/response DTOs. Keep in sync with packages/shared/src/index.ts.

These are the flat, join-friendly shapes the clients consume — distinct from
the ORM tables in models.py.
"""
from pydantic import BaseModel

from .models import (
    ChecklistItemSource,
    ChecklistItemStatus,
    ChecklistPhase,
    EhrNoteStatus,
    EncounterSetting,
    EncounterStatus,
    FindingType,
    MeetingStatus,
    SdohDomain,
    SdohRisk,
    VisitStatus,
)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "abridge-api"


class ClinicianRead(BaseModel):
    id: str
    name: str
    role: str


class PatientRead(BaseModel):
    id: str
    mrn: str
    display_name: str
    gender: str | None = None
    chart_summary: str = ""


class CreateEncounterRequest(BaseModel):
    patient_id: str
    clinician_id: str
    setting: EncounterSetting
    visit_id: str | None = None


class TranscriptRead(BaseModel):
    text: str
    status: EncounterStatus
    model: str
    language: str | None = None


class EncounterRead(BaseModel):
    """List-view row: everything the app needs without a second request."""

    id: str
    setting: EncounterSetting
    status: EncounterStatus
    started_at: str  # ISO 8601
    patient: PatientRead
    clinician: ClinicianRead


class EncounterDetail(EncounterRead):
    """Detail view: adds the transcript once it's ready."""

    transcript: TranscriptRead | None = None


# --- discharge / coordination DTOs -----------------------------------------


class MeetingRead(BaseModel):
    id: str
    status: MeetingStatus
    scheduled_at: str  # ISO 8601
    participants: str
    notes: str


class AgentFindingRead(BaseModel):
    id: str
    type: FindingType
    title: str
    detail: str
    evidence: str
    suggested_ask: str = ""
    confidence: float
    source_engine: str = "rules"


class ChecklistItemRead(BaseModel):
    id: str
    phase: ChecklistPhase
    text: str
    status: ChecklistItemStatus
    source: ChecklistItemSource
    owner_role: str
    finding_id: str | None = None
    completed_at: str | None = None


class VisitRead(BaseModel):
    """List-view row for the coordination board."""

    id: str
    status: VisitStatus
    primary_diagnosis: str
    admitted_at: str  # ISO 8601
    patient: PatientRead
    encounter_count: int
    open_item_count: int      # accepted/in-progress, not yet done
    proposed_count: int       # agent items awaiting the review gate


class SdohFactorRead(BaseModel):
    domain: SdohDomain
    risk: SdohRisk
    detail: str
    source: str
    evidence: str


class EhrNoteRead(BaseModel):
    id: str
    status: EhrNoteStatus
    text: str
    model: str = ""
    created_at: str
    filed_at: str | None = None


class VisitDetail(VisitRead):
    """Everything the coordination view needs for one stay."""

    encounters: list[EncounterRead]
    meeting: MeetingRead | None = None
    findings: list[AgentFindingRead]
    checklist: list[ChecklistItemRead]
    sdoh: list[SdohFactorRead]
    ehr_note: EhrNoteRead | None = None


class CreateVisitRequest(BaseModel):
    patient_id: str
    primary_diagnosis: str = ""


class CareConferenceRequest(BaseModel):
    # Optional transcript text; when omitted the server uses a canned rounds
    # transcript so the demo has a mic-free fallback.
    text: str | None = None


class UpdateChecklistItemRequest(BaseModel):
    status: ChecklistItemStatus


class FileEhrNoteRequest(BaseModel):
    status: EhrNoteStatus = EhrNoteStatus.FILED


class UpdateMeetingRequest(BaseModel):
    status: MeetingStatus | None = None
    notes: str | None = None
