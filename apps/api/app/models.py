"""Ambient-capture data model.

The `Encounter` + its `Transcript` are the clean hand-off artifact the
downstream reasoning agent will consume. Everything else exists to produce
them: who recorded (Clinician), about whom (Patient), and the raw audio
(Recording).
"""
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EncounterSetting(str, Enum):
    """Where the encounter happened — mirrors the ambient-capture diagram."""

    ED = "ED"
    INPATIENT = "INPATIENT"
    HOME = "HOME"


class EncounterStatus(str, Enum):
    """Lifecycle the mobile app polls and the reasoning agent gates on."""

    RECORDING = "recording"      # capture in progress on-device
    UPLOADED = "uploaded"        # audio received, not yet transcribed
    TRANSCRIBING = "transcribing"
    READY = "ready"              # transcript available — safe to reason over
    FAILED = "failed"


class Clinician(SQLModel, table=True):
    """The healthcare worker doing the recording."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    email: str
    role: str = "clinician"
    created_at: datetime = Field(default_factory=_now)


class Patient(SQLModel, table=True):
    """The subject of the encounter. Minimal PHI for the hackathon."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    mrn: str = Field(index=True)
    display_name: str
    dob: str | None = None  # ISO date; optional
    created_at: datetime = Field(default_factory=_now)


class Encounter(SQLModel, table=True):
    """One bedside visit — the unit of ambient capture."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    clinician_id: str = Field(foreign_key="clinician.id", index=True)
    setting: EncounterSetting
    status: EncounterStatus = Field(default=EncounterStatus.RECORDING)
    started_at: datetime = Field(default_factory=_now)
    ended_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class Recording(SQLModel, table=True):
    """A captured audio segment for an encounter.

    `sequence` lets one encounter hold multiple clips (pause / resume).
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    encounter_id: str = Field(foreign_key="encounter.id", index=True)
    file_uri: str  # local path today; s3:// URI later
    mime_type: str = "audio/m4a"
    duration_seconds: float | None = None
    size_bytes: int | None = None
    sequence: int = 0
    created_at: datetime = Field(default_factory=_now)


class Transcript(SQLModel, table=True):
    """The transcription result — one per encounter, the agent's input."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    encounter_id: str = Field(foreign_key="encounter.id", index=True, unique=True)
    text: str = ""
    model: str = ""
    language: str | None = None
    status: EncounterStatus = Field(default=EncounterStatus.TRANSCRIBING)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
