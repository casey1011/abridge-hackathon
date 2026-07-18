"""Seed clinicians and ingest the admission dataset on first run.

Idempotent: does nothing if clinicians already exist. The 6 admission
encounters (inpatient / SNF / hospice) become discharge-planning Visits with
real ambient transcripts, structured SDOH profiles, the IDEAL checklist, a
scheduled coordination meeting, and agent-proposed items.
"""
from sqlmodel import Session, select

from .ingest import ingest_admissions
from .models import Clinician

_CLINICIANS = [
    Clinician(name="Dr. Amara Okafor", email="aokafor@example.org", role="physician"),
    Clinician(name="Nurse Ben Carter", email="bcarter@example.org", role="nurse"),
    Clinician(name="SW Priya Menon", email="pmenon@example.org", role="social_work"),
]


def seed(session: Session) -> None:
    if session.exec(select(Clinician)).first():
        return
    for c in _CLINICIANS:
        session.add(c)
    session.commit()
    ingest_admissions(session)
