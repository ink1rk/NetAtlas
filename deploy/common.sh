#!/usr/bin/env bash
# Shared helpers for install.sh / update.sh (sourced, not executed).
# shellcheck shell=bash

NETATLAS_HOME="${NETATLAS_HOME:-/opt/netatlas}"
NETATLAS_USER="${NETATLAS_USER:-netatlas}"
REPO_URL="${REPO_URL:-https://github.com/ink1rk/NetAtlas.git}"
BRANCH="${BRANCH:-main}"

log() { printf '[netatlas] %s\n' "$*"; }
die() { printf '[netatlas] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run as root (sudo …)"
  fi
}

git_na() {
  git -c "safe.directory=${NETATLAS_HOME}" "$@"
}

read_version() {
  local vf="${1:-${NETATLAS_HOME}/VERSION}"
  if [[ -f "${vf}" ]]; then
    tr -d '[:space:]' < "${vf}"
  else
    echo "dev"
  fi
}

# Unique image tag so compose always recreates from a freshly built image.
compute_image_tag() {
  local base sha
  base="$(read_version "${NETATLAS_HOME}/VERSION")"
  sha="$(git_na -C "${NETATLAS_HOME}" rev-parse --short HEAD 2>/dev/null || echo "local")"
  printf '%s-%s\n' "${base}" "${sha}"
}

upsert_env() {
  local key="$1" value="$2" env_file="${NETATLAS_HOME}/.env"
  [[ -f "${env_file}" ]] || die "Missing ${env_file}"
  if grep -q "^${key}=" "${env_file}"; then
    # Escape sed replacement safely
    local esc
    esc="$(printf '%s' "${value}" | sed -e 's/[\\/&]/\\&/g')"
    sed -i "s/^${key}=.*/${key}=${esc}/" "${env_file}"
  else
    printf '%s=%s\n' "${key}" "${value}" >> "${env_file}"
  fi
}

sync_repo() {
  require_root
  mkdir -p "${NETATLAS_HOME}"
  if [[ -d "${NETATLAS_HOME}/.git" ]]; then
    log "Fetching ${BRANCH} into ${NETATLAS_HOME}"
    git_na -C "${NETATLAS_HOME}" remote set-url origin "${REPO_URL}" 2>/dev/null || true
    git_na -C "${NETATLAS_HOME}" fetch --depth 1 origin "${BRANCH}"
    git_na -C "${NETATLAS_HOME}" checkout -B "${BRANCH}" "FETCH_HEAD"
    git_na -C "${NETATLAS_HOME}" reset --hard "FETCH_HEAD"
  else
    die "No git checkout at ${NETATLAS_HOME}. Fresh install: curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/install.sh | sudo bash"
  fi
}

rebuild_stack() {
  local tag
  tag="$(compute_image_tag)"
  log "Image tag: ${tag}"
  upsert_env "NETATLAS_VERSION" "${tag}"
  # Compose auto-loads ${NETATLAS_HOME}/.env; also export for this shell.
  export NETATLAS_VERSION="${tag}"

  cd "${NETATLAS_HOME}"

  log "Building API + frontend (no cache)…"
  docker compose build --no-cache --pull=false api frontend

  log "Recreating application containers…"
  docker compose up -d --force-recreate --remove-orphans \
    api worker beat syslog frontend nginx

  # Persist systemd unit from the tree we just pulled
  if [[ -f "${NETATLAS_HOME}/deploy/systemd/netatlas.service" ]]; then
    cp "${NETATLAS_HOME}/deploy/systemd/netatlas.service" /etc/systemd/system/netatlas.service
    systemctl daemon-reload
    systemctl enable netatlas.service >/dev/null 2>&1 || true
  fi

  # Convenience wrappers
  install -m 0755 "${NETATLAS_HOME}/update.sh" /usr/local/bin/netatlas-update
  cat > /usr/local/bin/netatlas-status <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "${NETATLAS_HOME:-/opt/netatlas}"
docker compose ps
echo
curl -kfsS https://127.0.0.1/api/v1/healthz 2>/dev/null || echo "healthz: down"
curl -kfsS https://127.0.0.1/api/v1/readyz 2>/dev/null || echo "readyz: down"
EOF
  chmod 0755 /usr/local/bin/netatlas-status
}

wait_healthy() {
  local tries="${1:-60}" i
  log "Waiting for API healthz + readyz…"
  for i in $(seq 1 "${tries}"); do
    if curl -kfsS "https://127.0.0.1/api/v1/healthz" >/dev/null 2>&1 \
      && curl -kfsS "https://127.0.0.1/api/v1/readyz" >/dev/null 2>&1; then
      log "API healthy"
      return 0
    fi
    sleep 3
  done
  log "API logs (tail):"
  docker compose -f "${NETATLAS_HOME}/docker-compose.yml" --project-directory "${NETATLAS_HOME}" logs api --tail 80 || true
  die "Health check failed"
}

verify_ui() {
  log "Verifying UI assets…"
  local body
  body="$(curl -sk "https://127.0.0.1/js/i18n.js" || true)"
  if printf '%s' "${body}" | grep -q "NetAtlas i18n"; then
    log "UI OK (i18n present)"
  else
    die "UI not serving i18n.js — check: docker compose logs frontend nginx"
  fi
  # Login page must load
  if ! curl -kfsS "https://127.0.0.1/" >/dev/null 2>&1; then
    die "Frontend root not reachable"
  fi
}

print_summary() {
  local ver
  ver="$(read_version)"
  local tag
  tag="$(grep -E '^NETATLAS_VERSION=' "${NETATLAS_HOME}/.env" 2>/dev/null | cut -d= -f2- || echo "?")"
  log "NetAtlas ${ver} ready (image ${tag})"
  log "UI:     https://<server-ip>/"
  log "Health: https://<server-ip>/api/v1/healthz"
  if [[ -f "${NETATLAS_HOME}/logs/initial_admin_password.txt" ]]; then
    log "Admin password file: ${NETATLAS_HOME}/logs/initial_admin_password.txt"
  fi
  log "Update anytime:  curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/update.sh | sudo bash"
  log "Or locally:      sudo netatlas-update"
  log "Status:          sudo netatlas-status"
}
