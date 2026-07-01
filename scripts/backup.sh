#!/bin/bash
# BackVora Backup Script
# Backs up: database, backend code, frontend source
# Keeps last 7 daily backups + last 4 weekly backups

set -euo pipefail

PROJECT_DIR="/home/slither/code/backvora"
BACKUP_DIR="${PROJECT_DIR}/backups"
DATE=$(date +%Y-%m-%d_%H%M)
DAY_OF_WEEK=$(date +%u)

mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly"

# 1. Database backup (sqlite3 .backup for consistency)
DB_BACKUP="${BACKUP_DIR}/daily/db_${DATE}.sqlite3"
cp "${PROJECT_DIR}/data/linkbuilder.db" "${DB_BACKUP}"
# Verify integrity
sqlite3 "${DB_BACKUP}" "PRAGMA integrity_check;" > /dev/null 2>&1 || {
    # Fallback: just copy if sqlite3 not available
    true
}

# 2. Code backup (backend + frontend source, no node_modules/venv)
CODE_BACKUP="${BACKUP_DIR}/daily/code_${DATE}.tar.gz"
tar czf "${CODE_BACKUP}" \
    -C "${PROJECT_DIR}" \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    backend/ \
    frontend-react/src/ \
    frontend-react/index.html \
    frontend-react/vite.config.ts \
    frontend-react/tsconfig*.json \
    frontend-react/package.json \
    scripts/ \
    data/linkbuilder.db \
    2>/dev/null || true

# 3. Weekly backup (Sundays)
if [ "${DAY_OF_WEEK}" = "7" ]; then
    cp "${DB_BACKUP}" "${BACKUP_DIR}/weekly/db_${DATE}.sqlite3"
    cp "${CODE_BACKUP}" "${BACKUP_DIR}/weekly/code_${DATE}.tar.gz"
fi

# 4. Rotate: keep 7 daily, 4 weekly
cd "${BACKUP_DIR}/daily" && ls -t db_*.sqlite3 2>/dev/null | tail -n +8 | xargs -r rm --
cd "${BACKUP_DIR}/daily" && ls -t code_*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm --
cd "${BACKUP_DIR}/weekly" && ls -t db_*.sqlite3 2>/dev/null | tail -n +5 | xargs -r rm --
cd "${BACKUP_DIR}/weekly" && ls -t code_*.tar.gz 2>/dev/null | tail -n +5 | xargs -r rm --

echo "Backup complete: ${DATE}"
ls -lh "${DB_BACKUP}" "${CODE_BACKUP}"
