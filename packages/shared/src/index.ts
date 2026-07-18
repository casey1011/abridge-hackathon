// Shared types used across web + mobile. Keep these in sync with the
// FastAPI Pydantic models in apps/api/app/schemas.py.

export interface HealthResponse {
  status: "ok";
  service: string;
}

export interface Item {
  id: string;
  title: string;
  createdAt: string; // ISO 8601
}

export interface CreateItemRequest {
  title: string;
}
