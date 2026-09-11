#!/usr/bin/env bash
#
# Elite One Desk — nightly backup.
#
# Two things need backing up and they fail differently: the database can be
# restored from a dump, but an uploaded photograph exists nowhere else. Both are
# written to /var/backups/elite-one-desk and pruned after RETENTION_DAYS.
#
#   sudo install -m 0755 deploy/backup.sh /usr/local/bin/elite-one-desk-backup
#   sudo crontab -e
#   15 2 * * *  /usr/local/bin/elite-one-desk-backup >> /var/log/elite-one-desk/backup.log 2>&1
#
# Copy the results off the machine as well. A backup that lives on the server it
# is protecting is not a backup.

set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/elite-one-desk/app}"
UPLOAD_DIR="${UPLOAD_DIR:-/var/www/elite-one-desk/uploads}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/elite-one-desk}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"

# DATABASE_URL comes from the application's own .env so the two can never drift.
if [[ -f "${APP_DIR}/.env" ]]; then
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "${APP_DIR}/.env" | tail -n1 | cut -d= -f2-)"
fi
: "${DATABASE_URL:?DATABASE_URL is not set and was not found in ${APP_DIR}/.env}"

mkdir -p "${BACKUP_DIR}"
umask 077

echo "[$(date -u +%FT%TZ)] database → ${BACKUP_DIR}/db-${STAMP}.sql.gz"
# Custom format would be smaller, but plain SQL can be read and partially
# restored by hand at 3am, which matters more than the megabytes.
pg_dump --no-owner --no-privileges --clean --if-exists "${DATABASE_URL}" \
  | gzip -9 > "${BACKUP_DIR}/db-${STAMP}.sql.gz.tmp"
mv "${BACKUP_DIR}/db-${STAMP}.sql.gz.tmp" "${BACKUP_DIR}/db-${STAMP}.sql.gz"

if [[ -d "${UPLOAD_DIR}" ]]; then
  echo "[$(date -u +%FT%TZ)] uploads  → ${BACKUP_DIR}/uploads-${STAMP}.tar.gz"
  tar -czf "${BACKUP_DIR}/uploads-${STAMP}.tar.gz.tmp" -C "$(dirname "${UPLOAD_DIR}")" "$(basename "${UPLOAD_DIR}")"
  mv "${BACKUP_DIR}/uploads-${STAMP}.tar.gz.tmp" "${BACKUP_DIR}/uploads-${STAMP}.tar.gz"
else
  echo "[$(date -u +%FT%TZ)] uploads  → skipped, ${UPLOAD_DIR} does not exist"
fi

echo "[$(date -u +%FT%TZ)] pruning backups older than ${RETENTION_DAYS} days"
find "${BACKUP_DIR}" -maxdepth 1 -type f -name '*.gz' -mtime "+${RETENTION_DAYS}" -delete

# A dump that cannot be read is worse than no dump, because it is trusted.
gzip -t "${BACKUP_DIR}/db-${STAMP}.sql.gz"
echo "[$(date -u +%FT%TZ)] done — $(du -sh "${BACKUP_DIR}" | cut -f1) in ${BACKUP_DIR}"
