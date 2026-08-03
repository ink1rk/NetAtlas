# Changelog

All notable changes to NetAtlas are documented in this file.

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
- Dark offline-first Bootstrap/Cytoscape/Chart.js frontend
- Docker Compose stack, Nginx TLS, systemd unit, `install.sh`
- GitHub Actions CI and GHCR image publish

### Changed

- Primary supported estate is Eltex/Mikrotik/UniFi/Proxmox/vSphere/Ideco/Kyocera (Cisco not required)
- See `docs/architecture/09-TARGET_STACK.md`
