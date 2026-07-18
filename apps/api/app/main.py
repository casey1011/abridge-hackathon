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

from .config import settings
from .db import engine, get_session, init_db
from .models import (
    Clinician,
    Encounter,
    EncounterSetting,
    EncounterStatus,
    Patient,
    Recording,
    Transcript,
)
from .schemas import (
    ClinicianRead,
    CreateEncounterRequest,
    EncounterDetail,
    EncounterRead,
    HealthResponse,
    PatientRead,
    TranscriptRead,
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
        patient=PatientRead(id=patient.id, mrn=patient.mrn, display_name=patient.display_name),
        clinician=ClinicianRead(id=clinician.id, name=clinician.name, role=clinician.role),
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
    enc = Encounter(
        patient_id=body.patient_id,
        clinician_id=body.clinician_id,
        setting=body.setting,
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
