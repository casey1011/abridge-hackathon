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
    """Where/what the encounter is.

    ED/INPATIENT/HOME are provider↔patient bedside captures (the ambient-capture
    diagram). CARE_CONFERENCE is a provider↔provider multidisciplinary rounds
    discussion *about* the patient — the social-work / care-management meeting.
    Both attach to the same Visit and both feed the reasoning agent.
    """

    ED = "ED"
    INPATIENT = "INPATIENT"
    HOME = "HOME"
    CARE_CONFERENCE = "CARE_CONFERENCE"


class EncounterStatus(str, Enum):
    """Lifecycle the mobile app polls and the reasoning agent gates on."""

    RECORDING = "recording"      # capture in progress on-device
    UPLOADED = "uploaded"        # audio received, not yet transcribed
    TRANSCRIBING = "transcribing"
    READY = "ready"              # transcript available — safe to reason over
    FAILED = "failed"


class VisitStatus(str, Enum):
    """Lifecycle of a hospital stay."""

    ACTIVE = "active"                          # admitted, in hospital
    DISCHARGE_PLANNING = "discharge_planning"  # coordination meeting phase
    DISCHARGED = "discharged"


class MeetingStatus(str, Enum):
    """The care coordination (discharge planning) meeting lifecycle."""

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ChecklistPhase(str, Enum):
    """The IDEAL Discharge Planning phases (AHRQ)."""

    INITIAL_ASSESSMENT = "initial_assessment"  # initial nursing assessment
    DAILY = "daily"                            # ongoing, every day of the stay
    PRE_MEETING = "pre_meeting"                # prior to the planning meeting
    MEETING = "meeting"                        # during the planning meeting
    DAY_OF_DISCHARGE = "day_of_discharge"


class ChecklistItemStatus(str, Enum):
    """`proposed` + `AGENT` source encode the human-review gate: agent items
    must be `accepted` in the meeting before they're worked."""

    PROPOSED = "proposed"        # agent-suggested; awaits meeting approval
    ACCEPTED = "accepted"        # approved / on the plan
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DISMISSED = "dismissed"


class ChecklistItemSource(str, Enum):
    TEMPLATE = "template"        # from the IDEAL checklist
    AGENT = "agent"             # proposed by the reasoning agent
    MANUAL = "manual"           # added by a clinician


class FindingType(str, Enum):
    """Mirrors the reasoning-agent sub-boxes in the diagram."""

    IMPLICATURE = "implicature"                # unspoken barriers
    MED_RECONCILIATION = "med_reconciliation"  # formulation / dose changes
    SDOH = "sdoh"                              # pharmacy, transit, affordability


class SdohDomain(str, Enum):
    """Social-determinant domains tracked on a patient's chart."""

    CAREGIVER = "caregiver"              # hands-on support at home
    TRANSPORTATION = "transportation"
    FOOD = "food"                        # food security / nutrition
    HOUSING = "housing"
    FINANCIAL = "financial"             # income / employment / affordability
    SOCIAL_ISOLATION = "social_isolation"
    SAFETY = "safety"                   # abuse / violence
    EDUCATION = "education"             # health-literacy proxy


class SdohRisk(str, Enum):
    OK = "ok"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


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
    gender: str | None = None
    # One-line chart background (active conditions / meds) for context.
    chart_summary: str = ""
    created_at: datetime = Field(default_factory=_now)


class Encounter(SQLModel, table=True):
    """One bedside visit — the unit of ambient capture."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    clinician_id: str = Field(foreign_key="clinician.id", index=True)
    # A stay (Visit) groups many encounters (ED -> inpatient -> home). Optional
    # so ad-hoc captures still work before a Visit exists.
    visit_id: str | None = Field(default=None, foreign_key="visit.id", index=True)
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


class Visit(SQLModel, table=True):
    """A hospital stay — groups many Encounters (ED -> inpatient -> home).

    This is the "inpatient visit" the whole discharge process hangs off of:
    it owns the discharge checklist and the care coordination meeting.
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    primary_diagnosis: str = ""
    status: VisitStatus = Field(default=VisitStatus.ACTIVE)
    admitted_at: datetime = Field(default_factory=_now)
    discharged_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class CareCoordinationMeeting(SQLModel, table=True):
    """The discharge planning meeting — the human-review gate.

    The reasoning agent fires against the visit's transcripts around this
    meeting; approved findings become `accepted` checklist items.
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    visit_id: str = Field(foreign_key="visit.id", index=True)
    status: MeetingStatus = Field(default=MeetingStatus.SCHEDULED)
    scheduled_at: datetime = Field(default_factory=_now)
    participants: str = ""   # comma-separated roles/names (hackathon-simple)
    notes: str = ""
    created_at: datetime = Field(default_factory=_now)


class AgentFinding(SQLModel, table=True):
    """One thing the reasoning agent surfaced from the transcripts.

    Each finding can spawn a `proposed` ChecklistItem that the meeting accepts
    or dismisses. Defined before ChecklistItem so its FK target exists.
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    visit_id: str = Field(foreign_key="visit.id", index=True)
    type: FindingType
    title: str
    detail: str = ""
    evidence: str = ""          # supporting quote from the transcript
    # A clarifying question the clinician could ask to close the gap. This is
    # the "implicature catch" payload — surfaced on the card in the UI.
    suggested_ask: str = ""
    confidence: float = 0.5
    # "llm" when produced by the Claude reasoning call, "rules" for the
    # deterministic fallback. Shown as provenance in the UI.
    source_engine: str = "rules"
    created_at: datetime = Field(default_factory=_now)


class ChecklistItem(SQLModel, table=True):
    """One line on a visit's discharge checklist."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    visit_id: str = Field(foreign_key="visit.id", index=True)
    phase: ChecklistPhase
    text: str
    status: ChecklistItemStatus = Field(default=ChecklistItemStatus.ACCEPTED)
    source: ChecklistItemSource = Field(default=ChecklistItemSource.TEMPLATE)
    owner_role: str = ""
    # Set when this item was spawned from a reasoning-agent finding.
    finding_id: str | None = Field(default=None, foreign_key="agentfinding.id")
    completed_by: str | None = None
    completed_at: datetime | None = None
    sort_order: int = 0
    created_at: datetime = Field(default_factory=_now)


class EhrNoteStatus(str, Enum):
    DRAFT = "draft"    # generated, awaiting SW review
    FILED = "filed"    # signed off and pushed to the EHR chart


class EhrNote(SQLModel, table=True):
    """An AI-drafted, up-to-date discharge-planning / social-work note.

    The social worker generates it from the current visit picture (chart, SDOH,
    rounds decisions, accepted plan), reviews, and files it to the EHR chart —
    closing the loop back to the EHR box in the diagram.
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    visit_id: str = Field(foreign_key="visit.id", index=True)
    text: str = ""
    status: EhrNoteStatus = Field(default=EhrNoteStatus.DRAFT)
    model: str = ""
    created_at: datetime = Field(default_factory=_now)
    filed_at: datetime | None = None


class SdohFactor(SQLModel, table=True):
    """One social-determinant factor on a patient's chart.

    Derived from structured Synthea condition findings and/or the ambient
    transcript; `source` records which, and `evidence` carries a grounding
    quote when it came from the conversation.
    """

    id: str = Field(default_factory=_uuid, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    domain: SdohDomain
    risk: SdohRisk = Field(default=SdohRisk.UNKNOWN)
    detail: str = ""
    source: str = "chart"        # "chart" | "transcript" | "chart+transcript"
    evidence: str = ""
    created_at: datetime = Field(default_factory=_now)
