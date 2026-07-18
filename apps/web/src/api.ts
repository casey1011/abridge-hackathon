import type { HealthResponse, Item, CreateItemRequest } from "@abridge/shared";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${API_URL}/health`).then(json<HealthResponse>),
  listItems: () => fetch(`${API_URL}/items`).then(json<Item[]>),
  createItem: (body: CreateItemRequest) =>
    fetch(`${API_URL}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Item>),
};
