# Onboard Observability Server

**Module:** NetAtlas Observability (Syslog + SMTP + Triggers + Partial SIEM)  
**Mode:** Local / self-hosted / offline-first  
**Principle:** Same security bar as the rest of NetAtlas — no device writes, secrets encrypted, auditable.

## Why onboard

Network estate (Eltex, Mikrotik, UniFi, Ideco, Proxmox, vSphere, Kyocera) should send logs and raise conditions **to NetAtlas itself**, without depending on an external SIEM/Zabbix cloud.

```
Devices ──syslog UDP/TCP──► NetAtlas Syslog Receiver
Metrics / discovery ───────► Trigger Engine (Zabbix-like)
Trigger PROBLEM/OK ────────► SMTP + in-app alerts
Syslog + triggers ─────────► Partial SIEM (normalize, search, correlate)
```

## Capabilities (v1)

| Capability | Scope |
|------------|--------|
| **Syslog server** | RFC5424 / RFC3164 ingest on UDP/TCP `:514` (and optional TLS later) |
| **SMTP** | Outbound mail for PROBLEM/OK / security alerts (local MTA or relay) |
| **Triggers** | Threshold / expression / syslog-match rules with severity, hysteresis, recovery |
| **Partial SIEM** | Normalize events, store, search, simple correlation rules, MITRE-ish tags optional |

Non-goals for v1: full SOAR, packet capture, ML UEBA, replacing Elastic/Wazuh wholesale.

## Trigger model (Zabbix-inspired)

- **Trigger** has: name, severity, expression, recovery expression, enabled, ok_event_closes  
- **Expression kinds:**
  - `metric_threshold` — e.g. `cpu_percent > 90 for 5m`
  - `interface_status` — oper_status down
  - `syslog_match` — regex on facility/severity/message
  - `absence` — no heartbeat / no syslog from host for N minutes
  - `siem_correlation` — N matching events in window
- States: `ok` → `problem` → `ok` (with PROBLEM/OK events)
- Actions: create alert, SMTP notify, optional webhook (local only)

## Syslog pipeline

1. Receive datagram/stream  
2. Parse RFC3164/5424  
3. Resolve device by source IP → `device_id` when known  
4. Normalize → `observability_events`  
5. Fan-out: persist, evaluate syslog triggers, SIEM correlators  

## SMTP

Outbound only in v1:

- Settings in encrypted credential profile `protocol=smtp` or env `NETATLAS_SMTP_*`  
- Templates for PROBLEM / OK / security  
- Rate-limit digests to avoid storms  

## Data retention

- Raw syslog: configurable TTL (default 30 days)  
- Trigger events / alerts: 365 days  
- Maintenance job purges expired rows  

## Deployment

Compose service `syslog` (+ shared API DB).  
Host ports: `514/udp`, `514/tcp`.  
API remains on HTTPS via Nginx; syslog is not proxied through Nginx.
