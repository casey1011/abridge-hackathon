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
from datetime import datetime, timezone

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


def _visit_transcript_text(visit_id: str, session: Session, since=None) -> str:
    """A visit's transcripts, each labelled by capture type so the agent can
    tell a bedside encounter from rounds. When `since` is given, only captures
    created after that stamp are included (incremental re-runs)."""
    encounters = session.exec(
        select(Encounter).where(Encounter.visit_id == visit_id).order_by(Encounter.started_at)
    ).all()
    parts: list[str] = []
    for e in encounters:
        if since is not None and e.created_at <= since:
            continue
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
    visit = session.get(Visit, visit_id)
    now = datetime.now(timezone.utc)
    # The "stamp": only process captures newer than the last run, so a re-run
    # surfaces what's NEW instead of re-deriving (and paraphrasing) findings
    # from transcripts already processed.
    since = visit.reasoned_at if visit is not None else None
    text = _visit_transcript_text(visit_id, session, since=since)

    # The whole current plan (any status) — the agent reconciles against this
    # and must NOT re-propose it; also the dedup safety net.
    existing = session.exec(
        select(ChecklistItem).where(ChecklistItem.visit_id == visit_id)
    ).all()

    def _norm(t: str) -> str:
        return " ".join(t.lower().split())

    existing_lines = [f"- {i.text} [{i.status.value}]" for i in existing]
    seen = {_norm(i.text) for i in existing}

    def _stamp() -> None:
        if visit is not None:
            visit.reasoned_at = now
            session.add(visit)
            session.commit()

    # Re-run with no new capture since the last stamp → nothing to do.
    if since is not None and not text.strip():
        _stamp()
        return []

    findings: list[AgentFinding] = []

    def emit(ftype: FindingType, title: str, detail: str, evidence: str,
             phase: ChecklistPhase, item_text: str, owner: str,
             suggested_ask: str = "", confidence: float = 0.7,
             source_engine: str = "rules") -> None:
        # Skip anything already on the plan / already decided (dedup safety net).
        if _norm(item_text) in seen:
            return
        seen.add(_norm(item_text))
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

    factors = (
        session.exec(select(SdohFactor).where(SdohFactor.patient_id == visit.patient_id)).all()
        if visit is not None
        else []
    )
    chart = session.get(Patient, visit.patient_id).chart_summary if visit is not None else ""

    # Primary engine: Claude reasons over transcript + chart + SDOH profile.
    # `None` = the call failed (fall back to rules); `[]` = ran, nothing new.
    llm = _llm_findings(text, chart, factors, existing_lines) if use_llm else None
    if llm is not None:
        for f in llm:
            emit(
                f["type"], f["title"], f["detail"], f["evidence"],
                ChecklistPhase.DAY_OF_DISCHARGE, f["action"], f["owner"],
                suggested_ask=f.get("suggested_ask", ""),
                confidence=f.get("confidence", 0.75),
                source_engine="llm",
            )
        session.commit()
        _stamp()
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
    _stamp()
    return findings


# --- Claude reasoning call --------------------------------------------------

_VALID_TYPES = {"implicature", "sdoh"}
_VALID_OWNERS = {"social_work", "pharmacist", "nurse", "care_management"}

_SYSTEM = """You are a discharge-plan RECONCILIATION agent in an ambient \
clinical-documentation product. You are given, in order:
1) PRIOR CHART / SDOH CONTEXT pulled from the medical record — this may be \
OUTDATED.
2) One or more conversation transcripts in CHRONOLOGICAL order (oldest first, \
newest last), each labelled BEDSIDE or CARE CONFERENCE (multidisciplinary \
rounds). The newest transcript, and any rounds, reflect the CURRENT truth.

Your job is to reconcile the discharge plan with what was ACTUALLY said, \
prioritizing the most recent information.

CORE RULES — reconciliation first:
- RECENCY WINS. If a newer statement contradicts the chart/SDOH context or an \
earlier transcript, the newer statement is current. NEVER assert a fact the \
latest conversation contradicts.
- ONE finding per contradicted fact. When the conversation resolves or \
contradicts a chart fact, emit EXACTLY ONE reconciliation update and NOTHING \
ELSE about that topic. Do NOT also emit a barrier that re-raises the now-false \
concern, and do NOT quote the outdated statement as if it were current. \
Example: chart says "lives alone / socially isolated" but the patient now says \
her son lives with her → emit ONE finding "Update caregiver status — patient \
now reports son co-resides (chart said lives alone)"; do NOT also emit \
"verify caregiver support given prior isolation" and do NOT quote "I live \
alone / my sister passed" — that fact is superseded.
- When you cite `evidence`, quote the statement that makes your finding TRUE \
right now — for a reconciliation, quote the NEW statement, never the old one.
- RECONCILE, don't repeat. Prefer findings that either (a) catch an unspoken \
or contradicted barrier, or (b) capture a concrete decision/detail the plan \
must reflect: who is picking the patient up and WHEN, DME ordered, home-health \
or follow-up arranged, a medication change, a resolved barrier.
- Do NOT surface a barrier that the conversation RESOLVES or contradicts.
- Every finding MUST quote the transcript in `evidence`, preferring the most \
recent transcript. No speculation, no padding.
- Be concise: titles under ~8 words, detail one short sentence, AT MOST 6 \
findings ranked by discharge impact. Skip generic checklist steps.

You surface only TWO kinds of finding:
- `implicature` — an UNSPOKEN or CONTRADICTED barrier: something the \
conversation implied but never resolved, or a fact that contradicts the chart \
or plan (e.g. agreed to daily weights but has no scale; chart says "lives \
alone" but the patient now reports living with family).
- `sdoh` — a PLAN UPDATE the discharge plan must reflect: a reconciled fact or \
a concrete decision/arrangement stated in the conversation (who is picking the \
patient up and WHEN, a caregiver change, home-health or follow-up arranged, a \
resolved barrier).
Do NOT emit medication-reconciliation findings. If unsure which kind, use \
`implicature`."""

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


def _llm_findings(
    text: str, chart: str, factors: list[SdohFactor], existing_plan: list[str] | None = None
) -> list[dict] | None:
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
        plan_lines = "\n".join(existing_plan) if existing_plan else "(nothing yet)"
        prompt = (
            "=== PRIOR CHART / SDOH CONTEXT (from the record — MAY BE OUTDATED; "
            "reconcile against the conversation, which is more current) ===\n"
            f"Chart: {chart or '(none)'}\n"
            f"SDOH on file:\n{sdoh_lines}\n\n"
            "=== ALREADY ON THE DISCHARGE PLAN / ALREADY DECIDED (do NOT "
            "re-propose these; surface only NEW or CHANGED items) ===\n"
            f"{plan_lines}\n\n"
            "=== CONVERSATION TRANSCRIPTS (chronological, newest last — the "
            "current source of truth) ===\n"
            f"{text}\n\n"
            "Reconcile the discharge plan with the conversation. Return ONLY new "
            "or changed findings (an empty list is fine if nothing changed) as "
            "JSON."
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
    # Empty list is a valid result ("nothing new") — only failures return None.
    return out
