"""Reasoning agent.

Reads a visit's transcripts + chart + structured SDOH profile and surfaces
findings across the three lenses in the diagram: implicature catch (unspoken
barriers), med reconciliation (formulation changes), and SDOH lookup. The
primary engine is a Claude call (`_llm_findings`); a deterministic
SDOH-factor + keyword pass (`_rules_findings`) is the fallback so the loop is
never dead — if the API key is missing or the call fails, the demo still runs.

Each finding also yields a `proposed` checklist item that the social-work /
care-coordination rounds (the human-review gate) accept or dismiss.
"""
import json

from sqlmodel import Session, select

from .config import settings
from .models import (
    AgentFinding,
    ChecklistItem,
    ChecklistItemSource,
    ChecklistItemStatus,
    ChecklistPhase,
    Encounter,
    EncounterSetting,
    FindingType,
    Patient,
    SdohDomain,
    SdohFactor,
    SdohRisk,
    Transcript,
    Visit,
)

# Structured SDOH factors -> a grounded proposed action. domain -> (finding
# type, finding title, item text, owner). Only at-risk / critical factors fire.
_SDOH_ACTION: dict[SdohDomain, tuple[FindingType, str, str, str]] = {
    SdohDomain.CAREGIVER: (
        FindingType.IMPLICATURE,
        "Caregiver support gap at home",
        "Confirm home caregiver and backup; arrange home health if needed",
        "social_work",
    ),
    SdohDomain.TRANSPORTATION: (
        FindingType.SDOH,
        "Transportation barrier to follow-up",
        "Arrange transportation for follow-up appointments",
        "social_work",
    ),
    SdohDomain.FOOD: (
        FindingType.SDOH,
        "Nutrition / food access risk",
        "Refer to dietitian; arrange meal support (e.g. Meals on Wheels)",
        "social_work",
    ),
    SdohDomain.FINANCIAL: (
        FindingType.SDOH,
        "Financial / medication affordability risk",
        "Screen medication affordability; connect to financial assistance",
        "social_work",
    ),
    SdohDomain.SAFETY: (
        FindingType.IMPLICATURE,
        "Safety concern needs social-work review",
        "Social work safety assessment before discharge",
        "social_work",
    ),
    SdohDomain.SOCIAL_ISOLATION: (
        FindingType.IMPLICATURE,
        "Social isolation risk after discharge",
        "Arrange community / social support to reduce isolation",
        "social_work",
    ),
}

# Each rule: if any trigger appears in the visit's transcripts, emit a finding
# plus a proposed checklist item. Shaped so a Claude call can return the same.
_RULES: list[dict] = [
    {
        "type": FindingType.IMPLICATURE,
        "triggers": ["my daughter", "ride", "can't drive", "cannot drive", "no one", "alone", "get here", "drive me"],
        "title": "Possible transportation barrier to follow-up",
        "detail": "Patient hinted they may lack a reliable ride to appointments.",
        "phase": ChecklistPhase.DAY_OF_DISCHARGE,
        "item": "Confirm transportation to follow-up appointments; arrange a ride if needed",
        "owner": "social_work",
    },
    {
        "type": FindingType.MED_RECONCILIATION,
        "triggers": ["switched", "new dose", "instead of", "stopped taking", "formulation", "generic", "brand"],
        "title": "Medication change needs reconciliation",
        "detail": "A medication switch or dose change was mentioned and should be reconciled against the discharge list.",
        "phase": ChecklistPhase.DAY_OF_DISCHARGE,
        "item": "Reconcile the mentioned medication change with the discharge med list",
        "owner": "pharmacist",
    },
    {
        "type": FindingType.SDOH,
        "triggers": ["afford", "cost", "copay", "insurance", "pharmacy", "expensive", "coupon"],
        "title": "Possible medication affordability / access barrier",
        "detail": "Patient may struggle to afford or access prescribed medications.",
        "phase": ChecklistPhase.DAY_OF_DISCHARGE,
        "item": "Check medication affordability; provide coupons or assistance-program info",
        "owner": "social_work",
    },
]


def _find_evidence(text: str, triggers: list[str]) -> str | None:
    """Return a short quote around the first matching trigger, else None."""
    lowered = text.lower()
    for t in triggers:
        idx = lowered.find(t)
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(t) + 40)
            return "…" + text[start:end].strip() + "…"
    return None


