#!/usr/bin/env bash
# NetAtlas one-command installer for Ubuntu 22.04 / 24.04
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/install.sh | sudo bash
#   sudo ./install.sh
set -euo pipefail

NETATLAS_HOME="${NETATLAS_HOME:-/opt/netatlas}"
NETATLAS_USER="${NETATLAS_USER:-netatlas}"
REPO_URL="${REPO_URL:-https://github.com/ink1rk/NetAtlas.git}"
BRANCH="${BRANCH:-main}"

log() { printf '[netatlas] %s\n' "$*"; }
die() { printf '[netatlas] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Run as root (sudo ./install.sh)"
  fi
}

check_ubuntu() {
  if [[ ! -f /etc/os-release ]]; then
    die "Cannot detect OS"
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID}" == "ubuntu" ]] || die "Ubuntu required (found: ${ID})"
  case "${VERSION_ID}" in
    22.04|24.04) ;;
    *) die "Unsupported Ubuntu ${VERSION_ID}. Supported: 22.04, 24.04" ;;
  esac
  log "Ubuntu ${VERSION_ID} detected"
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    log "Docker already installed"
    return
  fi
  log "Installing Docker Engine + Compose plugin"
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg openssl git rsync
  install -m 0755 -d /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
  fi
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

ensure_user() {
  if ! id "${NETATLAS_USER}" >/dev/null 2>&1; then
    useradd --system --home "${NETATLAS_HOME}" --shell /usr/sbin/nologin "${NETATLAS_USER}"
    log "Created system user ${NETATLAS_USER}"
  fi
  usermod -aG docker "${NETATLAS_USER}" || true
}

git_na() {
  git -c "safe.directory=${NETATLAS_HOME}" "$@"
}

prepare_dirs() {
  if [[ -d "${NETATLAS_HOME}/.git" ]]; then
    log "Existing install detected — syncing ${BRANCH} (data/.env preserved)"
    git_na -C "${NETATLAS_HOME}" remote set-url origin "${REPO_URL}" 2>/dev/null || true
    git_na -C "${NETATLAS_HOME}" fetch --depth 1 origin "${BRANCH}"
    git_na -C "${NETATLAS_HOME}" checkout -B "${BRANCH}" "FETCH_HEAD"
    git_na -C "${NETATLAS_HOME}" reset --hard "FETCH_HEAD"
  elif [[ -f "${PWD}/docker-compose.yml" && "${PWD}" != "${NETATLAS_HOME}" ]]; then
    log "Using local repository copy at ${PWD}"
    mkdir -p "${NETATLAS_HOME}"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude .git "${PWD}/" "${NETATLAS_HOME}/"
    else
      cp -a "${PWD}/." "${NETATLAS_HOME}/"
    fi
    # Prefer a real git remote so update.sh works later
    if [[ -d "${PWD}/.git" ]]; then
      git_na -C "${NETATLAS_HOME}" init
      git_na -C "${NETATLAS_HOME}" remote add origin "${REPO_URL}" 2>/dev/null \
        || git_na -C "${NETATLAS_HOME}" remote set-url origin "${REPO_URL}"
      git_na -C "${NETATLAS_HOME}" fetch --depth 1 origin "${BRANCH}"
      git_na -C "${NETATLAS_HOME}" checkout -B "${BRANCH}" "FETCH_HEAD"
    fi
  else
    if [[ -d "${NETATLAS_HOME}" && ! -f "${NETATLAS_HOME}/docker-compose.yml" ]]; then
      log "Removing incomplete install directory at ${NETATLAS_HOME}"
      local preserve
      preserve="$(mktemp -d /tmp/netatlas-preserve.XXXXXX)"
      for item in data logs .env deploy/certs; do
        if [[ -e "${NETATLAS_HOME}/${item}" ]]; then
          mkdir -p "$(dirname "${preserve}/${item}")"
          mv "${NETATLAS_HOME}/${item}" "${preserve}/${item}"
        fi
      done
      rm -rf "${NETATLAS_HOME}"
      git_na clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${NETATLAS_HOME}"
      for item in data logs .env deploy/certs; do
        if [[ -e "${preserve}/${item}" ]]; then
          mkdir -p "$(dirname "${NETATLAS_HOME}/${item}")"
          rm -rf "${NETATLAS_HOME}/${item}"
          mv "${preserve}/${item}" "${NETATLAS_HOME}/${item}"
        fi
      done
      rm -rf "${preserve}"
    elif [[ -f "${NETATLAS_HOME}/docker-compose.yml" ]]; then
      log "Repository files present without .git — continuing"
    else
      log "Cloning ${REPO_URL} (${BRANCH}) → ${NETATLAS_HOME}"
      git_na clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${NETATLAS_HOME}"
    fi
  fi
  mkdir -p "${NETATLAS_HOME}"/{deploy/certs,data,logs}
  chmod 0755 "${NETATLAS_HOME}/install.sh" "${NETATLAS_HOME}/update.sh" 2>/dev/null || true
  chown -R "${NETATLAS_USER}:${NETATLAS_USER}" "${NETATLAS_HOME}"
}

