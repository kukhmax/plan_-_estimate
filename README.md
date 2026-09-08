# Plan & Estimate (Telegram Mini App)

Telegram Mini App for managing interior finishing and renovation work in Poland (*prace wykończeniowe i remontowe*).

## Project Structure

```
.
├── backend/          # FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic v2, pytest
├── frontend/         # React, TypeScript, Vite, Tailwind CSS, Vitest
├── bot/              # aiogram 3.x Telegram Bot
├── docs/             # Development progress & architecture documentation
├── docker-compose.yml# Local infrastructure (PostgreSQL, Backend)
└── GEMINI.md         # Permanent engineering rules & workflow
```

## Quick Start & Essential Commands

### 1. Environment Setup
```bash
cp .env.example .env
```

### 2. Database Startup
Start the PostgreSQL database service using Docker Compose:
```bash
docker compose up -d postgres
```
To run the full stack (database + backend) in containers:
```bash
docker compose up -d
```

### 3. Backend Startup
Run the FastAPI backend locally:
```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```
Health Check: `http://localhost:8000/api/health`

### 4. Backend Tests
Execute the backend automated test suite:
```bash
cd backend
pytest
```

### 5. Frontend Startup
Run the Vite development server for the frontend:
```bash
cd frontend
npm install
npm run dev
```
Open in browser: `http://localhost:5173`

### 6. Frontend Tests
Execute the frontend Vitest suite:
```bash
cd frontend
npm test -- --run
```

### 7. Production Build
Typecheck and build the production bundle for the frontend:
```bash
cd frontend
npm run build
```

---

## Telegram Bot (Optional Bootstrap)
```bash
cd bot
source ../backend/.venv/bin/activate
python main.py
```
