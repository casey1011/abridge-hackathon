"""The IDEAL Discharge Planning checklist template (AHRQ).

Seeds a fresh visit's checklist, phased exactly as the AHRQ tool: initial
nursing assessment, daily, prior-to-meeting, during-meeting, day-of-discharge.
These are `template` items and start `accepted` (they're the standard plan);
the reasoning agent adds `proposed` items on top that the meeting reviews.
"""
from .models import (
    ChecklistItem,
    ChecklistItemSource,
    ChecklistItemStatus,
    ChecklistPhase,
)

# (phase, text, owner_role)
_TEMPLATE: list[tuple[ChecklistPhase, str, str]] = [
    (ChecklistPhase.INITIAL_ASSESSMENT, "Identify the caregiver at home and backups", "nurse"),
    (ChecklistPhase.INITIAL_ASSESSMENT, "Tell patient and family about the white board", "nurse"),
    (ChecklistPhase.INITIAL_ASSESSMENT, "Elicit patient and family goals for the hospital stay", "nurse"),
    (ChecklistPhase.INITIAL_ASSESSMENT, "Inform patient and family about steps to discharge", "nurse"),
    (ChecklistPhase.DAILY, "Educate patient and family about condition; use teach-back", "nurse"),
    (ChecklistPhase.DAILY, "Discuss progress toward patient, family, and clinician goals", "nurse"),
    (ChecklistPhase.DAILY, "Explain medications to patient and family", "nurse"),
    (ChecklistPhase.PRE_MEETING, "Distribute 'Be Prepared to Go Home' checklist and booklet", "care_management"),
    (ChecklistPhase.PRE_MEETING, "Schedule the discharge planning meeting", "care_management"),
    (ChecklistPhase.MEETING, "Discuss patient questions", "social_work"),
    (ChecklistPhase.MEETING, "Discuss family questions", "social_work"),
    (ChecklistPhase.MEETING, "Review discharge instructions as needed", "nurse"),
    (ChecklistPhase.MEETING, "Use teach-back", "nurse"),
    (ChecklistPhase.MEETING, "Offer to schedule follow-up appointments with providers", "care_management"),
    (ChecklistPhase.DAY_OF_DISCHARGE, "Reconcile medication list", "pharmacist"),
    (ChecklistPhase.DAY_OF_DISCHARGE, "Review medication list with patient and family; use teach-back", "pharmacist"),
    (ChecklistPhase.DAY_OF_DISCHARGE, "Schedule follow-up appointments", "care_management"),
    (ChecklistPhase.DAY_OF_DISCHARGE, "Arrange any home care needed", "social_work"),
    (ChecklistPhase.DAY_OF_DISCHARGE, "Give written appointments to the patient and family", "care_management"),
    (ChecklistPhase.DAY_OF_DISCHARGE, "Give contact info for the follow-up person after discharge", "nurse"),
]


def template_items(visit_id: str) -> list[ChecklistItem]:
    """Build the standard IDEAL checklist for a new visit."""
    return [
        ChecklistItem(
            visit_id=visit_id,
            phase=phase,
            text=text,
            owner_role=owner,
            source=ChecklistItemSource.TEMPLATE,
            status=ChecklistItemStatus.ACCEPTED,
            sort_order=i,
        )
        for i, (phase, text, owner) in enumerate(_TEMPLATE)
    ]
