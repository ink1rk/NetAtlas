#!/usr/bin/env bash
# NetAtlas one-command installer for Ubuntu 22.04 / 24.04
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
  apt-get install -y ca-certificates curl gnupg openssl git
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

prepare_dirs() {
  # Runtime dirs created AFTER the repo is in place. Creating them first made
  # /opt/netatlas non-empty and broke `git clone` on first/retry installs.
  if [[ -d "${NETATLAS_HOME}/.git" ]]; then
    log "Updating existing repository at ${NETATLAS_HOME}"
    git -C "${NETATLAS_HOME}" fetch --depth 1 origin "${BRANCH}"
    git -C "${NETATLAS_HOME}" checkout -B "${BRANCH}" "FETCH_HEAD"
  elif [[ -f "${PWD}/docker-compose.yml" ]]; then
    log "Using local repository copy at ${PWD}"
    mkdir -p "${NETATLAS_HOME}"
    if command -v rsync >/dev/null 2>&1; then
      rsync -a --exclude .git "${PWD}/" "${NETATLAS_HOME}/"
    else
      cp -a "${PWD}/." "${NETATLAS_HOME}/"
    fi
  else
    if [[ -d "${NETATLAS_HOME}" ]]; then
      if [[ -f "${NETATLAS_HOME}/docker-compose.yml" ]]; then
        log "Repository files present without .git; continuing"
      else
        log "Removing incomplete install directory at ${NETATLAS_HOME}"
        # Preserve any secrets/data from a partial previous run
        local preserve
        preserve="$(mktemp -d /tmp/netatlas-preserve.XXXXXX)"
        for item in data logs .env deploy/certs; do
          if [[ -e "${NETATLAS_HOME}/${item}" ]]; then
            mkdir -p "$(dirname "${preserve}/${item}")"
            mv "${NETATLAS_HOME}/${item}" "${preserve}/${item}"
          fi
        done
        rm -rf "${NETATLAS_HOME}"
        git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${NETATLAS_HOME}"
        for item in data logs .env deploy/certs; do
          if [[ -e "${preserve}/${item}" ]]; then
            mkdir -p "$(dirname "${NETATLAS_HOME}/${item}")"
            rm -rf "${NETATLAS_HOME}/${item}"
            mv "${preserve}/${item}" "${NETATLAS_HOME}/${item}"
          fi
        done
        rm -rf "${preserve}"
      fi
    else
      git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${NETATLAS_HOME}"
    fi
  fi
  mkdir -p "${NETATLAS_HOME}"/{deploy/certs,data,logs}
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

    # Generate JWT RS256 keypair
    openssl genrsa -out "${NETATLAS_HOME}/deploy/certs/jwt_private.pem" 2048
    openssl rsa -in "${NETATLAS_HOME}/deploy/certs/jwt_private.pem" -pubout -out "${NETATLAS_HOME}/deploy/certs/jwt_public.pem"
    local jwt_private jwt_public
    jwt_private="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' "${NETATLAS_HOME}/deploy/certs/jwt_private.pem")"
    jwt_public="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' "${NETATLAS_HOME}/deploy/certs/jwt_public.pem")"

    cat > "${env_file}" <<EOF
NETATLAS_ENVIRONMENT=production
NETATLAS_DEBUG=false
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
  fi
  chown -R "${NETATLAS_USER}:${NETATLAS_USER}" "${NETATLAS_HOME}"
}

install_systemd() {
  cp "${NETATLAS_HOME}/deploy/systemd/netatlas.service" /etc/systemd/system/netatlas.service
  systemctl daemon-reload
  systemctl enable netatlas.service
}

start_stack() {
  cd "${NETATLAS_HOME}"
  log "Building and starting containers"
  # Prefer local builds; do not let a stale GHCR :1.0.0 tag hide local UI fixes
  docker compose build --pull
  docker compose up -d --force-recreate
}

wait_health() {
  log "Waiting for API health"
  local i
  for i in $(seq 1 60); do
    if curl -kfsS "https://127.0.0.1/api/v1/healthz" >/dev/null 2>&1 \
      || curl -fsS "http://127.0.0.1:8000/api/v1/healthz" >/dev/null 2>&1; then
      log "Health check passed"
      return 0
    fi
    sleep 5
  done
  die "Health check failed. Inspect: docker compose -f ${NETATLAS_HOME}/docker-compose.yml logs"
}

main() {
  require_root
  check_ubuntu
  install_docker
  ensure_user
  prepare_dirs
  generate_secrets
  install_systemd
  start_stack
  systemctl start netatlas.service || true
  wait_health
  log "NetAtlas installed at ${NETATLAS_HOME}"
  log "Open https://<server-ip>/ and login as admin"
  log "Change the bootstrap password immediately after first login"
}

main "$@"
