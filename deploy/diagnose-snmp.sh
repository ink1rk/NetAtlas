#!/usr/bin/env bash
# Run ON the NetAtlas host (as a user with sudo):
#   curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/deploy/diagnose-snmp.sh | sudo bash
# Optional: TARGET_IP=10.116.111.171 COMMUNITY=public bash ...
set -euo pipefail

TARGET_IP="${TARGET_IP:-10.116.111.171}"
COMMUNITY="${COMMUNITY:-public}"
INSTALL_DIR="${INSTALL_DIR:-/opt/netatlas}"
API="${API:-https://127.0.0.1/api/v1}"

section() { echo; echo "======== $* ========"; }

section "Host"
hostname; date -Is; whoami
ip -4 addr show 2>/dev/null | sed -n 's/.*inet //p' | head -10 || true

section "Update NetAtlas to latest main (1.3.8+)"
if [[ -x /usr/local/bin/netatlas-update ]]; then
  /usr/local/bin/netatlas-update || true
elif [[ -f "$INSTALL_DIR/update.sh" ]]; then
  bash "$INSTALL_DIR/update.sh" || true
else
  curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/update.sh | bash || true
fi

section "Status / versions"
if command -v netatlas-status >/dev/null 2>&1; then
  netatlas-status || true
fi
if [[ -f "$INSTALL_DIR/VERSION" ]]; then
  echo "VERSION file: $(cat "$INSTALL_DIR/VERSION")"
fi
cd "$INSTALL_DIR" 2>/dev/null || cd /opt/netatlas 2>/dev/null || true
docker compose ps 2>/dev/null || docker-compose ps 2>/dev/null || true

section "pysnmp / pyasn1 inside API container"
API_CID="$(docker ps --format '{{.ID}} {{.Names}}' | awk '/api|netatlas-api/{print $1; exit}')"
if [[ -z "${API_CID:-}" ]]; then
  echo "ERROR: api container not found"
else
  echo "api container: $API_CID"
  docker exec "$API_CID" python - <<'PY' || true
import importlib.metadata as m
pkgs = ["pysnmp", "pysnmp-lextudio", "pyasn1"]
for p in pkgs:
    try:
        print(f"{p}={m.version(p)}")
    except Exception as e:
        print(f"{p}=MISSING ({e})")
try:
    from netatlas.infrastructure.collectors.base.snmp_transport import check_pysnmp, SnmpTransport
    import asyncio
    print("check_pysnmp:", check_pysnmp())
except Exception as e:
    print("check_pysnmp FAILED:", e)
PY
fi

section "SNMP from host to ${TARGET_IP}"
if command -v snmpget >/dev/null 2>&1; then
  snmpget -v2c -c "$COMMUNITY" -t 2 -r 1 "$TARGET_IP" 1.3.6.1.2.1.1.1.0 || echo "host snmpget FAILED"
else
  echo "snmpget not installed on host — trying from API container"
fi

section "SNMP from API container to ${TARGET_IP}"
if [[ -n "${API_CID:-}" ]]; then
  docker exec -e TARGET_IP="$TARGET_IP" -e COMMUNITY="$COMMUNITY" "$API_CID" python - <<'PY' || true
import asyncio, os, time
from netatlas.infrastructure.collectors.base.snmp_transport import SnmpTransport, get_last_snmp_error, check_pysnmp
print("lib:", check_pysnmp())
host = os.environ["TARGET_IP"]
community = os.environ.get("COMMUNITY", "public")
async def main():
    t = SnmpTransport()
    t0 = time.time()
    v = await t.get(host, "1.3.6.1.2.1.1.1.0", community=community, version=2, timeout=3.0)
    print(f"elapsed={time.time()-t0:.3f}s sysDescr={v!r}")
    print("last_error:", get_last_snmp_error())
    if v:
        cpu = await t.get(host, "1.3.6.1.4.1.14988.1.1.3.11.0", community=community, version=2, timeout=3.0)
        mem = await t.get(host, "1.3.6.1.4.1.14988.1.1.3.12.0", community=community, version=2, timeout=3.0)
        print(f"mtxrHlProcessorLoad={cpu!r} mtxrHlMemoryUsage={mem!r}")
asyncio.run(main())
PY
fi

section "Collect metrics via local API"
# Try default admin if .env has it; otherwise use JWT from compose env is hard — call collect-now with login.
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-}"
if [[ -z "$ADMIN_PASS" && -f "$INSTALL_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  set +u
  # common keys
  ADMIN_PASS="$(grep -E '^NETATLAS_ADMIN_PASSWORD=' "$INSTALL_DIR/.env" | head -1 | cut -d= -f2- | tr -d '"' || true)"
  set -u
fi
if [[ -n "$ADMIN_PASS" ]]; then
  TOK="$(curl -sk -X POST "$API/auth/login" -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null || true)"
  if [[ -n "$TOK" ]]; then
    echo "Login OK as $ADMIN_USER"
    echo "--- collect-now ---"
    curl -sk -X POST "$API/monitoring/collect-now" -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{}' | python3 -m json.tool || true
    echo "--- fleet sample ---"
    curl -sk "$API/monitoring/fleet-metrics?limit=20" -H "Authorization: Bearer $TOK" | python3 -m json.tool | head -120 || true
    echo "--- recent poll logs ---"
    curl -sk "$API/monitoring/poll-logs?limit=15" -H "Authorization: Bearer $TOK" | python3 -m json.tool | head -160 || true
  else
    echo "Login failed — set ADMIN_PASS=... and re-run"
  fi
else
  echo "ADMIN_PASS not set. Re-run with: ADMIN_PASS='your-admin' sudo -E bash $0"
fi

section "Done"
echo "Paste this entire output back to the agent."
