# MEMORA AI

> Private AI Memory and Agent Intelligence Platform

MEMORA AI is an intelligent personal AI assistant equipped with memory, contextual retrieval, and proactive agency.

---

## Project Structure

```text
MEMORA-AI/
│
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── schemas.py
│   │   │
│   │   └── services/
│   │       ├── __init__.py
│   │       └── llm_service.py
│   │
│   ├── .env
│   ├── .env.example
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   ├── index.css
│   │   └── main.jsx
│   └── package.json
│
├── docs/
│
├── .gitignore
├── README.md
└── LICENSE
```

---

## Quickstart

### 1. Virtual Environment & Backend Setup

```powershell
# From project root
py -3.11 -m venv .venv
# Or: python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Install dependencies
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Edit `backend/.env` with your Nebius API Key:

```env
NEBIUS_API_KEY=YOUR_ACTUAL_NEBIUS_API_KEY
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=nvidia/Nemotron-3_5-Lightning
FRONTEND_ORIGIN=http://localhost:5173
```

### 3. Run the Backend API

```powershell
fastapi dev app/main.py
# or
uvicorn app.main:app --reload --port 8000
```

Access the interactive API docs at:
- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/health`
