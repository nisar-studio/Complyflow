# ComplyFlow — Production Deployment Guide

## Prerequisites

- **Docker** (20.10+) and **Docker Compose** (v2+), OR
- **Python 3.11+** for bare-metal deployment
- A **Google Gemini API key** ([get one here](https://aistudio.google.com/apikey))
- A server with at least 1GB RAM and 10GB disk

---

## 1. Environment Setup

### Copy and configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set the following **required** production values:

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_ENV` | **Yes** | Set to `production` |
| `SESSION_SECRET` | **Yes** | Cryptographic secret for session signing (min 32 chars) |
| `CSRF_SECRET` | **Yes** | Cryptographic secret for CSRF tokens (min 32 chars) |
| `GEMINI_API_KEY` | **Yes** | Google Gemini API key for AI-powered analysis |
| `CORS_ORIGINS` | **Yes** | Your frontend URL (e.g. `https://compliance.example.com`) |
| `COOKIE_SECURE` | **Yes** | Set to `true` when behind HTTPS |
| `DATABASE_PATH` | No | SQLite database path (default: `complyflow.db`) |
| `UPLOAD_DIR` | No | File upload directory (default: `uploads`) |
| `BACKEND_PORT` | No | Server port (default: `8000`) |
| `GEMINI_MODEL` | No | Gemini model (default: `gemini-3.5-flash`) |
| `LOG_LEVEL` | No | Log level (default: `INFO`) |

### Generate secure secrets

```bash
# Generate SESSION_SECRET
python -c "import secrets; print(secrets.token_hex(32))"

# Generate CSRF_SECRET
python -c "import secrets; print(secrets.token_hex(32))"
```

### Validate configuration

```bash
cd backend
python -m app verify-config
```

This will confirm your secrets are strong enough and your config is valid.

---

## 2. First Admin Provisioning

**Before** starting the server, create the initial admin account:

```bash
cd backend
python -m app create-admin
```

You will be prompted for:
- Admin email address
- Admin display name
- Password (entered securely, not shown)

For non-interactive use (e.g. in scripts):

```bash
python -m app create-admin --email admin@example.com --name "Admin User" --password "SecurePassword123!"
```

> ⚠️ **The `/api/auth/bootstrap` endpoint is disabled in production.** You MUST use the CLI to create the first admin.

---

## 3. Deployment Options

### Option A: Docker Compose (Recommended)

```bash
# Build and start
docker compose up -d --build

# Create the first admin
docker compose exec backend python -m app create-admin

# View logs
docker compose logs -f backend

# Stop
docker compose down
```

### Option B: Docker (Manual)

```bash
cd backend

# Build the image
docker build -t complyflow-backend .

# Run with required environment variables
docker run -d \
  --name complyflow-backend \
  -p 8000:8000 \
  -v complyflow-data:/app/data \
  -v complyflow-uploads:/app/uploads \
  -e APP_ENV=production \
  -e SESSION_SECRET="your-unique-session-secret-here" \
  -e CSRF_SECRET="your-unique-csrf-secret-here" \
  -e COOKIE_SECURE=true \
  -e GEMINI_API_KEY="your-gemini-api-key" \
  -e CORS_ORIGINS="https://your-frontend-domain.com" \
  complyflow-backend

# Create the first admin
docker exec -it complyflow-backend python -m app create-admin
```

### Option C: Bare Metal

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export APP_ENV=production
export SESSION_SECRET="your-unique-session-secret-here"
export CSRF_SECRET="your-unique-csrf-secret-here"
export COOKIE_SECURE=true
export GEMINI_API_KEY="your-gemini-api-key"
export CORS_ORIGINS="https://your-frontend-domain.com"
export DATABASE_PATH=/opt/complyflow/data/complyflow.db
export UPLOAD_DIR=/opt/complyflow/uploads

# Create data directories
mkdir -p /opt/complyflow/data /opt/complyflow/uploads

# Create admin
python -m app create-admin

# Start server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

> ⚠️ **Always use `--workers 1`**. The SSE event broadcaster is process-local and requires a single worker.

### Option D: Frontend Build + Backend

```bash
# Build frontend
cd frontend
npm ci
npm run build

# Serve with nginx or similar, proxy /api to backend
# See "Reverse Proxy" section below
```

---

## 4. Persistent Storage

The application stores data in two locations:

| Path | Content | Backup? |
|------|---------|---------|
| `DATABASE_PATH` (default: `complyflow.db`) | SQLite database with all application data | **Yes — critical** |
| `UPLOAD_DIR` (default: `uploads/`) | Uploaded evidence documents, remediation files, reports | **Yes** |

### Docker Volumes

Docker Compose creates named volumes `complyflow-data` and `complyflow-uploads` that persist across container restarts.

### Bare Metal

Ensure the data directory is backed up regularly (see [BACKUP_RESTORE.md](BACKUP_RESTORE.md)).

---

## 5. HTTPS / Reverse Proxy

ComplyFlow does **not** handle TLS directly. Use a reverse proxy in front of it.

### Nginx Example

```nginx
server {
    listen 443 ssl http2;
    server_name compliance.example.com;

    ssl_certificate /etc/letsencrypt/live/compliance.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/compliance.example.com/privkey.pem;

    # Frontend static files
    location / {
        root /var/www/complyflow/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE support
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name compliance.example.com;
    return 301 https://$host$request_uri;
}
```

### Caddy Example

```
compliance.example.com {
    tls /etc/caddy/cert.pem /etc/caddy/key.pem

    handle /api/* {
        reverse_proxy localhost:8000
    }

    handle {
        root * /var/www/complyflow/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

---

## 6. Health & Readiness Checks

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `GET /health` | Liveness probe | `{"status": "ok", ...}` (200) |
| `GET /ready` | Readiness probe | `{"status": "ready", ...}` (200) or 503 |

### Docker HEALTHCHECK

The Dockerfile includes a built-in healthcheck that polls `/health` every 30 seconds.

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /ready
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## 7. Upgrades

### Pre-upgrade checklist

1. **Back up the database** (see [BACKUP_RESTORE.md](BACKUP_RESTORE.md))
2. **Back up uploaded files**
3. Review the changelog for breaking changes

### Docker upgrade

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose up -d --build

# Verify health
curl http://localhost:8000/health
```

### Schema migrations

ComplyFlow uses **auto-migration on startup**. The `_init_db()` method:
- Creates new tables with `CREATE TABLE IF NOT EXISTS`
- Adds missing columns with `ALTER TABLE ... ADD COLUMN`
- Migrates primary keys when needed

No manual migration steps are required. Backups are still recommended before upgrades.

### Rollback

If the new version has issues:

```bash
# Docker: revert to previous image tag
git checkout <previous-commit>
docker compose up -d --build

# Bare metal: revert and restart
git checkout <previous-commit>
pip install -r requirements.txt
# Restart uvicorn
```

---

## 8. Troubleshooting

### "Production configuration rejected: SESSION_SECRET..."

Your `SESSION_SECRET` is missing, too short (< 32 chars), or using a known default. Generate a new one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### "Production configuration rejected: CSRF_SECRET..."

Same as above but for `CSRF_SECRET`. Both must be unique, random, and ≥ 32 characters.

### Database is locked / busy

SQLite handles concurrent access via WAL mode, but heavy write loads can cause transient locks. The application uses a 5-second busy timeout. If you see persistent lock errors:
- Ensure only one backend worker is running (`--workers 1`)
- Check for other processes accessing the database file

### Uploads not persisting after container restart

Ensure Docker volumes are properly mounted. Check with:

```bash
docker compose exec backend ls -la /app/uploads
```

### Health check returns "degraded"

The SQLite database may not be initialized yet. Wait a few seconds and check again. If persistent, check the database file permissions.

### AI analysis fails with 500

Ensure `GEMINI_API_KEY` is set and valid. The health endpoint shows `"gemini_configured": true` when the key is present.

---

## 9. Architecture Summary

```
┌──────────────┐     ┌──────────────────┐     ┌────────────┐
│   Frontend   │────▶│  FastAPI Backend  │────▶│   SQLite   │
│  (React/Vite)│     │   (uvicorn)      │     │  (WAL mode)│
└──────────────┘     │                  │     └────────────┘
                     │  ┌─────────────┐ │
                     │  │  Gemini AI  │ │
                     │  │  (ADK)      │ │
                     │  └─────────────┘ │
                     └──────────────────┘
```

- **Local-first**: No external database or cloud storage required
- **Single worker**: Required for SSE event streaming
- **SQLite WAL**: Supports concurrent reads, serialized writes
- **HttpOnly cookies**: No token storage in localStorage/sessionStorage
- **CSRF protection**: Double-submit cookie pattern
