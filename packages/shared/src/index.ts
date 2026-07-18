// Shared types used across web + mobile. Keep these in sync with the
// FastAPI DTOs in apps/api/app/schemas.py.

export interface HealthResponse {
  status: "ok";
  service: string;
}

export type EncounterSetting = "ED" | "INPATIENT" | "HOME" | "CARE_CONFERENCE";

export type EncounterStatus =
  | "recording"
  | "uploaded"
  | "transcribing"
  | "ready"
  | "failed";

export interface Clinician {
  id: string;
  name: string;
  role: string;
}

export interface Patient {
  id: string;
  mrn: string;
  display_name: string;
  gender?: string | null;
  chart_summary?: string;
}

export interface CreateEncounterRequest {
  patient_id: string;
  clinician_id: string;
  setting: EncounterSetting;
  visit_id?: string | null;
}

export interface Transcript {
  text: string;
  status: EncounterStatus;
  model: string;
  language: string | null;
}

export interface Encounter {
  id: string;
  setting: EncounterSetting;
  status: EncounterStatus;
  started_at: string; // ISO 8601
  patient: Patient;
  clinician: Clinician;
}

export interface EncounterDetail extends Encounter {
  transcript: Transcript | null;
}

// --- discharge / coordination ------------------------------------------------

export type VisitStatus = "active" | "discharge_planning" | "discharged";

export type MeetingStatus = "scheduled" | "in_progress" | "completed";

export type ChecklistPhase =
  | "initial_assessment"
  | "daily"
  | "pre_meeting"
  | "meeting"
  | "day_of_discharge";

export type ChecklistItemStatus =
  | "proposed"
  | "accepted"
  | "in_progress"
  | "done"
  | "dismissed";

export type ChecklistItemSource = "template" | "agent" | "manual";

export type FindingType = "implicature" | "med_reconciliation" | "sdoh";

export interface Meeting {
  id: string;
  status: MeetingStatus;
  scheduled_at: string; // ISO 8601
  participants: string;
  notes: string;
}

export interface AgentFinding {
  id: string;
  type: FindingType;
  title: string;
  detail: string;
  evidence: string;
  suggested_ask: string;
  confidence: number;
  source_engine: string; // "llm" | "rules"
}

export interface ChecklistItem {
  id: string;
  phase: ChecklistPhase;
  text: string;
  status: ChecklistItemStatus;
  source: ChecklistItemSource;
  owner_role: string;
  finding_id: string | null;
  completed_at: string | null;
}

export interface Visit {
  id: string;
  status: VisitStatus;
  primary_diagnosis: string;
  admitted_at: string; // ISO 8601
  patient: Patient;
  encounter_count: number;
  open_item_count: number;
  proposed_count: number;
}

export type SdohDomain =
  | "caregiver"
  | "transportation"
  | "food"
  | "housing"
  | "financial"
  | "social_isolation"
  | "safety"
  | "education";

export type SdohRisk = "ok" | "at_risk" | "critical" | "unknown";

export interface SdohFactor {
  domain: SdohDomain;
  risk: SdohRisk;
  detail: string;
  source: string;
  evidence: string;
}

export type EhrNoteStatus = "draft" | "filed";

export interface EhrNote {
  id: string;
  status: EhrNoteStatus;
  text: string;
  model: string;
  created_at: string;
  filed_at: string | null;
}

export interface VisitDetail extends Visit {
  encounters: Encounter[];
  meeting: Meeting | null;
  findings: AgentFinding[];
  checklist: ChecklistItem[];
  sdoh: SdohFactor[];
  ehr_note: EhrNote | null;
}

export interface CreateVisitRequest {
  patient_id: string;
  primary_diagnosis?: string;
}

export interface UpdateChecklistItemRequest {
  status: ChecklistItemStatus;
}
