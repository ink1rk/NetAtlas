# Module Catalog

## Directory Layout

```
NetAtlas/
├── backend/
│   ├── src/netatlas/
│   │   ├── domain/                 # entities, value objects, ports, errors
│   │   ├── application/            # use cases / services
│   │   ├── infrastructure/
│   │   │   ├── persistence/        # SQLAlchemy, Alembic, repositories
│   │   │   ├── messaging/          # Celery, RabbitMQ, Redis
│   │   │   ├── security/           # JWT, AES vault, RBAC
│   │   │   ├── collectors/         # SNMP, SSH, ICMP, ESXi, Docker plugins
│   │   │   └── export/             # Draw.io, GraphML, SVG, PDF, …
│   │   ├── api/                    # FastAPI routers, deps, middleware
│   │   ├── workers/                # Celery app & tasks
│   │   └── bootstrap.py
│   ├── tests/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── static/                     # bootstrap, cytoscape, chart.js (vendored)
│   ├── css/
│   ├── js/
│   ├── index.html
│   └── Dockerfile
├── deploy/
│   ├── nginx/
│   ├── systemd/
│   └── certs/                      # generated at install time
├── docs/
├── .github/workflows/
├── docker-compose.yml
├── install.sh
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── CHANGELOG.md
└── README.md
```

## Modules

### `domain`
Pure Python. Devices, interfaces, links, VLANs, prefixes, snapshots, discovery seeds. Value objects: MacAddress, IPv4Network, Speed, VlanId. Domain errors. Ports as `typing.Protocol`.

### `application`
Use cases:
- `StartDiscovery`
- `BuildTopology`
- `ResolveCablePath`
- `CreateSnapshot`
- `CompareSnapshots`
- `SearchInventory`
- `QueryIpam`
- `CollectMetrics`
- `ExportTopology`
- `AuthenticateUser` / `Authorize`

### `infrastructure.collectors`
| Plugin | Platforms | Transports |
|--------|-----------|------------|
| `eltex` | Eltex MES/ESR | SNMP, SSH show-only, LLDP, FDB |
| `mikrotik` | RouterOS | SNMP, SSH read, neighbor/ARP/bridge |
| `unifi` | UniFi gateway/switch/AP | Controller API GET, SNMP |
| `proxmox` | Proxmox VE | API token read, SSH `pvesh`, SNMP |
| `vsphere` | vSphere / ESXi | HTTPS read API, SNMP |
| `ideco` | Ideco UTM | SNMP, SSH read, ARP |
| `kyocera` | Kyocera printers | Printer-MIB SNMP |
| `linux` / `windows` / `docker_host` | helpers | SSH/SNMP/API |
| `cisco_ios` | optional legacy | SNMP, SSH show-only |
| `generic_snmp` | fallback | SNMP |

Discovery fallback chain for neighbors: **LLDP → FDB → ARP**.

### `infrastructure.persistence`
SQLAlchemy 2 mapped models, Alembic migrations, repository adapters, unit-of-work.

### `infrastructure.security`
- Argon2id passwords  
- JWT access (short) + refresh (rotating)  
- RBAC permission codes  
- AES-256-GCM credential vault with key versioning  
- Rate limiting, CSRF for cookie sessions, audit writer  

### `infrastructure.export`
Exporters implement `TopologyExporter` port: JSON, GraphML, SVG, PNG, PDF, Draw.io XML, Visio VSDX (Open Packaging).

### `api`
Versioned REST under `/api/v1`, WebSocket `/ws/discovery/{job_id}`, OpenAPI generated from Pydantic, health `/healthz` `/readyz`.

### `workers`
Celery queues: `discovery`, `metrics`, `export`, `maintenance`.

### `frontend`
SPA-like multipage Bootstrap 5 dark theme, Cytoscape topology, Chart.js metrics, offline-vendored assets only.
