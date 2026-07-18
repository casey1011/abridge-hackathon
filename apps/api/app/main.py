"""Abridge — ambient capture API.

Flow: pick clinician + patient + setting -> POST /encounters -> record on
device -> POST /encounters/{id}/recordings (audio) -> transcription runs in
the background -> status flips to `ready` -> GET /encounters/{id} for the text.

Run:  uv run uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from .checklist import template_items
from .config import settings
from .db import engine, get_session, init_db
from .ehr import generate_note
from .models import (
    AgentFinding,
    CareCoordinationMeeting,
    ChecklistItem,
    ChecklistItemStatus,
    Clinician,
    EhrNote,
    EhrNoteStatus,
    Encounter,
    EncounterSetting,
    EncounterStatus,
    Patient,
    Recording,
    SdohFactor,
    Transcript,
    Visit,
    VisitStatus,
)
from .reasoning import run_reasoning
from .schemas import (
    AgentFindingRead,
    CareConferenceRequest,
    ChecklistItemRead,
    ClinicianRead,
    CreateEncounterRequest,
    CreateVisitRequest,
    EhrNoteRead,
    EncounterDetail,
    EncounterRead,
    FileEhrNoteRequest,
    HealthResponse,
    MeetingRead,
    PatientRead,
    SdohFactorRead,
    TranscriptRead,
    UpdateChecklistItemRequest,
    UpdateMeetingRequest,
    VisitDetail,
    VisitRead,
)
from .seed import seed
from .storage import read_audio, save_audio
from .transcription import transcribe


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        seed(session)
    yield


app = FastAPI(title="Abridge API", lifespan=lifespan)

# Open CORS for hackathon convenience (web dev server + Expo). Tighten later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- serialization helpers -------------------------------------------------


def _encounter_read(enc: Encounter, session: Session) -> EncounterRead:
    patient = session.get(Patient, enc.patient_id)
    clinician = session.get(Clinician, enc.clinician_id)
    return EncounterRead(
        id=enc.id,
        setting=enc.setting,
        status=enc.status,
        started_at=enc.started_at.isoformat(),
        patient=PatientRead(
            id=patient.id, mrn=patient.mrn, display_name=patient.display_name,
            gender=patient.gender, chart_summary=patient.chart_summary,
        ),
        clinician=ClinicianRead(id=clinician.id, name=clinician.name, role=clinician.role),
    )


def _visit_encounters(visit_id: str, session: Session) -> list[Encounter]:
    return session.exec(
        select(Encounter).where(Encounter.visit_id == visit_id).order_by(Encounter.started_at)
    ).all()


def _visit_checklist(visit_id: str, session: Session) -> list[ChecklistItem]:
    return session.exec(
        select(ChecklistItem)
        .where(ChecklistItem.visit_id == visit_id)
        .order_by(ChecklistItem.sort_order, ChecklistItem.created_at)
    ).all()


def _visit_read(visit: Visit, session: Session) -> VisitRead:
    patient = session.get(Patient, visit.patient_id)
    items = _visit_checklist(visit.id, session)
    open_items = sum(
        1
        for i in items
        if i.status in (ChecklistItemStatus.ACCEPTED, ChecklistItemStatus.IN_PROGRESS)
    )
    proposed = sum(1 for i in items if i.status == ChecklistItemStatus.PROPOSED)
    return VisitRead(
        id=visit.id,
        status=visit.status,
        primary_diagnosis=visit.primary_diagnosis,
        admitted_at=visit.admitted_at.isoformat(),
        patient=PatientRead(
            id=patient.id, mrn=patient.mrn, display_name=patient.display_name,
            gender=patient.gender, chart_summary=patient.chart_summary,
        ),
        encounter_count=len(_visit_encounters(visit.id, session)),
        open_item_count=open_items,
        proposed_count=proposed,
    )


def _meeting_read(meeting: CareCoordinationMeeting) -> MeetingRead:
    return MeetingRead(
        id=meeting.id,
        status=meeting.status,
        scheduled_at=meeting.scheduled_at.isoformat(),
        participants=meeting.participants,
        notes=meeting.notes,
    )


def _checklist_item_read(item: ChecklistItem) -> ChecklistItemRead:
    return ChecklistItemRead(
        id=item.id,
        phase=item.phase,
        text=item.text,
        status=item.status,
        source=item.source,
        owner_role=item.owner_role,
        finding_id=item.finding_id,
        completed_at=item.completed_at.isoformat() if item.completed_at else None,
    )


def _visit_detail(visit: Visit, session: Session) -> VisitDetail:
    base = _visit_read(visit, session)
    meeting = session.exec(
        select(CareCoordinationMeeting)
        .where(CareCoordinationMeeting.visit_id == visit.id)
        .order_by(CareCoordinationMeeting.scheduled_at.desc())
    ).first()
    findings = session.exec(
        select(AgentFinding)
        .where(AgentFinding.visit_id == visit.id)
        .order_by(AgentFinding.created_at)
    ).all()
    sdoh = session.exec(
        select(SdohFactor)
        .where(SdohFactor.patient_id == visit.patient_id)
        .order_by(SdohFactor.created_at)
    ).all()
    return VisitDetail(
        **base.model_dump(),
        encounters=[_encounter_read(e, session) for e in _visit_encounters(visit.id, session)],
        meeting=_meeting_read(meeting) if meeting else None,
        findings=[
            AgentFindingRead(
                id=f.id,
                type=f.type,
                title=f.title,
                detail=f.detail,
                evidence=f.evidence,
                suggested_ask=f.suggested_ask,
                confidence=f.confidence,
                source_engine=f.source_engine,
            )
            for f in findings
        ],
        checklist=[_checklist_item_read(i) for i in _visit_checklist(visit.id, session)],
        sdoh=[
            SdohFactorRead(
                domain=f.domain, risk=f.risk, detail=f.detail,
                source=f.source, evidence=f.evidence,
            )
            for f in sdoh
        ],
        ehr_note=_latest_note_read(visit.id, session),
    )


def _latest_note_read(visit_id: str, session: Session) -> EhrNoteRead | None:
    note = session.exec(
        select(EhrNote)
        .where(EhrNote.visit_id == visit_id)
        .order_by(EhrNote.created_at.desc())
    ).first()
    if note is None:
        return None
    return EhrNoteRead(
        id=note.id,
        status=note.status,
        text=note.text,
        model=note.model,
        created_at=note.created_at.isoformat(),
        filed_at=note.filed_at.isoformat() if note.filed_at else None,
    )


# --- background transcription ----------------------------------------------


def _run_transcription(encounter_id: str, file_uri: str, filename: str) -> None:
    """Transcribe an encounter's audio, then flip status to ready/failed.

    Runs in a FastAPI BackgroundTask with its own DB session.
    """
    with Session(engine) as session:
        enc = session.get(Encounter, encounter_id)
        if enc is None:
            return
        enc.status = EncounterStatus.TRANSCRIBING
        session.add(enc)
        session.commit()

        try:
            text = transcribe(read_audio(file_uri), filename=filename).strip()
            status = EncounterStatus.READY
        except Exception as exc:  # keep the encounter recoverable, don't crash the worker
            text = f"[transcription failed: {exc}]"
            status = EncounterStatus.FAILED

        transcript = session.exec(
            select(Transcript).where(Transcript.encounter_id == encounter_id)
        ).first()
        if transcript is None:
            transcript = Transcript(encounter_id=encounter_id)
        transcript.text = text
        transcript.model = settings.groq_transcribe_model
        transcript.status = status
        transcript.updated_at = datetime.now(timezone.utc)
        session.add(transcript)

        enc.status = status
        session.add(enc)
        session.commit()


# --- routes ----------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/clinicians", response_model=list[ClinicianRead])
def list_clinicians(session: Session = Depends(get_session)) -> list[Clinician]:
    return session.exec(select(Clinician)).all()


@app.get("/patients", response_model=list[PatientRead])
def list_patients(session: Session = Depends(get_session)) -> list[Patient]:
    return session.exec(select(Patient)).all()


@app.post("/encounters", response_model=EncounterRead)
def create_encounter(
    body: CreateEncounterRequest, session: Session = Depends(get_session)
) -> EncounterRead:
    if session.get(Patient, body.patient_id) is None:
        raise HTTPException(404, "patient not found")
    if session.get(Clinician, body.clinician_id) is None:
        raise HTTPException(404, "clinician not found")
    if body.visit_id is not None and session.get(Visit, body.visit_id) is None:
        raise HTTPException(404, "visit not found")
    # Auto-attach to the patient's active stay when no visit is given, so every
    # capture (bedside or rounds) shows up on that patient's discharge board.
    visit_id = body.visit_id
    if visit_id is None:
        visit = session.exec(
            select(Visit)
            .where(Visit.patient_id == body.patient_id)
            .order_by(Visit.admitted_at.desc())
        ).first()
        visit_id = visit.id if visit else None
    enc = Encounter(
        patient_id=body.patient_id,
        clinician_id=body.clinician_id,
        setting=body.setting,
        visit_id=visit_id,
    )
    session.add(enc)
    session.commit()
    session.refresh(enc)
    return _encounter_read(enc, session)


@app.get("/encounters", response_model=list[EncounterRead])
def list_encounters(session: Session = Depends(get_session)) -> list[EncounterRead]:
    encounters = session.exec(
        select(Encounter).order_by(Encounter.started_at.desc())
    ).all()
    return [_encounter_read(e, session) for e in encounters]


@app.get("/encounters/{encounter_id}", response_model=EncounterDetail)
def get_encounter(
    encounter_id: str, session: Session = Depends(get_session)
) -> EncounterDetail:
    enc = session.get(Encounter, encounter_id)
    if enc is None:
        raise HTTPException(404, "encounter not found")
    base = _encounter_read(enc, session)
    transcript = session.exec(
        select(Transcript).where(Transcript.encounter_id == encounter_id)
    ).first()
    return EncounterDetail(
        **base.model_dump(),
        transcript=(
            TranscriptRead(
                text=transcript.text,
                status=transcript.status,
                model=transcript.model,
                language=transcript.language,
            )
            if transcript
            else None
        ),
    )


@app.post("/encounters/{encounter_id}/recordings", response_model=EncounterDetail)
async def add_recording(
    encounter_id: str,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    duration_seconds: float | None = Form(None),
    sequence: int = Form(0),
    session: Session = Depends(get_session),
) -> EncounterDetail:
    """Upload a captured audio clip and kick off transcription in the background."""
    enc = session.get(Encounter, encounter_id)
    if enc is None:
        raise HTTPException(404, "encounter not found")

    audio = await file.read()
    filename = file.filename or "audio.m4a"
    file_uri, size = save_audio(audio, filename)

    recording = Recording(
        encounter_id=encounter_id,
        file_uri=file_uri,
        mime_type=file.content_type or "audio/m4a",
        duration_seconds=duration_seconds,
        size_bytes=size,
        sequence=sequence,
    )
    session.add(recording)

    enc.status = EncounterStatus.UPLOADED
    enc.ended_at = datetime.now(timezone.utc)
    session.add(enc)
    session.commit()

    background.add_task(_run_transcription, encounter_id, file_uri, filename)
    return get_encounter(encounter_id, session)


# --- visits / coordination / checklist -------------------------------------


@app.get("/visits", response_model=list[VisitRead])
def list_visits(session: Session = Depends(get_session)) -> list[VisitRead]:
    visits = session.exec(select(Visit).order_by(Visit.admitted_at.desc())).all()
    return [_visit_read(v, session) for v in visits]


@app.post("/visits", response_model=VisitDetail)
def create_visit(
    body: CreateVisitRequest, session: Session = Depends(get_session)
) -> VisitDetail:
    if session.get(Patient, body.patient_id) is None:
        raise HTTPException(404, "patient not found")
    visit = Visit(patient_id=body.patient_id, primary_diagnosis=body.primary_diagnosis)
    session.add(visit)
    session.commit()
    session.refresh(visit)
    # Seed the standard IDEAL checklist for the new stay.
    for item in template_items(visit.id):
        session.add(item)
    session.commit()
    return _visit_detail(visit, session)


@app.get("/visits/{visit_id}", response_model=VisitDetail)
def get_visit(visit_id: str, session: Session = Depends(get_session)) -> VisitDetail:
    visit = session.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(404, "visit not found")
    return _visit_detail(visit, session)


@app.post("/visits/{visit_id}/reasoning/run", response_model=VisitDetail)
def run_visit_reasoning(
    visit_id: str, session: Session = Depends(get_session)
) -> VisitDetail:
    """Fire the reasoning agent over the visit's transcripts.

    Writes AgentFindings + `proposed` checklist items, and moves the stay into
    the discharge-planning phase.
    """
    visit = session.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(404, "visit not found")
    run_reasoning(visit_id, session)
    if visit.status == VisitStatus.ACTIVE:
        visit.status = VisitStatus.DISCHARGE_PLANNING
        session.add(visit)
        session.commit()
    session.refresh(visit)
    return _visit_detail(visit, session)


# A canned multidisciplinary-rounds transcript — the mic-free demo fallback for
# the provider↔provider care conference. It RESOLVES the bedside implicature and
# commits the team to concrete actions, so re-running the agent visibly updates
# the plan.
_CANNED_ROUNDS = """SW: Alright, discharge rounds on Mrs. Bellweather, heart failure, targeting tomorrow. I want to flag what came up in her bedside recording — she agreed to daily weights but let slip she has no working scale, and her daughter Renee, who used to help, moved to Arizona.
DR: Right, that's exactly the kind of thing that bounces her back in a week.
SW: So I actually got Renee on the phone this morning. She can't relocate, but she'll do a nightly video check-in and help her read the numbers over the phone.
NURSE: Good. And for the scale itself?
SW: Let's order a DME bathroom scale, delivered before discharge, not a prescription she has to go pick up.
DR: Agreed. And enroll her in the heart-failure telehealth nurse program so someone is watching those daily weights remotely, not just her.
PHARMACIST: On the medication side — I confirmed the copay assistance card for the fluticasone-salmeterol inhaler went through, so the hundred-dollar cost that made her skip it last time is handled. I'll also do a final reconciliation on the Lasix-to-furosemide and the metoprolol succinate switch at the bedside.
NURSE: I'll do teach-back on the red-flag symptoms and the new once-daily metoprolol before she leaves.
SW: And a home-health evaluation for the first week given she's now living alone. I think that covers the gaps.
DR: That's a safe discharge. Let's do it."""


@app.post("/visits/{visit_id}/care-conference", response_model=VisitDetail)
def add_care_conference(
    visit_id: str,
    body: CareConferenceRequest,
    session: Session = Depends(get_session),
) -> VisitDetail:
    """Attach a provider↔provider rounds transcript to the visit.

    Mobile records the meeting live (setting=CARE_CONFERENCE, visit_id) and hits
    the normal upload/transcribe path; this endpoint is the mic-free fallback —
    with no body it drops the canned rounds transcript on the visit. Either way
    the transcript then feeds the reasoning agent on the next run.
    """
    visit = session.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(404, "visit not found")

    clinician = session.exec(
        select(Clinician).where(Clinician.role == "social_work")
    ).first() or session.exec(select(Clinician)).first()

    enc = Encounter(
        patient_id=visit.patient_id,
        clinician_id=clinician.id,
        visit_id=visit_id,
        setting=EncounterSetting.CARE_CONFERENCE,
        status=EncounterStatus.READY,
        ended_at=datetime.now(timezone.utc),
    )
    session.add(enc)
    session.commit()
    session.refresh(enc)

    session.add(
        Transcript(
            encounter_id=enc.id,
            text=(body.text or _CANNED_ROUNDS).strip(),
            model="care-conference",
            status=EncounterStatus.READY,
        )
    )
    session.commit()
    return _visit_detail(visit, session)


@app.post("/visits/{visit_id}/ehr-note", response_model=VisitDetail)
def create_ehr_note(
    visit_id: str, session: Session = Depends(get_session)
) -> VisitDetail:
    """Generate a fresh, up-to-date discharge-planning note (draft) for the SW."""
    visit = session.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(404, "visit not found")
    text, model = generate_note(visit_id, session)
    session.add(EhrNote(visit_id=visit_id, text=text, model=model))
    session.commit()
    return _visit_detail(visit, session)


@app.patch("/ehr-notes/{note_id}", response_model=EhrNoteRead)
def file_ehr_note(
    note_id: str,
    body: FileEhrNoteRequest,
    session: Session = Depends(get_session),
) -> EhrNoteRead:
    """File the reviewed note to the EHR chart — closes the loop to the EHR."""
    note = session.get(EhrNote, note_id)
    if note is None:
        raise HTTPException(404, "note not found")
    note.status = body.status
    note.filed_at = (
        datetime.now(timezone.utc) if body.status == EhrNoteStatus.FILED else None
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    return _latest_note_read(visit_id=note.visit_id, session=session)  # type: ignore[return-value]


@app.patch("/checklist-items/{item_id}", response_model=ChecklistItemRead)
def update_checklist_item(
    item_id: str,
    body: UpdateChecklistItemRequest,
    session: Session = Depends(get_session),
) -> ChecklistItemRead:
    """The human-review gate: accept/dismiss proposed items, mark work done."""
    item = session.get(ChecklistItem, item_id)
    if item is None:
        raise HTTPException(404, "checklist item not found")
    item.status = body.status
    item.completed_at = (
        datetime.now(timezone.utc) if body.status == ChecklistItemStatus.DONE else None
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return _checklist_item_read(item)


@app.patch("/meetings/{meeting_id}", response_model=MeetingRead)
def update_meeting(
    meeting_id: str,
    body: UpdateMeetingRequest,
    session: Session = Depends(get_session),
) -> MeetingRead:
    meeting = session.get(CareCoordinationMeeting, meeting_id)
    if meeting is None:
        raise HTTPException(404, "meeting not found")
    if body.status is not None:
        meeting.status = body.status
    if body.notes is not None:
        meeting.notes = body.notes
    session.add(meeting)
    session.commit()
    session.refresh(meeting)
    return _meeting_read(meeting)
