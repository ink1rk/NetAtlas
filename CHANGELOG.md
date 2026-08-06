# Changelog

All notable changes to NetAtlas are documented in this file.

## [1.3.1] - 2026-08-06

### Fixed — SNMP discovery / identity enrichment

- Discovery now tries **all SNMP credential profiles** (not only those attached to the seed), so profiles created on Credentials actually authenticate MikroTik/Eltex/…
- “Assign to all devices” also attaches the profile to **all discovery seeds**
- Unknown Device path still **binds credentials** for later enrichment
- “Collect metrics now” runs **inline identity enrichment** (sysName, vendor, model, interfaces, MAC) for ICMP-only stubs
- MikroTik model parsed from `sysDescr` (e.g. `CRS354-48P-4S+2Q+`); management MAC from IF-MIB
- SNMP `NoSuchObject` / empty ENTITY `.1` no longer blocks classification

## [1.3.0] - 2026-08-06

### Added — Enterprise Analysis Platform

- **Smart Discovery persistence unlock**: FDB, ARP, LLDP/CDP neighbors and per-device VLANs
  are now written to the database on every discovery run (`/devices/{id}/{fdb,arp,neighbors}`
  previously read from tables nothing ever populated).
- **`scan_mode` is now honored**: `fast` skips adjacency collection for a quick sweep,
  `topology` collects adjacency without full VLAN/route persistence, `deep` does everything.
- **Unknown Device fallback**: hosts that answer ICMP but no collector (SNMP/SSH) can reach
  are still recorded, classified by MAC OUI + reverse DNS (`device_class`, `oui_vendor`).
- **Credential Manager rotation**: discovery now tries each attached SNMP profile in turn
  until one authenticates, and records the winning profile on the device
  (`attributes.verified_credential_profile_id`).
- **Interface-centric Link model**: `media`, `link_status`, `crc_errors`, `drops`,
  `rx/tx_utilization_pct`, SFP vendor/model/serial, optical power, temperature, voltage —
  architecture ready, populated as vendor telemetry becomes available.
- **Link Health engine** (`domain/services/LinkHealthScorer`): healthy/warning/critical based
  on interface state, duplex mismatch, CRC/drops (SNMP IF-MIB per-interface counters), optical
  power and temperature. Surfaced on `/topology/graph`, `/topology/links`, and the new
  `GET /topology/links/{id}` connection card.
- **Mikrotik Bridge View**: bridge/bridge-port/bridge-VLAN parsing (PVID, tagged/untagged,
  RSTP) via `GET /devices/{id}/bridge`.
- **Printer Discovery**: CMYK + waste toner, paper tray status, total page count, and
  Printer-MIB error flags for Kyocera (`GET /devices/{id}/printer`); printer badge + accent
  on the topology map.
- **Trace Engine expansion**: `GET /trace/device`, `GET /trace/vlan/{id}` alongside the
  existing `GET /trace/mac` (which now also traces IP/hostname).
- **VLAN Explorer polish**: tagged vs. untagged port breakdown, editable gateway/prefix
  (`PATCH /vlans/{id}`), rendered in the NOC workspace and global search.
- **Trigger pack**: Interface CRC/Drops thresholds, High Temperature, Low Toner, Paper
  Empty, Device Offline (new `device_status` trigger kind), Optical RX Low.
- OUI vendor lookup table + device-type heuristics (`infrastructure/collectors/base/oui.py`).

### Changed — Enterprise Design System v2

- Deep-navy glass shell, engineering-grid canvas, refined typography and card identity
- NOC three-panel polish (explorer / map / inspector) with hover/selection glow
- Device inspector gauges, VLAN chips, mini-topology; link-health edge colors on the map
- Asset cache-bust `rel1` across all pages

## [1.2.0] - 2026-08-06

### Added
- Credentials UI (SNMPv2/v3/SSH) + assign profiles to all devices
- Device credential attach API/UI for post-discovery monitoring
- Real metrics collection sweep (HOST-RESOURCES / IF-MIB / SNMPv2-MIB)
- MIB metrics catalog for trigger building
- Trigger create form from metric catalog
- Seed credential profile picker in Discovery Wizard

## [1.1.1] - 2026-08-06

### Fixed
- Discovery jobs no longer stick in PENDING when Celery/broker fails — inline background fallback
- Dark theme form inputs: typed text contrast (Bootstrap `data-bs-theme` + hardened controls)

### Added
- Stop / Retry discovery jobs (`POST /discovery/jobs/{id}/cancel|retry`)
- Enterprise Discovery Wizard UI with live progress

## [1.1.0] - 2026-08-04

### Added

- Device Intelligence: role detection, metadata, inspector digital-twin view
- MAC Trace / Find Device workspace + `/trace/mac`
- VLAN Intelligence views + `/vlans`
- Hierarchical topology layout, role grouping, path highlighting
- Cable Map model (`patch_panels`, `cables`) and `/cable-map`
- Discovery Wizard scan modes: fast / deep / topology
- Audit timeline / object history APIs for daily change awareness
- Command palette intelligence actions (open device, find IP, show VLAN, trace MAC)
- Integration stubs: `infrastructure/connectors/` (Zabbix, NetBox, CMDB), `plugins/` hooks
- Docs: `DEVICE_INTELLIGENCE.md`, `TOPOLOGY_ENGINE.md`, `MAC_TRACE.md`, `VLAN_MODEL.md`
- Alembic migration `0002_device_intelligence` (additive)

## [1.0.0] - 2026-08-03

### Added

- Architecture baseline (Clean/Hexagonal, ER, OpenAPI, ADRs)
- FastAPI backend with JWT/RBAC, AES-256-GCM credential vault
- Stack-first read-only collectors: Eltex, Mikrotik, UniFi, Proxmox, vSphere/ESXi, Ideco, Kyocera
- Optional collectors: Linux, Windows, Docker, Cisco IOS (legacy), generic SNMP
- Discovery orchestration with LLDP → FDB → ARP fallback
- Automatic snapshots after discovery and snapshot diff
- Topology graph + cable path APIs
- IPAM prefixes, usage, conflicts
- Export: JSON, GraphML, SVG, PNG, PDF, Draw.io, Visio VSDX
- **Onboard Observability**: Syslog UDP/TCP/TLS, SMTP + Telegram + Element alerts, Zabbix-like triggers, partial SIEM
- Ideco/Eltex-oriented default syslog trigger pack
- Visual design system (`design/`): Cyber Blue atlas theme, Inter + JetBrains Mono, topology role colors, logo/mesh assets
- Dark offline-first Bootstrap/Cytoscape/Chart.js frontend
- Docker Compose stack (incl. `syslog` service), Nginx TLS, systemd unit, `install.sh`
- GitHub Actions CI and GHCR image publish

### Changed

- Primary supported estate is Eltex/Mikrotik/UniFi/Proxmox/vSphere/Ideco/Kyocera (Cisco not required)
- See `docs/architecture/09-TARGET_STACK.md`
