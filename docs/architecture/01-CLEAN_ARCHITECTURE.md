# Clean / Hexagonal Architecture

## Layer Map

```
┌──────────────────────────────────────────────────────────────┐
│ Presentation (API / WebSocket / Static UI)                   │
│  FastAPI routers, schemas, WS hubs, Jinja/static frontend    │
└───────────────────────────┬──────────────────────────────────┘
                            │ DTOs / Commands / Queries
┌───────────────────────────▼──────────────────────────────────┐
│ Application (Use Cases)                                      │
│  DiscoveryJobRunner, SnapshotComparer, TopologyQuery,        │
│  IpamAllocatorView, ExportService, AuthService               │
└───────────────────────────┬──────────────────────────────────┘
                            │ Domain Ports (interfaces)
┌───────────────────────────▼──────────────────────────────────┐
│ Domain                                                       │
│  Aggregates: Device, Interface, Link, Subnet, Snapshot,      │
│  CredentialVaultRef, DiscoverySeed, AuditEvent               │
│  Domain services: TopologyBuilder, CablePathResolver,        │
│  ConflictDetector, ReadOnlyGuard                             │
└───────────────────────────┬──────────────────────────────────┘
                            │ Port implementations
┌───────────────────────────▼──────────────────────────────────┐
│ Infrastructure Adapters                                      │
│  SQLAlchemy repos, Celery tasks, Redis cache, RabbitMQ,      │
│  AES vault, SNMP/SSH/ICMP collectors, ESXi/Docker adapters   │
└──────────────────────────────────────────────────────────────┘
```

## Dependency Rule

Inner layers never import outer layers.  
Domain has **zero** FastAPI / SQLAlchemy / pysnmp imports.

## Ports (examples)

| Port | Direction | Purpose |
|------|-----------|---------|
| `DeviceRepository` | driven | Persist/load devices |
| `SnapshotRepository` | driven | Snapshot CRUD |
| `SecretVault` | driven | Encrypt/decrypt credentials |
| `CollectorPlugin` | driven | Read device facts |
| `MessageBus` | driven | Publish discovery events |
| `Clock` / `IdGenerator` | driven | Testable time/IDs |
| `AuditLogger` | driven | Immutable audit trail |

## Plugin Architecture

Collectors implement:

```python
class CollectorPlugin(Protocol):
    vendor: str
    platforms: frozenset[str]

    def supports(self, fingerprint: DeviceFingerprint) -> bool: ...
    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts: ...
    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]: ...
    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]: ...
    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]: ...
    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample: ...
```

Registry discovers entry points under `netatlas.collectors`.

## Read-Only Guard

`CollectorContext` exposes only **GET/READ** transport methods:

- SNMP GET / WALK  
- SSH `exec` against an allow-listed command catalog  
- ICMP echo  
- HTTPS GET for vendor APIs (ESXi, Docker)  

Any attempt to call a write path raises `WriteOperationForbiddenError` and is audited.

## DI

Composition root: `backend/src/netatlas/bootstrap.py`  
Wiring: dependency-injector or FastAPI `Depends` factories registered once at startup.
