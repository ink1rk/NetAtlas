# Device Intelligence

NetAtlas treats each device as the primary digital-twin object for daily NOC work.

## Identity

| Field | Source |
|-------|--------|
| hostname | discovery / SNMP / SSH |
| vendor, model, serial, firmware | inventory collectors |
| management IP / MAC | discovery identity |
| platform | fingerprint + collector |

## Role

Roles: `core`, `distribution`, `access`, `firewall`, `router`, `server`, `storage`, `wireless`, `unknown`.

Auto-detection (`RoleDetector`) scores topology/inventory signals:

- many VLANs + trunks + uplinks + ≥10G → **CORE**
- many access ports + FDB entries → **ACCESS**
- firewall platform / WAN hints → **FIREWALL**
- hypervisor / server OS → **SERVER**
- wireless AP patterns → **WIRELESS**

Result stored on the device:

- `network_role`
- `role_confidence` (0–100)
- `role_reasons[]`
- `role_source` (`auto` | `manual`)

## Metadata

`location`, `rack`, `owner`, `criticality`, `description` — editable via API without wiping discovery identity.

## Relationships

Inspector and intelligence API surface:

- interfaces
- LLDP/CDP neighbors
- VLAN membership
- inferred cable/path hops

## UI

- **Map-first**: select a node → Inspector drawer (no full-page navigation)
- Overview shows role badge, confidence, reasons, identity, metadata
- **Detect role** recomputes heuristics for one device
- History tab → audit/lifecycle (`Created` / `First seen` / `Last seen` / changes)

## API

| Method | Path |
|--------|------|
| GET | `/api/v1/devices/{id}/intelligence` |
| POST | `/api/v1/devices/{id}/role/detect` |
| PATCH | `/api/v1/devices/{id}/role` |
| POST | `/api/v1/devices/roles/detect-all` |
| PATCH | `/api/v1/devices/{id}/metadata` |