generate_secrets() {
  local env_file="${NETATLAS_HOME}/.env"
  local cert_dir="${NETATLAS_HOME}/deploy/certs"
  mkdir -p "${cert_dir}"

  if [[ ! -f "${cert_dir}/privkey.pem" || ! -f "${cert_dir}/fullchain.pem" ]]; then
    log "Generating self-signed TLS certificate"
    openssl req -x509 -nodes -newkey rsa:4096 -days 825 \
      -keyout "${cert_dir}/privkey.pem" \
      -out "${cert_dir}/fullchain.pem" \
      -subj "/CN=netatlas.local/O=NetAtlas/C=XX"
  fi

  if [[ ! -f "${env_file}" ]]; then
    log "Generating .env secrets"
    local master_key postgres_password rabbitmq_password admin_password
    master_key="$(openssl rand -base64 32)"
    postgres_password="$(openssl rand -hex 24)"
    rabbitmq_password="$(openssl rand -hex 24)"
    admin_password="$(openssl rand -base64 18)"

    openssl genrsa -out "${NETATLAS_HOME}/deploy/certs/jwt_private.pem" 2048
    openssl rsa -in "${NETATLAS_HOME}/deploy/certs/jwt_private.pem" -pubout -out "${NETATLAS_HOME}/deploy/certs/jwt_public.pem"
    local jwt_private jwt_public
    jwt_private="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' "${NETATLAS_HOME}/deploy/certs/jwt_private.pem")"
    jwt_public="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' "${NETATLAS_HOME}/deploy/certs/jwt_public.pem")"
    local ver
    ver="$(tr -d '[:space:]' < "${NETATLAS_HOME}/VERSION" 2>/dev/null || echo "1.3.4")"

    cat > "${env_file}" <<EOF
NETATLAS_ENVIRONMENT=production
NETATLAS_DEBUG=false
NETATLAS_VERSION=${ver}
POSTGRES_PASSWORD=${postgres_password}
RABBITMQ_PASSWORD=${rabbitmq_password}
NETATLAS_MASTER_KEY_B64=${master_key}
NETATLAS_JWT_PRIVATE_KEY_PEM="${jwt_private}"
NETATLAS_JWT_PUBLIC_KEY_PEM="${jwt_public}"
NETATLAS_BOOTSTRAP_ADMIN_USERNAME=admin
NETATLAS_BOOTSTRAP_ADMIN_PASSWORD=${admin_password}
NETATLAS_BOOTSTRAP_ADMIN_EMAIL=admin@netatlas.local
NETATLAS_TLS_DIR=${cert_dir}
NETATLAS_HTTPS_PORT=443
NETATLAS_HTTP_PORT=80
EOF
    chmod 600 "${env_file}"
    printf '%s\n' "${admin_password}" > "${NETATLAS_HOME}/logs/initial_admin_password.txt"
    chmod 600 "${NETATLAS_HOME}/logs/initial_admin_password.txt"
    log "Initial admin password stored in ${NETATLAS_HOME}/logs/initial_admin_password.txt"
  else
    log "Keeping existing .env"
  fi
  chown -R "${NETATLAS_USER}:${NETATLAS_USER}" "${NETATLAS_HOME}"
}

main() {
  require_root
  check_ubuntu
  install_docker
  ensure_user
  prepare_dirs
  generate_secrets

  # shellcheck disable=SC1091
  source "${NETATLAS_HOME}/deploy/common.sh"

  # Bring up infra first so API healthchecks can pass
  cd "${NETATLAS_HOME}"
  log "Starting data plane (postgres/redis/rabbitmq)…"
  docker compose up -d postgres redis rabbitmq
  sleep 5

  rebuild_stack
  systemctl start netatlas.service || true
  wait_healthy 80
  verify_ui
  print_summary
  log "First login: admin / password from logs/initial_admin_password.txt"
  log "Then: Учётные данные → SNMPv2 community → Назначить всем → Discovery"
}

main "$@"
