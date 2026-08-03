# NetAtlas Architecture Overview

**Product:** NetAtlas  
**Version:** 1.0 MVP (Read-Only)  
**Classification:** Enterprise / Critical Infrastructure  

## Mission

NetAtlas is a self-hosted, offline-first platform for autonomous network discovery, inventory, topology mapping, cable-path visualization, IPAM, snapshot/diff, and monitoring. The MVP is strictly **read-only**: the system never modifies device configuration.

## Non-Goals (MVP)

- Device configuration (CLI write, SNMP SET, API mutate)
- Cloud SaaS dependencies, CDN, telemetry, analytics
- Manual topology editing
- Multi-tenant SaaS isolation (single enterprise deployment)

## Design Mandates

| Principle | Application |
|-----------|-------------|
| Clean Architecture | Domain independent of frameworks |
| Hexagonal (Ports & Adapters) | Collectors, DB, MQ, crypto are adapters |
| DDD | Bounded contexts with explicit aggregates |
| SOLID | Plugin collectors, DI containers |
| Repository Pattern | Persistence behind interfaces |
| Offline-first | All assets served locally |
| Secrets never in plaintext | AES-256-GCM at rest |
| Fail closed | Unknown protocol ops rejected |

## Bounded Contexts

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Identity &      │  │ Discovery       │  │ Inventory       │
│ Access (IAM)    │  │ Orchestration   │  │ (Devices)       │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
┌────────┴────────┐  ┌────────┴────────┐  ┌────────┴────────┐
│ Topology &      │  │ Snapshot &      │  │ IPAM            │
│ Cable Paths     │  │ Diff            │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
┌────────┴────────┐  ┌────────┴────────┐  ┌────────┴────────┐
│ Monitoring      │  │ Export          │  │ Audit &         │
│ Telemetry       │  │                 │  │ Compliance      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Technology Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, Pydantic v2, WebSocket |
| Workers | Celery, Redis, RabbitMQ |
| DB | PostgreSQL 16, SQLAlchemy 2, Alembic |
| Frontend | Bootstrap 5 (local), Cytoscape.js, Chart.js |
| Edge | Nginx (TLS termination) |
| Runtime | Docker Compose, systemd installer |
| Crypto | AES-256-GCM, JWT (RS256), Argon2id |

## Quality Gates (every module)

1. Compiles / type-checks  
2. Unit tests  
3. Structured logging  
4. Typed error handling  
5. Health check endpoint or probe  
6. Module documentation  

## Delivery Phases

1. **Architecture** (this package) — diagrams, ER, OpenAPI, modules  
2. **Foundation** — IAM, persistence, DI, plugin loader, health  
3. **Discovery core** — ICMP/SNMP/SSH read collectors + graph builder  
4. **Snapshot / Diff / IPAM / Monitoring read APIs**  
5. **Frontend** — dark adaptive UI, topology, search  
6. **Deploy** — compose, install.sh, CI/CD, GHCR  

Each phase ends with a green test suite and a git commit.
