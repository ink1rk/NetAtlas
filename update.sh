#!/usr/bin/env bash
# Update an existing NetAtlas install to the latest main.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/update.sh | sudo bash
#   sudo /opt/netatlas/update.sh
#   sudo netatlas-update
set -euo pipefail

NETATLAS_HOME="${NETATLAS_HOME:-/opt/netatlas}"

# When piped from curl, this script may run before the tree is updated —
# bootstrap minimal helpers, then re-exec from the freshly pulled tree so we
# always use the latest common.sh + compose after fetch.
_bootstrap_and_reexec() {
  if [[ "${NETATLAS_UPDATE_INNER:-}" == "1" ]]; then
    return 0
  fi
  if [[ ! -d "${NETATLAS_HOME}/.git" ]]; then
    echo "[netatlas] ERROR: ${NETATLAS_HOME} is not an installed NetAtlas tree." >&2
    echo "[netatlas] Fresh install:" >&2
    echo "  curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/install.sh | sudo bash" >&2
    exit 1
  fi
  if [[ "${EUID}" -ne 0 ]]; then
    echo "[netatlas] ERROR: Run as root (sudo)" >&2
    exit 1
  fi

  git -c "safe.directory=${NETATLAS_HOME}" -C "${NETATLAS_HOME}" remote set-url origin \
    "${REPO_URL:-https://github.com/ink1rk/NetAtlas.git}" 2>/dev/null || true
  echo "[netatlas] Fetching ${BRANCH:-main}…"
  git -c "safe.directory=${NETATLAS_HOME}" -C "${NETATLAS_HOME}" fetch --depth 1 origin "${BRANCH:-main}"
  git -c "safe.directory=${NETATLAS_HOME}" -C "${NETATLAS_HOME}" checkout -B "${BRANCH:-main}" FETCH_HEAD
  git -c "safe.directory=${NETATLAS_HOME}" -C "${NETATLAS_HOME}" reset --hard FETCH_HEAD

  # Re-exec the update.sh that now lives on disk (post-pull).
  export NETATLAS_UPDATE_INNER=1
  exec bash "${NETATLAS_HOME}/update.sh"
}

_bootstrap_and_reexec

# shellcheck disable=SC1091
source "${NETATLAS_HOME}/deploy/common.sh"

require_root
[[ -f "${NETATLAS_HOME}/.env" ]] || die "Missing ${NETATLAS_HOME}/.env — run install.sh first"
[[ -f "${NETATLAS_HOME}/docker-compose.yml" ]] || die "Missing docker-compose.yml"

log "Updating NetAtlas at ${NETATLAS_HOME} (already synced to ${BRANCH})"
rebuild_stack
wait_healthy 60
verify_ui
print_summary
log "Update complete"
