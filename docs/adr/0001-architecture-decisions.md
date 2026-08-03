# ADR Index

| ID | Title | Status |
|----|-------|--------|
| ADR-0001 | Hexagonal Clean Architecture | Accepted |
| ADR-0002 | Read-only collectors | Accepted |
| ADR-0003 | PostgreSQL as system of record | Accepted |
| ADR-0004 | AES-256-GCM credential vault | Accepted |
| ADR-0005 | Offline-first frontend packaging | Accepted |
| ADR-0006 | Neighbor fallback LLDP→FDB→ARP | Accepted |

## ADR-0001 — Hexagonal Clean Architecture

**Context:** Enterprise longevity and testability.  
**Decision:** Domain/application independent of FastAPI/SQLAlchemy; adapters at edges.  
**Consequences:** Slightly more boilerplate; high isolation and pluginability.

## ADR-0002 — Read-only collectors

**Context:** Critical infrastructure risk.  
**Decision:** Hard-block SNMP SET and SSH mutate patterns in transport adapters.  
**Consequences:** No config automation in MVP; safety by design.

## ADR-0003 — PostgreSQL as system of record

**Context:** Relational inventory + IPAM + audit.  
**Decision:** PostgreSQL 16 with SQLAlchemy 2 + Alembic.  
**Consequences:** Strong consistency; operational familiarity.

## ADR-0004 — AES-256-GCM credential vault

**Context:** SNMP/SSH secrets at rest.  
**Decision:** Application-level AES-256-GCM with versioned master key.  
**Consequences:** Must manage key backup; DB dumps alone are insufficient to steal creds.

## ADR-0005 — Offline-first frontend

**Context:** Air-gapped enterprise networks.  
**Decision:** Vendor Bootstrap/Cytoscape/Chart.js into repo; no CDN.  
**Consequences:** Larger repo; reproducible UI offline.

## ADR-0006 — Neighbor fallback chain

**Context:** Incomplete LLDP deployments.  
**Decision:** Prefer LLDP/CDP; else FDB correlation; else ARP.  
**Consequences:** Links may have confidence < 1.0; UI must show method/confidence.
