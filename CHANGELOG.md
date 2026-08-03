# Changelog

All notable changes to NetAtlas are documented in this file.

## [1.0.0] - 2026-08-03

### Added

- Architecture baseline (Clean/Hexagonal, ER, OpenAPI, ADRs)
- FastAPI backend with JWT/RBAC, AES-256-GCM credential vault
- Read-only collectors: Cisco IOS, Mikrotik, Eltex, Linux, Windows, ESXi, Docker, generic SNMP
- Discovery orchestration with LLDP/CDP → FDB → ARP fallback
- Automatic snapshots after discovery and snapshot diff
- Topology graph + cable path APIs
- IPAM prefixes, usage, conflicts
- Export: JSON, GraphML, SVG, PNG, PDF, Draw.io, Visio VSDX
- Dark offline-first Bootstrap/Cytoscape/Chart.js frontend
- Docker Compose stack, Nginx TLS, systemd unit, `install.sh`
- GitHub Actions CI and GHCR image publish
