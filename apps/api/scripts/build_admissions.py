"""Build-time: extract the discharge-relevant records from the hackathon dataset.

Reads the full `synthetic-ambient-fhir-25` dataset (kept in ~/Downloads, not in
the repo) and writes a slim, repo-local `app/data/admissions.json` holding only
the 6 admission-type encounters (inpatient / SNF / hospice) — the ones that
need discharge planning. Each slim record keeps the patient facts, the Synthea
condition findings (which carry structured SDOH), medication labels, and the
ambient transcript + note. Runtime code never touches ~/Downloads.

Usage:  uv run python scripts/build_admissions.py
"""
import json
import re
from pathlib import Path

SRC = Path.home() / "Downloads" / "synthetic-ambient-fhir-25" / "synthetic-ambient-fhir-25.jsonl"
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "admissions.json"

ADMISSION_KEYS = ("admission", "isolation", "hospice")


def clean_name(patient: dict) -> str:
    n = patient["name"][0]
    prefix = " ".join(n.get("prefix", []))
    given = n.get("given", ["Unknown"])[0]
    family = re.sub(r"\d+", "", n["family"])  # Synthea appends digits
    return " ".join(x for x in (prefix, given, family) if x).strip()


def slim(record: dict) -> dict:
    m = record["metadata"]
    pc = record["patient_context"]
    patient = pc["patient"]
    summary = pc["longitudinal_summary"]
    return {
        "fhir_patient_id": m["patient_id"],
        "fhir_encounter_id": m["encounter_id"],
        "display_name": clean_name(patient),
        "gender": patient.get("gender"),
        "birth_date": patient.get("birthDate"),
        "marital_status": patient.get("maritalStatus", {}).get("text"),
        "date": m["date"],
        "visit_title": m["visit_title"],
        "visit_type": m["visit_type"],
        "condition_labels": summary.get("condition_labels", []),
        "medication_labels": summary.get("medication_labels", []),
        "transcript": record["transcript"],
        "note": record["note"],
        "after_visit_summary": record["after_visit_summary"],
    }


def main() -> None:
    records = [json.loads(line) for line in SRC.open()]
    admissions = [
        slim(r)
        for r in records
        if any(k in r["metadata"]["visit_type"].lower() for k in ADMISSION_KEYS)
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(admissions, indent=1))
    print(f"wrote {len(admissions)} admission records -> {OUT}")
    for a in admissions:
        print(f"  - {a['display_name']}: {a['visit_title']}")


if __name__ == "__main__":
    main()
