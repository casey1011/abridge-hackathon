import type {
  ChecklistItem,
  ChecklistItemStatus,
  EhrNote,
  Encounter,
  EncounterDetail,
  HealthResponse,
  Visit,
  VisitDetail,
} from "@abridge/shared";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API_URL}/health`).then(json<HealthResponse>),

  listEncounters: () => fetch(`${API_URL}/encounters`).then(json<Encounter[]>),
  getEncounter: (id: string) =>
    fetch(`${API_URL}/encounters/${id}`).then(json<EncounterDetail>),

  listVisits: () => fetch(`${API_URL}/visits`).then(json<Visit[]>),
  getVisit: (id: string) =>
    fetch(`${API_URL}/visits/${id}`).then(json<VisitDetail>),

  runReasoning: (visitId: string) =>
    fetch(`${API_URL}/visits/${visitId}/reasoning/run`, { method: "POST" }).then(
      json<VisitDetail>,
    ),

  updateChecklistItem: (itemId: string, status: ChecklistItemStatus) =>
    fetch(`${API_URL}/checklist-items/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }).then(json<ChecklistItem>),

  // Attach a provider↔provider rounds transcript (no body = canned fallback).
  addCareConference: (visitId: string) =>
    fetch(`${API_URL}/visits/${visitId}/care-conference`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }).then(json<VisitDetail>),

  generateEhrNote: (visitId: string) =>
    fetch(`${API_URL}/visits/${visitId}/ehr-note`, { method: "POST" }).then(
      json<VisitDetail>,
    ),

  fileEhrNote: (noteId: string) =>
    fetch(`${API_URL}/ehr-notes/${noteId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "filed" }),
    }).then(json<EhrNote>),
};
