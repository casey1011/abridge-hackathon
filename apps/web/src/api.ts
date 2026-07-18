import type {
  Encounter,
  EncounterDetail,
  HealthResponse,
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
};
