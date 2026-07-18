// Shared types used across web + mobile. Keep these in sync with the
// FastAPI DTOs in apps/api/app/schemas.py.

export interface HealthResponse {
  status: "ok";
  service: string;
}

export type EncounterSetting = "ED" | "INPATIENT" | "HOME";

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
}

export interface CreateEncounterRequest {
  patient_id: string;
  clinician_id: string;
  setting: EncounterSetting;
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
