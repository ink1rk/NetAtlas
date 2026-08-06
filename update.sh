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

echo "[netatlas] Rebuilding API + frontend and recreating stack…"
docker compose build --no-cache api frontend
docker compose up -d --force-recreate api worker beat syslog frontend nginx

echo "[netatlas] Waiting for API…"
ok=0
for i in $(seq 1 40); do
  if curl -kfsS "https://127.0.0.1/api/v1/healthz" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 3
done
if [[ "${ok}" -ne 1 ]]; then
  echo "[netatlas] WARN — API health check failed; inspect: docker compose logs api --tail 100"
  exit 1
fi

echo "[netatlas] Verifying UI…"
if curl -sk "https://127.0.0.1/js/i18n.js?v=rel1" | grep -q "NetAtlas i18n"; then
  echo "[netatlas] OK — API healthy, Design System v2 UI live (RU/EN)"
else
  echo "[netatlas] WARN — i18n.js not served yet; check: docker compose logs frontend"
  exit 1
fi

echo "[netatlas] Update complete — NetAtlas 1.3.0"
