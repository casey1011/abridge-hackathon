# Abridge Hackathon

Monorepo with a web app, an iPhone app, and a shared backend.

## Stack

| Part      | Tech                        | Location          |
| --------- | --------------------------- | ----------------- |
| Web       | Vite + React + TypeScript   | `apps/web`        |
| Mobile    | Expo (React Native, TS)     | `apps/mobile`     |
| Backend   | Python + FastAPI (uv)       | `apps/api`        |
| Shared    | TypeScript types            | `packages/shared` |

JS/TS is a **pnpm workspace**. `packages/shared` is imported by both web and
mobile as `@abridge/shared` so request/response types stay in sync. The Python
API mirrors those types in `apps/api/app/schemas.py`.

## Prerequisites

- Node 22+ and pnpm 10+
- [uv](https://docs.astral.sh/uv/) (manages Python 3.12 for the API)
- Expo Go app on your iPhone (for the mobile app)

## First-time setup

```bash
pnpm install                 # installs web + mobile + shared
cd apps/api && uv sync       # installs the API's Python deps
```

## Run everything (three terminals)

```bash
# 1. Backend  → http://localhost:8000  (docs at /docs)
pnpm api

# 2. Web      → http://localhost:5173
pnpm web

# 3. Mobile   → scan the QR code with Expo Go
pnpm mobile
```

### Mobile → API on a physical iPhone

`localhost` on your phone points at the phone, not your Mac. Start the mobile
app with your Mac's LAN IP so it can reach the API:

```bash
EXPO_PUBLIC_API_URL=http://<your-mac-ip>:8000 pnpm mobile
```

## Layout

```
abridge-hackathon/
├── apps/
│   ├── web/      # Vite + React
│   ├── mobile/   # Expo
│   └── api/      # FastAPI (uv, not part of the pnpm workspace)
└── packages/
    └── shared/   # @abridge/shared — TS types shared by web + mobile
```

## API endpoints (starter)

- `GET  /health` → `{ status, service }`
- `GET  /items`  → `Item[]`
- `POST /items`  → create an item `{ title }`

The store is in-memory — swap it for a real database when you need persistence.
