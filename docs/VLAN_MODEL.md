# VLAN Model

VLAN Intelligence aggregates per-VLAN operational context for the digital twin.

## Object fields

| Field | Description |
|-------|-------------|
| vlan_id | Numeric VLAN ID |
| name | Name from device / vlan_objects |
| description | Free-text |
| networks | Related prefixes when known |
| active ports | Interfaces carrying the VLAN |
| devices | Devices that participate |
| topology_path | Role path (e.g. Core → Access) |

## Persistence

- Existing `vlans` / interface VLAN associations remain the discovery source
- Additive `vlan_objects` table holds curated metadata without wiping discovered rows

## UI

NOC workspace **VLANs** (`?ws=vlans&vlan=120`):

- list with device counts
- detail: name, path, member devices → click opens Inspector / map focus

## API

| Method | Path |
|--------|------|
| GET | `/api/v1/vlans` |
| GET | `/api/v1/vlans/{vlan_id}` |

Global search also returns VLAN hits for numeric IDs and names.
