# ReadMark

Save links, track reading progress, and sync across devices.

This is a monorepo containing both halves of the ReadMark app:

```
readmark/
├── extension/   # Browser extension (Chrome MV3) — the client
└── backend/     # FastAPI server — auth + item sync API
```

## extension/

A Manifest V3 browser extension.

| File | Purpose |
|------|---------|
| `manifest.json` | Extension manifest |
| `background.js` | Service worker (API proxy, alarms) |
| `content.js` | Content script injected into pages |
| `popup.html` / `popup.js` | Popup UI |
| `api.js` | API client — set `API_BASE_URL` to your server |
| `icons/` | Extension icons |

**Load it:** open `chrome://extensions`, enable Developer mode, click **Load unpacked**, select `extension/`.

## backend/

A FastAPI service (run with `uvicorn main:app`) providing:

- `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- `GET/POST/PATCH/DELETE /api/items`, plus scroll/sync/lookup endpoints

**Setup:**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in real secrets
uvicorn main:app --host 0.0.0.0 --port 8000
```

Point `extension/api.js` (`API_BASE_URL`) at wherever you host the backend.
Secrets (`.env`) and the database (`*.db`) are gitignored and never committed.
