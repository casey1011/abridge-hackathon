"""Seed a couple of clinicians and demo patients on first run.

Idempotent: does nothing if clinicians already exist.
"""
from sqlmodel import Session, select

from .models import Clinician, Patient

_CLINICIANS = [
    Clinician(name="Dr. Amara Okafor", email="aokafor@example.org", role="physician"),
    Clinician(name="Nurse Ben Carter", email="bcarter@example.org", role="nurse"),
]

_PATIENTS = [
    Patient(mrn="MRN-1001", display_name="Jane Doe", dob="1958-03-12"),
    Patient(mrn="MRN-1002", display_name="Robert Nguyen", dob="1972-11-02"),
    Patient(mrn="MRN-1003", display_name="Maria Alvarez", dob="1990-06-25"),
    Patient(mrn="MRN-1004", display_name="Sam Whitfield", dob="1945-01-30"),
]


def seed(session: Session) -> None:
    if session.exec(select(Clinician)).first():
        return
    for row in (*_CLINICIANS, *_PATIENTS):
        session.add(row)
    session.commit()
