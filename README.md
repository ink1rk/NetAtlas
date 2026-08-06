# NetAtlas

Enterprise self-hosted platform for autonomous network discovery, inventory, interactive topology, cable paths, IPAM, snapshots/diff, and monitoring.

**MVP is strictly read-only.** NetAtlas never modifies device configuration.

## Supported device stack (this deployment)

Primary:

- Eltex (MES/ESR)
- Mikrotik RouterOS
- UniFi (Ubiquiti)
- Proxmox VE
- VMware vSphere / ESXi
- Ideco UTM
- Kyocera printers/MFP

Optional/legacy collectors exist (e.g. Cisco IOS, generic Linux/Windows/Docker) but are not part of the target estate.

See [`docs/architecture/09-TARGET_STACK.md`](docs/architecture/09-TARGET_STACK.md).

## Features

- **Digital Twin NOC workspace** — map-first canvas + inspector drawer (no page jumps for selection)
- **Device Intelligence** — identity, auto role detection (Core/Access/Firewall/…), metadata, relationships
- **MAC Trace / Find Device** — locate endpoints by MAC, IP, or hostname with path highlighting
- **VLAN Intelligence** — VLAN list/detail with member devices and topology path
- Automatic discovery via ICMP, SNMPv2/v3, SSH (allow-listed show/read commands), vendor APIs (UniFi/Proxmox/vSphere), LLDP, FDB, ARP
- Discovery Wizard with Fast / Deep / Topology scan modes
- Hierarchical Cytoscape topology (Firewall → Core → Distribution → Access) with grouping and path highlight
- Cable Map mode (patch-panel model ready; paths inferred from LLDP/FDB)
- Immutable snapshots after every discovery + timeline + ADDED/REMOVED/CHANGED diff
- Global search + Ctrl+K command palette (`open device`, `find IP`, `show VLAN`, `trace MAC`)
- Object audit history (created / first seen / last seen / changes)
- Integration-ready stubs: `connectors/` (Zabbix, NetBox, CMDB) and `plugins/` hooks
- Stack-first inventory for Eltex, Mikrotik, UniFi, Proxmox, vSphere/ESXi, Ideco, Kyocera
- Onboard observability: Syslog server, SMTP alerts, Zabbix-like triggers, partial SIEM
- IPAM with used/free/conflict tracking
- Export: Draw.io, Visio (VSDX), SVG, PNG, PDF, JSON, GraphML
- Offline-first UI (no CDN), HTTPS-only edge, JWT + RBAC, AES-256-GCM secrets vault

### Product docs

- [`docs/DEVICE_INTELLIGENCE.md`](docs/DEVICE_INTELLIGENCE.md)
- [`docs/TOPOLOGY_ENGINE.md`](docs/TOPOLOGY_ENGINE.md)
- [`docs/MAC_TRACE.md`](docs/MAC_TRACE.md)
- [`docs/VLAN_MODEL.md`](docs/VLAN_MODEL.md)

## Quick install (Ubuntu 22.04 / 24.04)

```bash
curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/install.sh | sudo bash
```

Or from a clone:

```bash
sudo ./install.sh
```

Open `https://<server>/` and sign in as `admin`. The initial password is written to `/opt/netatlas/logs/initial_admin_password.txt`.

## Update existing install

```bash
curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/update.sh | sudo bash
```

Pulls `main`, rebuilds API + frontend, recreates the stack. Current release: **1.3.1**.

## Local development

```bash
cp .env.example .env
# generate NETATLAS_MASTER_KEY_B64 and JWT keys, then:
docker compose up -d --build
```

API docs: `https://localhost/api/docs`  
Health: `/api/v1/healthz` · Ready: `/api/v1/readyz`

## Architecture

See [`docs/architecture/`](docs/architecture/README.md).

## Design system

Visual source of truth: [`design/`](design/README.md) (colors, logo, mesh background, frontend guidelines).

## Security

See [`SECURITY.md`](SECURITY.md). Rotate any credentials that were ever pasted into chat or tickets.

## License

Apache-2.0 — see [`LICENSE`](LICENSE).
