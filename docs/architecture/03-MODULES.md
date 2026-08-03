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
| `cisco_ios` | Cisco IOS | SNMP, SSH (show-only) |
| `mikrotik` | RouterOS | SNMP, SSH/API read |
| `eltex` | Eltex | SNMP, SSH |
| `linux` | Linux | SNMP, SSH |
| `windows` | Windows | SNMP, WMI-read via SSH when available |
| `esxi` | VMware ESXi | HTTPS API read |
| `docker_host` | Docker | Docker API unix/tcp read |
| `generic_snmp` | fallback | SNMP |

Discovery fallback chain for neighbors: **LLDP/CDP → FDB → ARP**.

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
