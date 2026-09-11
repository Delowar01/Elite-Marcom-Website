#!/usr/bin/env bash
#
# Elite One Desk — release script.
#
# Run it on the VPS from the application directory:
#
#   cd /var/www/elite-one-desk/app && ./deploy/deploy.sh
#
# Order matters: build first, migrate second, restart last. A build that fails
# leaves the running site untouched, and migrations only run once there is a
# release that can actually use them.

set -euo pipefail

APP_DIR="${APP_DIR:-/var/www/elite-one-desk/app}"
SERVICE="${SERVICE:-elite-one-desk}"
BRANCH="${BRANCH:-main}"

cd "${APP_DIR}"

echo "==> Fetching ${BRANCH}"
git fetch --prune origin
git checkout "${BRANCH}"
git reset --hard "origin/${BRANCH}"

echo "==> Installing dependencies"
npm ci --omit=dev --ignore-scripts
# sharp needs its platform binary, which --ignore-scripts skips.
npm rebuild sharp

echo "==> Building"
npm run build

echo "==> Migrating the database"
npm run db:migrate

echo "==> Syncing seed content (idempotent — existing content is never overwritten)"
npm run db:seed

echo "==> Copying static assets next to the standalone server"
# `output: standalone` does not copy these; without them the server has no
# stylesheets and no fonts.
rm -rf .next/standalone/.next/static .next/standalone/public
cp -r .next/static .next/standalone/.next/static
cp -r public .next/standalone/public

echo "==> Restarting"
if command -v systemctl >/dev/null && systemctl list-unit-files | grep -q "^${SERVICE}.service"; then
  sudo systemctl restart "${SERVICE}"
  sleep 3
  systemctl is-active --quiet "${SERVICE}" && echo "    ${SERVICE} is running"
elif command -v pm2 >/dev/null; then
  pm2 reload elite-one-desk --update-env
else
  echo "!! No process manager found. Start the app yourself." >&2
  exit 1
fi

echo "==> Checking the site answers"
for _ in $(seq 1 10); do
  if curl -fsS -o /dev/null http://127.0.0.1:3000/; then
    echo "    OK"
    exit 0
  fi
  sleep 2
done

echo "!! The site did not answer after the restart. Check the logs." >&2
exit 1