def _visit_transcript_text(visit_id: str, session: Session) -> str:
    """All of a visit's transcripts, each labelled by capture type so the agent
    can tell a bedside encounter from a multidisciplinary rounds discussion."""
    encounters = session.exec(
        select(Encounter).where(Encounter.visit_id == visit_id).order_by(Encounter.started_at)
    ).all()
    parts: list[str] = []
    for e in encounters:
        tr = session.exec(
            select(Transcript).where(Transcript.encounter_id == e.id)
        ).first()
        if tr is None or not (tr.text or "").strip():
            continue
        label = (
            "CARE CONFERENCE — MULTIDISCIPLINARY ROUNDS (provider↔provider, about the patient)"
            if e.setting == EncounterSetting.CARE_CONFERENCE
            else f"BEDSIDE ENCOUNTER — {e.setting.value} (provider↔patient)"
        )
        parts.append(f"===== {label} =====\n{tr.text}")
    return "\n\n".join(parts)


def run_reasoning(visit_id: str, session: Session, use_llm: bool = True) -> list[AgentFinding]:
    """Analyze a visit's transcripts; persist findings + proposed items.

    Re-runnable: clears prior *agent* output for the visit first so re-running
    from the UI doesn't pile up duplicates. Template/manual items are untouched.

    `use_llm=True` (the "Run reasoning agent" button) makes a live Claude call;
    `use_llm=False` (ingest/seed time) uses the fast deterministic pass so the
    app boots instantly and free, then the live call upgrades it on demand.
    """
    text = _visit_transcript_text(visit_id, session)

    for old_item in session.exec(
        select(ChecklistItem).where(
            (ChecklistItem.visit_id == visit_id)
            & (ChecklistItem.source == ChecklistItemSource.AGENT)
        )
    ).all():
        session.delete(old_item)
    for old_finding in session.exec(
        select(AgentFinding).where(AgentFinding.visit_id == visit_id)
    ).all():
        session.delete(old_finding)
    session.commit()

    findings: list[AgentFinding] = []

    def emit(ftype: FindingType, title: str, detail: str, evidence: str,
             phase: ChecklistPhase, item_text: str, owner: str,
             suggested_ask: str = "", confidence: float = 0.7,
             source_engine: str = "rules") -> None:
        finding = AgentFinding(
            visit_id=visit_id, type=ftype, title=title,
            detail=detail, evidence=evidence, suggested_ask=suggested_ask,
            confidence=confidence, source_engine=source_engine,
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)
        session.add(
            ChecklistItem(
                visit_id=visit_id, phase=phase, text=item_text, owner_role=owner,
                source=ChecklistItemSource.AGENT, status=ChecklistItemStatus.PROPOSED,
                finding_id=finding.id, sort_order=100,
            )
        )
        findings.append(finding)

    visit = session.get(Visit, visit_id)
    factors = (
        session.exec(select(SdohFactor).where(SdohFactor.patient_id == visit.patient_id)).all()
        if visit is not None
        else []
    )
    chart = session.get(Patient, visit.patient_id).chart_summary if visit is not None else ""

    # Primary engine: Claude reasons over transcript + chart + SDOH profile.
    llm = _llm_findings(text, chart, factors) if use_llm else None
    if llm:
        for f in llm:
            emit(
                f["type"], f["title"], f["detail"], f["evidence"],
                ChecklistPhase.DAY_OF_DISCHARGE, f["action"], f["owner"],
                suggested_ask=f.get("suggested_ask", ""),
                confidence=f.get("confidence", 0.75),
                source_engine="llm",
            )
        session.commit()
        return findings

    # Fallback: deterministic SDOH-factor + keyword pass (never a dead loop).
    covered_types: set[FindingType] = set()
    for f in factors:
        if f.risk not in (SdohRisk.AT_RISK, SdohRisk.CRITICAL):
            continue
        action = _SDOH_ACTION.get(f.domain)
        if action is None:
            continue
        ftype, title, item_text, owner = action
        emit(ftype, title, f.detail, f.evidence or f.detail,
             ChecklistPhase.DAY_OF_DISCHARGE, item_text, owner)
        covered_types.add(ftype)

    for rule in _RULES:
        if rule["type"] in covered_types and rule["type"] is not FindingType.MED_RECONCILIATION:
            continue
        evidence = _find_evidence(text, rule["triggers"])
        if evidence is None:
            continue
        emit(rule["type"], rule["title"], rule["detail"], evidence,
             rule["phase"], rule["item"], rule["owner"])

    session.commit()
    return findings


