# ComplyFlow — Backup & Restore Guide

## Overview

ComplyFlow stores all data in two locations:

1. **SQLite database** — all application data (projects, requirements, audit events, users, etc.)
2. **Upload directory** — evidence documents, remediation files, generated reports

Both must be backed up for complete data protection.

---

## 1. Database Backup

### Safe Backup Procedure (WAL Mode)

SQLite WAL mode allows concurrent reads during writes. For a **consistent backup** while the application is running:

```bash
# Method 1: SQLite .backup command (safest, works while running)
sqlite3 /path/to/complyflow.db ".backup '/path/to/backup/complyflow-$(date +%Y%m%d-%H%M%S).db'"

# Method 2: File copy (safe with WAL mode, but snapshot may be slightly behind)
cp /path/to/complyflow.db /path/to/backup/complyflow-$(date +%Y%m%d-%H%M%S).db
cp /path/to/complyflow.db-wal /path/to/backup/complyflow-$(date +%Y%m%d-%H%M%S).db-wal 2>/dev/null
cp /path/to/complyflow.db-shm /path/to/backup/complyflow-$(date +%Y%m%d-%H%M%S).db-shm 2>/dev/null
```

### Docker Backup

```bash
# Backup from running container
docker compose exec backend python -c "
import sqlite3, shutil, datetime
src = '/app/data/complyflow.db'
dst = f'/app/data/backup-{datetime.datetime.now().strftime(\"%Y%m%d-%H%M%S\")}.db'
shutil.copy2(src, dst)
print(f'Backup created: {dst}')
"

# Copy backup out of container
docker compose cp backend:/app/data/backup-*.db ./backups/
```

### Recommended Backup Frequency

| Scenario | Frequency |
|----------|-----------|
| Low usage (< 10 projects) | Daily |
| Medium usage (10-100 projects) | Every 6-12 hours |
| High usage / compliance-critical | Every 1-2 hours |

### Automated Backup Script Example

```bash
#!/bin/bash
# /opt/complyflow/backup.sh
BACKUP_DIR="/opt/complyflow/backups"
DB_PATH="/opt/complyflow/data/complyflow.db"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/complyflow-$TIMESTAMP.db'"

# Keep last 30 backups
ls -t "$BACKUP_DIR"/complyflow-*.db | tail -n +31 | xargs rm -f 2>/dev/null

echo "Backup completed: $BACKUP_DIR/complyflow-$TIMESTAMP.db"
```

### Cron Job (every 6 hours)

```bash
0 */6 * * * /opt/complyflow/backup.sh >> /var/log/complyflow-backup.log 2>&1
```

---

## 2. Uploads Backup

```bash
# Backup uploads directory
tar -czf /path/to/backup/uploads-$(date +%Y%m%d-%H%M%S).tar.gz /path/to/uploads/
```

### Docker Backup

```bash
docker compose cp backend:/app/uploads ./backups/uploads-$(date +%Y%m%d).tar.gz
```

---

## 3. Restore Procedure

### Stop the Application

```bash
# Docker
docker compose down

# Bare metal
# Stop the uvicorn process
```

### Restore Database

```bash
# Replace the database file
cp /path/to/backup/complyflow-YYYYMMDD-HHMMSS.db /path/to/data/complyflow.db

# If you also have WAL files, copy those too
cp /path/to/backup/complyflow-YYYYMMDD-HHMMSS.db-wal /path/to/data/complyflow.db-wal
cp /path/to/backup/complyflow-YYYYMMDD-HHMMSS.db-shm /path/to/data/complyflow.db-shm
```

### Restore Uploads

```bash
tar -xzf /path/to/backup/uploads-YYYYMMDD-HHMMSS.tar.gz -C /
```

### Restart

```bash
# Docker
docker compose up -d

# Bare metal
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

---

## 4. Verification After Restore

### Check health

```bash
curl http://localhost:8000/health
# Should return: {"status": "ok", "database_connected": true, ...}
```

### Check readiness

```bash
curl http://localhost:8000/ready
# Should return: {"status": "ready", "database_ready": true, ...}
```

### Verify data

```bash
# Quick database check
sqlite3 /path/to/complyflow.db "SELECT COUNT(*) as projects FROM projects;"
sqlite3 /path/to/complyflow.db "SELECT COUNT(*) as users FROM users;"
sqlite3 /path/to/complyflow.db "SELECT COUNT(*) as audit_events FROM audit_events;"
```

### Verify uploads

```bash
ls -la /path/to/uploads/
# Should show project directories with uploaded files
```

---

## 5. Disaster Recovery

### Complete Server Failure

1. Provision a new server
2. Install Docker + Docker Compose
3. Clone the repository
4. Copy `.env` from backup
5. Restore database and uploads from backup
6. Run `docker compose up -d --build`
7. Verify with health check

### Bad Deployment Rollback

```bash
# Revert code
git checkout <previous-commit>

# Rebuild
docker compose up -d --build

# If database was modified by the bad version:
# Restore database from pre-upgrade backup
```

### Database Corruption

If the SQLite database is corrupted:

1. Stop the application
2. Attempt repair: `sqlite3 complyflow.db ".recover" | sqlite3 complyflow-fixed.db`
3. If repair fails, restore from backup
4. If no backup exists, the database must be recreated (data will be lost)

---

## 6. What NOT to Back Up

- `.env` files (should be managed separately, e.g., in a secrets manager)
- `node_modules/` (reinstallable via `npm ci`)
- `__pycache__/` (rebuildable)
- `frontend/dist/` (rebuildable via `npm run build`)
- `.freebuff/` (agent working directory)
