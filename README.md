# 4-SPIN (Wheel of Fortune) — SQLite Edition

A complete, self-contained clone of the **4-SPIN** hackathon competition system, re-engineered to run on **SQLite (WAL mode)** instead of MongoDB. Designed to reliably host **40+ teams (160+ participants)** simultaneously.

---

## Architecture & Improvements

| Component | Original System | This Clone (`four_spin`) |
|---|---|---|
| **Database** | MongoDB (PyMongo direct driver) | **SQLite 3 with WAL Mode** via Django ORM |
| **Migrations** | Manual indexes script | Standard Django migrations (`makemigrations`, `migrate`) |
| **Concurrency** | Mongo document locks | `PRAGMA journal_mode=WAL;`, `busy_timeout=20000`, `IMMEDIATE` transaction mode |
| **Teams Capacity** | 30 teams hardcoded | **40 teams** seeded by default (expandable) |
| **Team Credentials** | Printed once to console | Exported to `team_credentials.csv` |
| **Rate Limiter** | Mongo TTL index per IP | SQLite-backed, keyed by `(IP, login_target)` so 40 teams on shared venue Wi-Fi don't throttle each other |
| **Realtime** | python-socketio ASGI | python-socketio ASGI with unified Uvicorn server |
| **Frontend** | React 19 + Vite | React 19 + Vite (proxies `/api` & `/socket.io` to local backend) |

---

## Quick Start (Running Locally)

### 1. Prerequisites
- Python 3.11+
- Node.js 18+

### 2. Backend Setup
```bash
cd "d:/wheel_of fortune/four_spin"

# Activate Python virtual environment
.\.venv\Scripts\Activate.ps1

# Run migrations
cd config
python manage.py migrate

# Start backend server (Uvicorn ASGI on port 8000)
python -m uvicorn config.asgi:application --host 127.0.0.1 --port 8000 --workers 1
```

### 3. Frontend Setup
```bash
cd "d:/wheel_of fortune/four_spin/frontend"

# Install dependencies (if not already installed)
npm install

# Start Vite dev server
npm run dev
```
Open **`http://127.0.0.1:5174/`** (or `5173`) in your browser.

---

## Accounts & Credentials

### Admin Account
- **Username**: `admin`
- **Password**: check your terminal output from the seed step or see `.env` / reset via:
  ```bash
  cd config
  python manage.py seed_game
  ```
  *(Or set `GAME_ADMIN_PASSWORD` in your environment and run non-interactively)*

### 40 Team Accounts
- Generated automatically into [`team_credentials.csv`](./team_credentials.csv).
- Format: `team_code, username, password`
- Teams range from `TEAM01` (`team01`) through `TEAM40` (`team40`).
- Each team logs in at `/team/login` using their team code (`TEAM01`) and generated password.

### Volunteer Accounts
- Created by the Admin in the dashboard (`POST /api/admin/volunteers`).
- Volunteers log in at `/volunteer/login` to manage attendance and review buzzer submissions.

---

## Hosting 40 Teams (Production Deployment)

### Why SQLite Works for 40 Teams:
1. **Low write frequency**: 40 teams submit spins and buzzers a few times per round (seconds apart).
2. **WAL mode (Write-Ahead Logging)**: Readers (leaderboard polling, state checks) **never block** writers.
3. **`IMMEDIATE` transaction mode**: Eliminates deadlocks during concurrent spin attempts.
4. **Single worker Uvicorn**: Keeps in-memory Socket.IO rooms consistent without needing Redis.

### Hosting on Render / Railway / VPS:
- Deploy using the included [`render.yaml`](./render.yaml).
- Ensure a **persistent disk** is attached and set:
  ```env
  SQLITE_PATH=/var/data/db.sqlite3
  ```
- Command to run in production:
  ```bash
  python manage.py migrate --noinput && python -m uvicorn config.asgi:application --host 0.0.0.0 --port $PORT --workers 1
  ```
