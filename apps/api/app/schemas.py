"""API request/response DTOs. Keep in sync with packages/shared/src/index.ts.

These are the flat, join-friendly shapes the clients consume — distinct from
the ORM tables in models.py.
"""
from pydantic import BaseModel

from .models import EncounterSetting, EncounterStatus


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


class CreateEncounterRequest(BaseModel):
    patient_id: str
    clinician_id: str
    setting: EncounterSetting


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
