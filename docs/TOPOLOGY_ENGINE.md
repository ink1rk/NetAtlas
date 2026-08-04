# Topology Engine

Interactive network map powered by Cytoscape.js inside the NOC workspace (~80% canvas / ~20% inspector).

## Hierarchical layout

Discovery/role enrichment feeds a layered layout:

```
Internet / Edge
      ↓
  Firewall
      ↓
    Core
      ↓
 Distribution
      ↓
   Access
      ↓
 Servers / Clients
```

Backend: `GET /api/v1/topology/graph` includes `layout.nodes` with `rank`, `column`, `layer`.  
Frontend: preset positions via `Topology.applyHierarchy` / `applyHierarchicalLayout`.

## Interactions

| Action | Behavior |
|--------|----------|
| Zoom / pan | Cytoscape wheel + drag |
| Hierarchy | Re-apply role ranks |
| Group | Compound nodes by role |
| Collapse / expand | Hide/show role groups |
| Focus mode | Dim graph; highlight 1-hop neighborhood |
| Path highlight | Dim graph; emphasize hop chain (Trace Path / MAC Trace) |
| Context menu | Open / Locate / Trace / Interfaces / History / Export |

## Clustering / grouping

`Topology.groupByRole()` creates compound parent nodes (`role-group`). Collapse dims or hides children for dense maps.

## API

| Method | Path |
|--------|------|
| GET | `/api/v1/topology/graph` |
| GET | `/api/v1/topology/layout` |
| GET | `/api/v1/topology/cable-path` |
