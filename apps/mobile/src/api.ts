import type {
  Clinician,
  CreateEncounterRequest,
  Encounter,
  EncounterDetail,
  HealthResponse,
  Patient,
} from "@abridge/shared";

// On a physical iPhone via Expo Go, "localhost" points at the phone, not your
// Mac. Set EXPO_PUBLIC_API_URL to your Mac's LAN IP, e.g.
//   EXPO_PUBLIC_API_URL=http://192.168.1.42:8000 pnpm --filter @abridge/mobile start
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API_URL}/health`).then(json<HealthResponse>),

  listClinicians: () => fetch(`${API_URL}/clinicians`).then(json<Clinician[]>),
  listPatients: () => fetch(`${API_URL}/patients`).then(json<Patient[]>),

  listEncounters: () => fetch(`${API_URL}/encounters`).then(json<Encounter[]>),
  getEncounter: (id: string) =>
    fetch(`${API_URL}/encounters/${id}`).then(json<EncounterDetail>),

  createEncounter: (body: CreateEncounterRequest) =>
    fetch(`${API_URL}/encounters`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Encounter>),

  // Uploads a recorded clip as multipart/form-data and kicks off transcription.
  uploadRecording: (
    encounterId: string,
    fileUri: string,
    durationSeconds?: number,
  ) => {
    const form = new FormData();
    form.append("file", {
      // React Native's FormData accepts this {uri,name,type} shape.
      uri: fileUri,
      name: "encounter.m4a",
      type: "audio/m4a",
    } as unknown as Blob);
    if (durationSeconds != null) {
      form.append("duration_seconds", String(durationSeconds));
    }
    return fetch(`${API_URL}/encounters/${encounterId}/recordings`, {
      method: "POST",
      body: form,
    }).then(json<EncounterDetail>);
  },
};
