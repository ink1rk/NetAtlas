# Discovery Enrichment (v1.3.0)

This document describes the "Enterprise Analysis Platform" additive changes: Smart
Discovery persistence, Credential Manager rotation, Interface-centric Link Health,
Mikrotik Bridge View, and Printer Discovery.

## 1. Smart Discovery persistence unlock

Before this change, `LldpNeighborModel`, `FdbEntryModel`, `ArpEntryModel`, `VlanModel`
and `RouteModel` existed in the schema and had working `GET` endpoints
(`/devices/{id}/{neighbors,fdb,arp,routes}`), but nothing ever wrote to them — the
discovery orchestrator only used FDB/ARP transiently, in-memory, to infer links.

`DiscoveryOrchestrator` now accepts optional writer ports:

- `NeighborRepository.replace_for_device`
- `FdbRepository.replace_for_device`
- `ArpRepository.replace_for_device`
- `VlanRepository.replace_for_device`
- `RouteRepository.replace_for_device`

Each discovery target now persists these facts as first-class inventory data — not
merely a fallback used only when LLDP/CDP is unavailable. This unlocks MAC Trace, the
VLAN Explorer, and any future SIEM/CMDB export that depends on FDB/ARP tables having
real content. Wiring lives in `workers/celery_app.py::_run_discovery`.

## 2. `scan_mode` is honored

`DiscoveryOrchestrator.run()` now reads `job.config["scan_mode"]`:

| Mode       | Inventory | Interfaces | Neighbors/FDB/ARP | VLANs/Routes |
|------------|-----------|------------|--------------------|--------------|
| `fast`     | ✅         | ✅          | ❌                  | ❌            |
| `topology` | ✅         | ✅          | ✅                  | ❌            |
| `deep`     | ✅         | ✅          | ✅                  | ✅            |

## 3. Unknown Device fallback (OUI classification)

When a target answers ICMP but no collector plugin can extract usable inventory
(closed SNMP, unmanaged appliance, IoT device, camera, phone), the orchestrator no
longer silently records a bare "generic/unknown" device. It resolves the local
kernel neighbor table (`ip neighbor show` / `arp -n`) for the target's MAC address,
looks it up in a static OUI table (`infrastructure/collectors/base/oui.py`), attempts
reverse DNS, and creates a device with `attributes.auto_classified = true`,
`attributes.oui_vendor`, and a best-guess `attributes.device_class` (printer, camera,
access_point, router, voip_phone, nas, virtual_machine, iot).

## 4. Credential Manager rotation

`infrastructure/security/credential_resolver.load_profile_candidates()` returns one
candidate credential bag per attached SNMP profile (instead of merging them all into
one, where only the last profile survives). `DiscoveryOrchestrator._fingerprint()`
tries each candidate's SNMP `sysDescr` in turn until one answers, then uses that
profile for the rest of the collection and records
`attributes.verified_credential_profile_id` on the device.

## 5. Interface-centric Link model + Link Health

`Link` (domain entity, `LinkModel` ORM) gained additive columns: `media`,
`link_status`, `crc_errors`, `drops`, `rx/tx_utilization_pct`, `sfp_vendor/model/serial`,
`rx/tx_optical_dbm`, `temperature_c`, `voltage`, `health`, `health_reasons`.

`domain/services/LinkHealthScorer` classifies a link as `healthy` / `warning` /
`critical` from interface oper-status, duplex mismatch, and per-interface SNMP
counters (`snmp_interface_counters()` in `collectors/base/snmp_inventory.py`, stored
in `DeviceMetricModel.extras.interface_counters`). Health is computed at read time
(not persisted at discovery time) so it always reflects the latest telemetry.

- `GET /topology/graph`, `GET /topology/links` — every edge/link now carries `health`
  and `health_reasons`.
- `GET /topology/links/{id}` — full interface-centric connection card (both endpoints,
  VLANs, media, health) for the "click a link → connection card" UX.

SFP vendor/model/optical power/temperature/voltage are architecturally present but
only populated when a vendor collector can supply them (no DOM/ENTITY-SENSOR data is
fabricated) — same honesty policy as the existing `temperature_c` metric-catalog entry.

## 6. Mikrotik Bridge View

`collectors/mikrotik/plugin.py` now also runs (read-only):

- `/interface vlan print detail` → per-device VLANs
- `/interface bridge print detail` → bridge name, RSTP mode, VLAN filtering
- `/interface bridge port print detail` → PVID / horizon per port
- `/interface bridge vlan print detail` → tagged/untagged port sets per VLAN
- `/ip route print detail` → routing table facts
- `/system clock print` → timezone

Bridge data is stored in `device.attributes.bridge` and exposed via
`GET /devices/{id}/bridge`. Bridge port PVID/tagged VLANs are also projected onto the
matching `Interface` record (`native_vlan`, `attributes.tagged_vlans`) so they feed
the VLAN Explorer and Link tagged/untagged columns without a separate table.

## 7. Printer Discovery

`collectors/kyocera/plugin.py` now walks `prtMarkerSuppliesTable` for all supply
units (not just the primary/black marker) and classifies them into black/cyan/
magenta/yellow/waste by their vendor-provided description string, plus
`prtMarkerLifeCount` (total pages), `prtInputTable` status (paper empty), and
`hrPrinterDetectedErrorState`/`hrPrinterStatus`. Exposed via `GET /devices/{id}/printer`
and rendered as a topology map badge (amber border when any consumable is critically
low or paper is empty).

## 8. Trigger pack

New default triggers (`bootstrap.py`): Interface CRC errors, Interface drops, High
Temperature, Low Toner, Paper Empty, Device Offline, Optical RX Low. "Device Offline"
introduces a new trigger `kind`: `device_status`, which checks
`Device.last_seen_at` / latest `DeviceMetricModel.collected_at` against a
configurable window — independent of the syslog-based `absence` kind.

## 9. Trace Engine

- `GET /trace/mac?q=` — unchanged, still resolves MAC/IP/hostname.
- `GET /trace/device?q=` — new: full path from a device to the nearest core/firewall.
- `GET /trace/vlan/{vlan_id}` — new: VLAN Explorer data reused as a trace result.

All additive; no existing endpoint's request/response shape changed.
