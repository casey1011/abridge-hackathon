"""Derive a structured SDOH profile for an ingested patient.

Two grounded sources, no fabrication:

1. **Chart** — Synthea encodes social determinants as Condition *findings*
   (e.g. "Social isolation (finding)"). `_CHART_MAP` maps those to domains.
2. **Transcript** — the acute discharge barriers (caregiver availability,
   transport, food, income) surface only in the ambient conversation.
   `_TRANSCRIPT_OVERLAY` carries factors read directly from each transcript,
   each with a grounding quote. Keyed by FHIR patient id.

`derive_factors` merges the two into one factor per domain (higher risk wins).
"""
from .models import SdohDomain, SdohRisk

_SEVERITY = {SdohRisk.UNKNOWN: 0, SdohRisk.OK: 1, SdohRisk.AT_RISK: 2, SdohRisk.CRITICAL: 3}

# (substring in condition label, domain, risk, detail)
_CHART_MAP: list[tuple[str, SdohDomain, SdohRisk, str]] = [
    ("social isolation", SdohDomain.SOCIAL_ISOLATION, SdohRisk.CRITICAL, "Documented social isolation"),
    ("limited social contact", SdohDomain.SOCIAL_ISOLATION, SdohRisk.AT_RISK, "Limited social contact"),
    ("intimate partner abuse", SdohDomain.SAFETY, SdohRisk.CRITICAL, "History of intimate partner abuse"),
    ("criminal record", SdohDomain.SAFETY, SdohRisk.AT_RISK, "Justice-system involvement (criminal record)"),
    ("not in labor force", SdohDomain.FINANCIAL, SdohRisk.AT_RISK, "Not in the labor force"),
    ("unemploy", SdohDomain.FINANCIAL, SdohRisk.AT_RISK, "Unemployed"),
    ("educated to high school", SdohDomain.EDUCATION, SdohRisk.AT_RISK, "Education to high-school level"),
    ("received higher education", SdohDomain.EDUCATION, SdohRisk.OK, "Completed higher education"),
]

