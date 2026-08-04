#!/usr/bin/env bash
# Force-update NetAtlas UI/code on an existing install
set -euo pipefail

NETATLAS_HOME="${NETATLAS_HOME:-/opt/netatlas}"
BRANCH="${BRANCH:-main}"

# Root updating a netatlas-owned tree trips "dubious ownership" — allow this path.
git_na() {
  git -c "safe.directory=${NETATLAS_HOME}" "$@"
}

cd "${NETATLAS_HOME}"

echo "[netatlas] Fetching ${BRANCH}…"
git_na fetch --depth 1 origin "${BRANCH}"
git_na checkout -B "${BRANCH}" "FETCH_HEAD"
git_na reset --hard "FETCH_HEAD"

echo "[netatlas] Rebuilding frontend (no cache) and recreating containers…"
docker compose build --no-cache frontend
docker compose up -d --force-recreate frontend nginx

echo "[netatlas] Verifying UI…"
sleep 2
if curl -sk "https://127.0.0.1/js/i18n.js?v=i18n1" | grep -q "NetAtlas i18n"; then
  echo "[netatlas] OK — i18n frontend is live (default language: RU, switcher: RU/EN)"
else
  echo "[netatlas] WARN — i18n.js not served yet; check: docker compose logs frontend"
  exit 1
fi
