"""Ingest the repo-local admission dataset into the app's domain model.

Each slim record (one admission encounter) becomes a Patient + Visit +
Encounter + Transcript, a structured SDOH profile (see `sdoh.derive_factors`),
the standard IDEAL checklist, and a scheduled coordination meeting. The
reasoning agent is then run so each stay opens with grounded proposed items.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from sqlmodel import Session, select

from .checklist import template_items
from .models import (
    CareCoordinationMeeting,
    Clinician,
    Encounter,
    EncounterSetting,
    EncounterStatus,
    MeetingStatus,
    Patient,
    SdohFactor,
    Transcript,
    Visit,
    VisitStatus,
)
from .sdoh import derive_factors

_DATA = Path(__file__).resolve().parent / "data" / "admissions.json"


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _chart_summary(record: dict) -> str:
    """One-line clinical background: top disorders + top meds."""
    disorders = [c for c in record.get("condition_labels", []) if "(disorder)" in c][:3]
    meds = [m.split(" ")[0:3] for m in record.get("medication_labels", [])[:3]]
    parts = []
    if disorders:
        parts.append("Active: " + ", ".join(d.replace(" (disorder)", "") for d in disorders))
    if meds:
        parts.append("Meds: " + ", ".join(" ".join(m) for m in meds))
    return " · ".join(parts)


def ingest_admissions(session: Session) -> int:
    """Create a Visit per admission record. Returns the count ingested."""
    records = json.loads(_DATA.read_text())
    physician = session.exec(select(Clinician).where(Clinician.role == "physician")).first()
    nurse = session.exec(select(Clinician).where(Clinician.role == "nurse")).first()

    for record in records:
        patient = Patient(
            mrn=f"SYN-{record['fhir_patient_id'][:8]}",
            display_name=record["display_name"],
            dob=record.get("birth_date"),
            gender=record.get("gender"),
            chart_summary=_chart_summary(record),
        )
        session.add(patient)
        session.commit()
        session.refresh(patient)

        # Structured SDOH profile.
        for f in derive_factors(record):
            session.add(SdohFactor(patient_id=patient.id, **f))

        admitted = _parse_dt(record["date"])
        visit = Visit(
            patient_id=patient.id,
            primary_diagnosis=record["visit_title"],
            status=VisitStatus.DISCHARGE_PLANNING,
            admitted_at=admitted,
        )
        session.add(visit)
        session.commit()
        session.refresh(visit)

        enc = Encounter(
            patient_id=patient.id,
            clinician_id=(physician or nurse).id,
            visit_id=visit.id,
            setting=EncounterSetting.INPATIENT,
            status=EncounterStatus.READY,
            started_at=admitted,
            ended_at=admitted + timedelta(minutes=20),
        )
        session.add(enc)
        session.commit()
        session.refresh(enc)

        session.add(
            Transcript(
                encounter_id=enc.id,
                text=record["transcript"],
                model="dataset",
                status=EncounterStatus.READY,
            )
        )
        for item in template_items(visit.id):
            session.add(item)
        session.add(
            CareCoordinationMeeting(
                visit_id=visit.id,
                status=MeetingStatus.SCHEDULED,
                scheduled_at=admitted + timedelta(days=1),
                participants=f"{physician.name}, {nurse.name}, SW Priya Menon",
            )
        )
        session.commit()

    return len(records)
