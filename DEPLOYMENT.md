# ComplyFlow — Production Deployment & Architecture Guide

> **Important Architecture Notice**: ComplyFlow is designed as a **Local-First, Self-Hosted Compliance Platform**.  
> **Google Cloud, Vertex AI, Cloud SQL, and Google Cloud Storage are NOT required.**

---

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                   React / Vite Frontend                 │
│              (Pure HttpOnly Cookie & CSRF)             │
└───────────────────────────┬────────────────────────────┘
                            │ (REST + SSE Streaming)
                            ▼
┌────────────────────────────────────────────────────────┐
│                    FastAPI Backend                     │
│    ├── RBAC & Cookie Session Security (HttpOnly)       │
│    ├── Structured Redacting Logger                     │
│    ├── Double Submit CSRF & Security Headers           │
│    └── ReportLab Deterministic PDF Exporter            │
└──────────────┬─────────────────────────┬───────────────┘
               │                         │
               ▼                         ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│     SQLite Database      │  │ Local Filesystem Storage │
│  (WAL Mode, Foreign Keys)│  │   (Project/Task Isolated)│
└──────────────────────────┘  └──────────────────────────┘
               │
               ▼
┌────────────────────────────────────────────────────────┐
│             Google Gemini API (via Google ADK)         │
│          Autonomous Multi-Agent Compliance Engine      │
└────────────────────────────────────────────────────────┘
```

---

## 2. Environment Variables Reference

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | Environment mode (`development` or `production`). |
| `LOG_LEVEL` | `INFO` | Log severity (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `GEMINI_API_KEY` | `""` | Google Gemini API key for live analysis. |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model variant (`gemini-3.5-flash` / `gemini-3.5-pro`). |
| `DATABASE_PATH` | `complyflow.db` | Local SQLite database file path. |
| `UPLOAD_DIR` | `uploads` | Directory for uploaded documents and reports. |
| `MAX_UPLOAD_SIZE_BYTES` | `52428800` | Maximum file upload size (50 MiB). |
| `BACKEND_HOST` | `0.0.0.0` | Bind host. |
| `BACKEND_PORT` | `8000` | Bind port. |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed CORS origins (no wildcards with credentials). |
| `SESSION_SECRET` | `(dev secret)` | HMAC signing secret for session tokens (min 32 chars). |
| `CSRF_SECRET` | `(dev secret)` | CSRF token secret. |
| `COOKIE_SECURE` | `false` | Set `true` in production behind HTTPS. |
| `COOKIE_SAMESITE` | `lax` | SameSite cookie policy (`lax` or `strict`). |
| `SESSION_LIFETIME_SECONDS` | `604800` | Session lifetime (7 days). |

---

## 3. Running Locally (Development)

### Backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

### Frontend
```powershell
cd frontend
npm install
npm run dev
```

---

## 4. Running in Production Mode (Local or Server)

1. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env and set:
   # APP_ENV=production
   # SESSION_SECRET=<generate a 32+ char random string>
   # COOKIE_SECURE=true (if behind HTTPS)
   # GEMINI_API_KEY=<your key>
   ```

2. **Start Backend**:
   ```bash
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
   ```

3. **Build & Serve Frontend**:
   ```bash
   cd frontend
   npm run build
   # Serve dist/ using Nginx, Caddy, or static file server
   ```

---

## 5. Docker Deployment (Zero-Cloud)

1. **Build Container**:
   ```bash
   docker build -t complyflow-backend -f backend/Dockerfile .
   ```

2. **Run Container**:
   ```bash
   docker run -d \
     --name complyflow \
     -p 8000:8000 \
     -v $(pwd)/data:/app/data \
     -v $(pwd)/uploads:/app/uploads \
     --env-file .env \
     complyflow-backend
   ```

---

## 6. Security Guarantees

1. **Ambient HttpOnly Cookies**: Tokens are never accessible via JavaScript. Zero `localStorage` or `sessionStorage` token leakage.
2. **Double Submit CSRF**: State-changing requests (`POST`, `PUT`, `DELETE`, `PATCH`) from cookies require valid `X-CSRF-Token` headers.
3. **Automated Secret & Path Redaction**: Application logs automatically scrub Gemini API keys, password hashes, session cookies, and local filesystem paths.
4. **Project Isolation**: Authorization is strictly project-scoped. Users of Project A cannot view or mutate Project B.
5. **Role-Based Access Control**:
   - `ADMIN`: Full management, invitations, role changes.
   - `AUDITOR`: Overrides, document uploads, verification runs, notes.
   - `REVIEWER`: Remediation uploads, notes (cannot create overrides).
   - `VIEWER`: Read-only report and timeline inspection.
6. **Immutable Snapshots**: Historical verification snapshots and audit timelines are append-only.
7. **Path Traversal Protection**: Uploaded files and evidence are sanitized against directory traversal and null bytes.

---

## 7. Health & Readiness Probes

- **Liveness Probe**: `GET /health` (Reports application and DB connectivity without exposing secrets).
- **Readiness Probe**: `GET /ready` (Returns HTTP 200 when ready to accept traffic).

---

## 8. Backup & Recovery

- **Database Backup**:
  ```bash
  sqlite3 complyflow.db ".backup 'backup_$(date +%Y%m%d_%H%M%S).db'"
  ```
- **Uploads Backup**: Backup the `uploads/` directory containing evidence files and exported PDF reports.
