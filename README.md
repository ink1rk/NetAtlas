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

- Automatic discovery via ICMP, SNMPv2/v3, SSH (allow-listed show/read commands), vendor APIs (UniFi/Proxmox/vSphere), LLDP, FDB, ARP
- Stack-first inventory for Eltex, Mikrotik, UniFi, Proxmox, vSphere/ESXi, Ideco, Kyocera
- Onboard observability: Syslog server, SMTP alerts, Zabbix-like triggers, partial SIEM
- Interactive topology (Cytoscape) with interface-level links, speed, LACP, VLAN, trunk
- Cable path visualization between endpoints
- Immutable snapshots after every discovery + diff
- IPAM with used/free/conflict tracking
- Monitoring metrics (CPU, RAM, temperature, interface counters; toner for printers)
- Export: Draw.io, Visio (VSDX), SVG, PNG, PDF, JSON, GraphML
- Offline-first UI (no CDN), HTTPS-only edge, JWT + RBAC, AES-256-GCM secrets vault

## Quick install (Ubuntu 22.04 / 24.04)

```bash
curl -fsSL https://raw.githubusercontent.com/ink1rk/NetAtlas/main/install.sh | sudo bash
```

Or from a clone:

```bash
sudo ./install.sh
```

Open `https://<server>/` and sign in as `admin`. The initial password is written to `/opt/netatlas/logs/initial_admin_password.txt`.

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
