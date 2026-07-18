"""Abridge hackathon API.

Run: uv run uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .schemas import CreateItemRequest, HealthResponse, Item

app = FastAPI(title="Abridge API")

# Open CORS for hackathon convenience (web dev server + Expo). Tighten later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store — swap for a real DB when you need persistence.
_items: list[Item] = []


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/items", response_model=list[Item])
def list_items() -> list[Item]:
    return _items


@app.post("/items", response_model=Item)
def create_item(body: CreateItemRequest) -> Item:
    item = Item(
        id=str(uuid4()),
        title=body.title,
        createdAt=datetime.now(timezone.utc).isoformat(),
    )
    _items.append(item)
    return item
