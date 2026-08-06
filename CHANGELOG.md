# Changelog

All notable changes to NetAtlas are documented in this file.

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
