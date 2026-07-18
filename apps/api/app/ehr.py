"""Generate an up-to-date discharge-planning / social-work note for the EHR.

The social worker triggers this from the dashboard; it drafts a concise note
from the current visit picture (chart, SDOH profile, agent findings, and the
accepted plan) that they review and file to the chart. Primary engine is a
Claude call; a deterministic template is the fallback so the button always
produces something.
"""
from sqlmodel import Session, select

from .config import settings
from .models import (
    AgentFinding,
    ChecklistItem,
    ChecklistItemStatus,
    Patient,
    SdohFactor,
    SdohRisk,
    Visit,
)


def _visit_facts(visit_id: str, session: Session) -> dict:
    visit = session.get(Visit, visit_id)
    patient = session.get(Patient, visit.patient_id)
    factors = session.exec(
        select(SdohFactor).where(SdohFactor.patient_id == visit.patient_id)
    ).all()
    findings = session.exec(
        select(AgentFinding).where(AgentFinding.visit_id == visit_id)
    ).all()
    items = session.exec(
        select(ChecklistItem).where(ChecklistItem.visit_id == visit_id)
    ).all()
    accepted = [
        i for i in items
        if i.status in (ChecklistItemStatus.ACCEPTED, ChecklistItemStatus.IN_PROGRESS,
                        ChecklistItemStatus.DONE)
    ]
    return {
        "patient": patient,
        "visit": visit,
        "factors": factors,
        "findings": findings,
        "accepted": accepted,
    }


def _template_note(f: dict) -> str:
    p, v = f["patient"], f["visit"]
    flagged = [x for x in f["factors"] if x.risk in (SdohRisk.AT_RISK, SdohRisk.CRITICAL)]
    lines = [
        f"DISCHARGE PLANNING / SOCIAL WORK NOTE — {p.display_name} (MRN {p.mrn})",
        f"Diagnosis: {v.primary_diagnosis}",
        "",
        "SDOH barriers identified:",
    ]
    lines += [f"  - {x.domain.value} ({x.risk.value}): {x.detail}" for x in flagged] or ["  - none flagged"]
    lines += ["", "Agent-surfaced findings:"]
    lines += [f"  - {x.title}" for x in f["findings"]] or ["  - none"]
    lines += ["", "Discharge plan (approved actions):"]
    lines += [f"  - [{i.owner_role or 'care team'}] {i.text}" for i in f["accepted"]] or ["  - none yet"]
    return "\n".join(lines)


def generate_note(visit_id: str, session: Session) -> tuple[str, str]:
    """Return (note_text, model_label)."""
    facts = _visit_facts(visit_id, session)
    if not settings.anthropic_api_key:
        return _template_note(facts), "template"
    try:
        import anthropic

        p, v = facts["patient"], facts["visit"]
        sdoh = "\n".join(
            f"- {x.domain.value} [{x.risk.value}]: {x.detail}" + (f" (\"{x.evidence}\")" if x.evidence else "")
            for x in facts["factors"]
        ) or "(none)"
        findings = "\n".join(
            f"- {x.type.value}: {x.title} — {x.detail}" for x in facts["findings"]
        ) or "(none)"
        plan = "\n".join(
            f"- [{i.owner_role or 'care team'}] {i.text}" for i in facts["accepted"]
        ) or "(none approved yet)"
        prompt = (
            f"Patient: {p.display_name} (MRN {p.mrn}). Diagnosis: {v.primary_diagnosis}.\n"
            f"Chart: {p.chart_summary}\n\n"
            f"SDOH profile:\n{sdoh}\n\n"
            f"Reasoning-agent findings:\n{findings}\n\n"
            f"Approved discharge-plan actions:\n{plan}\n"
        )
        system = (
            "You are a hospital social worker writing a concise, professional "
            "discharge-planning progress note for the EHR chart. Write in plain "
            "clinical prose with short labelled sections: Summary, Social "
            "determinants & barriers, Interventions in progress, Discharge "
            "readiness / outstanding needs. Be specific and factual — only use "
            "what is provided. Keep it under ~220 words. No preamble, no markdown "
            "headers with #, just SECTION LABELS in caps followed by the text."
        )
        resp = anthropic.Anthropic(api_key=settings.anthropic_api_key).messages.create(
            model=settings.anthropic_model,
            max_tokens=900,
            thinking={"type": "disabled"},
            output_config={"effort": "low"},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text:
            return text, settings.anthropic_model
    except Exception as exc:  # noqa: BLE001
        print(f"[ehr] note generation failed, using template: {exc}")
    return _template_note(facts), "template"
