"""Pydantic models. Keep in sync with packages/shared/src/index.ts."""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "abridge-api"


class Item(BaseModel):
    id: str
    title: str
    createdAt: str  # ISO 8601


class CreateItemRequest(BaseModel):
    title: str


class TranscriptResponse(BaseModel):
    text: str
