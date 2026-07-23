# ReadMark

**Save links, track reading progress, and never lose your place again.**

ReadMark is a full-stack reading list manager with a Python API, web dashboard, and Chrome extension that syncs your reading progress across devices.

## Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Chrome      │────▶│  FastAPI Server  │◀────│     Web      │
│  Extension    │     │  (Python + SQLite)│     │  Dashboard   │
└──────────────┘     └─────────────────┘     └──────────────┘
       │                      │                       │
       └──────────── REST API (JWT Auth) ─────────────┘
```

## Features

- **Save links** with one click from any browser tab
- **Track reading progress** — scroll position auto-saves and restores
- **Smart URL matching** — same article recognized regardless of tracking params or referral source
- **Status management** — Unread → Reading → Done
- **Categories** — Article, Essay, Tutorial, Research, Video, Podcast
- **Search & filter** across your entire library
- **Dark / Light mode**
- **Cross-device sync** via REST API
- **Email + Google OAuth** authentication

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy (async), SQLite
- **Auth:** JWT tokens, bcrypt password hashing, Google OAuth
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Extension:** Chrome Manifest V3
- **Deployment:** Docker + Docker Compose

---

## Quick Start

### 1. Clone and configure

```bash
cd readmark-api
cp .env.example .env
```

Edit `.env` and set a strong `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Run with Docker (recommended)

```bash
docker compose up -d
```

The server starts at `http://localhost:8000`.

### 3. Run without Docker

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

### 4. Open the dashboard

Go to `http://localhost:8000` in your browser. Create an account and start saving links.

### 5. Install the Chrome extension

1. Update the extension's `API_URL` in `content.js` and `popup.js` to point to your server
2. Go to `chrome://extensions`
3. Enable Developer mode
4. Click "Load unpacked" and select the extension folder

---

## API Endpoints

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Create account (email + password) |
| POST | `/api/auth/login` | Sign in |
| POST | `/api/auth/google` | Google OAuth sign in |
| GET | `/api/auth/me` | Get current user profile |

### Items

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/items` | List items (with filters, search, sort) |
| POST | `/api/items` | Save a new item |
| GET | `/api/items/{id}` | Get single item |
| PATCH | `/api/items/{id}` | Update item |
| DELETE | `/api/items/{id}` | Delete item |
| POST | `/api/items/scroll` | Update scroll position by URL |
| GET | `/api/items/lookup/url?url=...` | Look up item by URL |
| POST | `/api/items/sync` | Bulk sync (extension ↔ server) |

### Query Parameters for GET `/api/items`

- `status` — Filter by status: `unread`, `reading`, `done`
- `category` — Filter by category
- `search` — Full-text search across title, URL, notes
- `sort` — Sort order: `newest`, `oldest`, `updated`, `alpha`
- `limit` — Items per page (default: 50, max: 200)
- `offset` — Pagination offset

---

## Deployment on DigitalOcean

```bash
# SSH into your droplet
ssh root@your-droplet-ip

# Clone or upload the readmark-api folder
# Then:
cd readmark-api
cp .env.example .env
# Edit .env with your SECRET_KEY and domain

docker compose up -d
```

For HTTPS, put it behind a reverse proxy (Nginx or Caddy):

```nginx
# /etc/nginx/sites-available/readmark
server {
    listen 80;
    server_name readmark.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Then use Certbot for free SSL:

```bash
certbot --nginx -d readmark.yourdomain.com
```

---

## Google OAuth Setup (Optional)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → APIs & Services → Credentials
3. Create OAuth 2.0 Client ID
4. Add your domain to authorized origins
5. Copy Client ID and Secret to `.env`

---

## Extension ↔ Server Sync

The extension can operate in two modes:

1. **Offline (default)** — data stored locally in Chrome storage
2. **Synced** — when logged in, data syncs to the ReadMark server

To connect the extension to your server, update the `API_URL` constant in the extension files to your server's URL.

---

## Project Structure

```
readmark-api/
├── main.py              # FastAPI entry point
├── config.py            # Environment settings
├── database.py          # Async SQLAlchemy + SQLite
├── models.py            # User + ReadingItem models
├── schemas.py           # Pydantic request/response schemas
├── auth.py              # JWT + Google OAuth + password hashing
├── url_utils.py         # URL normalization (strips tracking params)
├── routes/
│   ├── auth_routes.py   # Register, login, Google OAuth
│   └── items_routes.py  # CRUD, scroll tracking, sync
├── static/
│   └── index.html       # Web dashboard (single-page app)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## License

MIT
