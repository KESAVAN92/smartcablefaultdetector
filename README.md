# Underground Cable Fault Distance Locator — Graph Mapping Extension

This workspace contains the backend and frontend for the "Underground Cable Fault Distance Locator with Graph-Based Digital Mapping" project. It extends a validated hardware prototype with a simulated readings pipeline, graph engine, and a mapping UI.

Overview
- backend/: Flask-based APIs for Modules 1–4
- frontend/: React + Vite UI

Quickstart (local)
1. Copy `.env.example` to `.env` and set `JWT_SECRET`.
2. Backend:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
set JWT_SECRET=some-secret
python backend/app.py
```

3. Frontend:

```bash
cd frontend
npm install
npm run dev
```

Docker (dev):

```bash
docker compose up --build
```

What I changed
- Implemented Module 4 backend scaffolding with users, JWT auth, fault events, alerts, and basic reports (CSV export).
- Added `require_auth` guards to Module 2 mutation endpoints.
- Frontend: added login, auth context, and reports UI in `Module4`.
- Added `.env.example`, `.gitignore`, `docker-compose.yml`, and a notification interface.

Next steps / Known gaps
- Backend: add robust websocket broadcaster for alerts (Module 4 currently keeps in-app notification list; real push requires background broadcaster).
- Frontend: integrate live toasts and buzzer from server-sent websocket messages (needs server broadcaster).
- Tests: run `pytest` and fix any regressions (this environment lacked installed deps so tests weren't executed here).
# Cable Fault Detector Starter

This workspace now includes:

- `frontend/`: React + Vite starter app
- `backend/`: Python Flask API starter
- `module1` to `module4` in both frontend and backend

## Frontend

```bash
cd frontend
npm install
npm run dev
```

If PowerShell blocks `npm`, use:

```bash
npm.cmd install
npm.cmd run dev
```

## Backend

```bash
cd backend
python -m pip install -r requirements.txt
python app.py
```

## API Routes

- `GET /api/health`
- `GET /api/module1/`
- `GET /api/module2/`
- `GET /api/module3/`
- `GET /api/module4/`
