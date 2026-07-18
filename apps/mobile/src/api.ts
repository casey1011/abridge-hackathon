import type { HealthResponse, Item, CreateItemRequest } from "@abridge/shared";

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
  listItems: () => fetch(`${API_URL}/items`).then(json<Item[]>),
  createItem: (body: CreateItemRequest) =>
    fetch(`${API_URL}/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Item>),
};