# Factors read from each transcript (grounded in real quotes). domain, risk, detail, evidence.
_TRANSCRIPT_OVERLAY: dict[str, list[tuple[SdohDomain, SdohRisk, str, str]]] = {
    # Mrs. Iris Bellweather — HF inpatient (demo patient)
    "hfdemo01-0000-4000-8000-hf0000000001": [
        (SdohDomain.CAREGIVER, SdohRisk.CRITICAL,
         "Lives alone; primary caregiver (daughter Renee) relocated out of state — no one at home to help with daily-weight monitoring.",
         "My daughter Renee usually sorts out that sort of thing for me — she's the one who reads the little numbers — but she moved out to Arizona in the spring."),
        (SdohDomain.FINANCIAL, SdohRisk.AT_RISK,
         "Cost-related medication nonadherence: skipped filling the ICS/LABA inhaler due to ~$100 out-of-pocket cost.",
         "that new inhaler you gave me last time, at the pharmacy it came to near a hundred dollars. I let that one go that month. Didn't fill it."),
        (SdohDomain.TRANSPORTATION, SdohRisk.OK,
         "Neighbor provides reliable rides to follow-up appointments.",
         "My neighbor Dot drives me to those. That part's fine."),
    ],
    # Mrs. Ariane Runolfsson — COVID inpatient
    "7bd9e5b0-5d4b-f10d-9579-f4813faf9cdc": [
        (SdohDomain.CAREGIVER, SdohRisk.OK, "Daughter Teresa at bedside, helping with care and history.",
         "Teresa, her daughter. They let me gown up to help get her settled."),
        (SdohDomain.FOOD, SdohRisk.AT_RISK, "Stopped eating properly during the acute illness.",
         "By New Year's Eve she was feverish and stopped eating properly."),
    ],
    # Ms. Latoyia Wilkinson — SNF after hospitalization
    "1be66dc9-cf0b-cb78-e88e-ada9a9a5405b": [
        (SdohDomain.CAREGIVER, SdohRisk.AT_RISK, "Lives alone; daughter Denise is 40 minutes away with her own family.",
         "I live alone, doctor. Denise is forty minutes away with a family of her own."),
        (SdohDomain.TRANSPORTATION, SdohRisk.AT_RISK, "Dependent on medical transport; the trip is exhausting.",
         "I followed the transport van over from the hospital... it wore me out something terrible."),
        (SdohDomain.FOOD, SdohRisk.AT_RISK, "Poor diabetic-diet adherence and intake at home.",
         "I let things slide at home. Cooking a proper diabetic..."),
    ],
    # Mrs. Monica Hilpert — SNF rehab
    "b504cdf2-e13b-979e-9c4a-95456823e3dd": [
        (SdohDomain.CAREGIVER, SdohRisk.CRITICAL, "Lives entirely alone; no one at home to help.",
         "Who's around you there? — Nobody, really. I'm on my own."),
        (SdohDomain.FOOD, SdohRisk.AT_RISK, "Tooth loss limits eating; likely under-nourished.",
         "With the teeth you've lost, tough food is hard work... eating less than you need."),
    ],
    # Mrs. Nola Kling — hospice
    "25fb1227-d194-b15e-e099-7cffcd6081ec": [
        (SdohDomain.CAREGIVER, SdohRisk.OK, "Daughter Karen present and closely involved.",
         "I eat like a bird and Karen fusses."),
        (SdohDomain.FOOD, SdohRisk.AT_RISK, "Poor appetite in end-stage illness.",
         "Appetite is small. I eat like a bird."),
    ],
    # Mr. Solomon Macejkovic — hospice
    "693a049b-0fd5-c1af-a6ab-e31c329f2891": [
        (SdohDomain.CAREGIVER, SdohRisk.OK, "Wife Margaret is primary caregiver (married 51 years); watch for caregiver strain — respite discussed.",
         "I am Margaret, his wife. Fifty-one years this spring."),
    ],
    # Ms. Traci Wiegand — SNF diabetes stabilization
    "5e93dd7e-1639-0886-8d0e-80ac11f2785c": [
        (SdohDomain.CAREGIVER, SdohRisk.AT_RISK, "Lives alone; sister passed; limited support network.",
         "I live alone... My sister passed two years ago."),
        (SdohDomain.FINANCIAL, SdohRisk.AT_RISK, "Income dropped after going part-time, then stopping work.",
         "Money got tight when I dropped to part-time, and tighter when I stopped."),
    ],
}


def derive_factors(record: dict) -> list[dict]:
    """Merge chart-finding + transcript factors into one per domain."""
    merged: dict[SdohDomain, dict] = {}

    def add(domain: SdohDomain, risk: SdohRisk, detail: str, source: str, evidence: str = "") -> None:
        existing = merged.get(domain)
        if existing is None:
            merged[domain] = {
                "domain": domain, "risk": risk, "detail": detail,
                "source": source, "evidence": evidence,
            }
            return
        # Same domain from both sources: keep higher risk, richer evidence, merge source.
        if _SEVERITY[risk] > _SEVERITY[existing["risk"]]:
            existing["risk"] = risk
            existing["detail"] = detail
        if evidence and not existing["evidence"]:
            existing["evidence"] = evidence
        if source not in existing["source"]:
            existing["source"] = "chart+transcript"

    for label in record.get("condition_labels", []):
        low = label.lower()
        for sub, domain, risk, detail in _CHART_MAP:
            if sub in low:
                add(domain, risk, detail, "chart")

    for domain, risk, detail, evidence in _TRANSCRIPT_OVERLAY.get(record["fhir_patient_id"], []):
        add(domain, risk, detail, "transcript", evidence)

    return sorted(merged.values(), key=lambda f: -_SEVERITY[f["risk"]])