# --- Claude reasoning call --------------------------------------------------

_VALID_TYPES = {"implicature", "med_reconciliation", "sdoh"}
_VALID_OWNERS = {"social_work", "pharmacist", "nurse", "care_management"}

_SYSTEM = """You are a discharge-planning reasoning agent embedded in an \
ambient clinical-documentation product. You read the transcript(s) of real \
conversations (bedside and/or multidisciplinary rounds), the patient's chart \
summary, and a structured social-determinants profile, and you update the \
discharge plan with the things a busy care team would otherwise miss or lose.

Capture across these lenses:
- implicature: an UNSPOKEN barrier the conversation glossed over — the patient \
agreed to something, then let slip a fact that quietly makes it impossible \
(e.g. agreed to daily weights, then mentioned they have no scale and their \
caregiver lives far away, and the conversation moved on).
- med_reconciliation: a medication switch, dose, or formulation change that \
must be reconciled against the discharge list.
- sdoh: a social barrier OR a concrete logistical arrangement for discharge — \
transportation and PICKUP arrangements (who is taking the patient home and \
WHEN, e.g. "daughter will pick him up at 3 pm"), caregiver availability, DME \
ordered, home-health arranged, follow-up appointments scheduled, food access, \
medication affordability. Capture these EVEN WHEN THEY RESOLVE rather than \
raise a concern — the plan must reflect what was actually said and decided. \
For a stated arrangement, write a specific, checkable action (e.g. "Confirm \
daughter pickup at 3:00 pm on discharge day").

The input may contain more than one transcript, each labelled by type. Treat \
CARE CONFERENCE (rounds) content as authoritative and most recent: reflect the \
team's and family's decisions and concrete details, with the right owner.

Rules:
- Be concise and high-signal. Titles under ~8 words; detail one short sentence.
- Return AT MOST 6 findings, ranked by discharge impact.
- Do NOT restate generic discharge steps a standard checklist already covers \
(teach-back, giving written appointments, "schedule follow-up") unless the \
conversation added a specific, patient-specific detail (a name, a time, a \
number, a dose).
- Every finding MUST quote the transcript in `evidence`. No padding, no \
speculation."""

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "type": {"type": "string", "enum": sorted(_VALID_TYPES)},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "evidence": {"type": "string"},
                    "suggested_ask": {"type": "string"},
                    "action": {"type": "string"},
                    "owner": {"type": "string", "enum": sorted(_VALID_OWNERS)},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "type", "title", "detail", "evidence",
                    "suggested_ask", "action", "owner", "confidence",
                ],
            },
        }
    },
    "required": ["findings"],
}


def _llm_findings(text: str, chart: str, factors: list[SdohFactor]) -> list[dict] | None:
    """Ask Claude for grounded discharge findings. Returns None on any failure
    so the caller can fall back to the deterministic engine."""
    if not settings.anthropic_api_key or not text.strip():
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        sdoh_lines = "\n".join(
            f"- {f.domain.value}: {f.risk.value} — {f.detail}" for f in factors
        ) or "(none on file)"
        prompt = (
            f"CHART SUMMARY:\n{chart or '(none)'}\n\n"
            f"STRUCTURED SDOH PROFILE:\n{sdoh_lines}\n\n"
            f"AMBIENT TRANSCRIPT:\n{text}\n\n"
            "Return the discharge-planning findings as JSON."
        )
        resp = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}, "effort": "medium"},
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        payload = "".join(b.text for b in resp.content if b.type == "text")
        data = json.loads(payload)
    except Exception as exc:  # noqa: BLE001 — never let the demo die on the agent
        print(f"[reasoning] LLM call failed, using rules fallback: {exc}")
        return None

    out: list[dict] = []
    for f in data.get("findings", []):
        ftype = f.get("type")
        owner = f.get("owner")
        if ftype not in _VALID_TYPES or not f.get("title") or not f.get("action"):
            continue
        out.append(
            {
                "type": FindingType(ftype),
                "title": f["title"],
                "detail": f.get("detail", ""),
                "evidence": f.get("evidence", ""),
                "suggested_ask": f.get("suggested_ask", ""),
                "action": f["action"],
                "owner": owner if owner in _VALID_OWNERS else "social_work",
                "confidence": float(f.get("confidence", 0.75)),
            }
        )
    return out or None
