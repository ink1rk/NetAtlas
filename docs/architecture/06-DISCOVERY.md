# Discovery Architecture

## Goals

Maximize autonomous coverage with **zero write operations** on network gear.

## Seed Model

A discovery seed contains:

- Target: single IP or CIDR  
- Credential profile references (SNMPv2, SNMPv3, SSH, ESXi, Docker)  
- Options: max concurrency, ICMP timeout, SNMP timeout, exclude lists  

## Pipeline Stages

1. **Expand** — CIDR → host list (respect excludes)  
2. **Probe** — ICMP echo; mark unreachable  
3. **Fingerprint** — SNMP sysDescr/sysObjectID or SSH banner  
4. **Select plugin** — registry match by fingerprint  
5. **Inventory** — hostname, vendor, model, serial, firmware, OS, interfaces, VLANs, PoE, CPU/RAM/temp/uptime  
6. **Adjacency** — LLDP/CDP → FDB → ARP fallback  
7. **Enrich** — routes (read), metrics baseline  
8. **Correlate** — merge duplicate devices (serial/MAC/IP)  
9. **Snapshot** — freeze world state  
10. **IPAM sync** — mark used/free/conflict  

## Transport Allow-Lists

### SNMP
GET / GETNEXT / GETBULK / WALK only. OID SET is hard-blocked in the SNMP adapter.

### SSH command catalog (examples)
Cisco: `show version`, `show inventory`, `show interfaces`, `show lldp neighbors detail`, `show cdp neighbors detail`, `show mac address-table`, `show ip arp`, `show vlan brief`, `show etherchannel summary`  
Mikrotik: `/system resource print`, `/interface print detail`, `/ip neighbor print`, …  
Linux: `hostnamectl`, `ip -j link`, `ip -j neigh`, `lldpctl -f json`, `cat /proc/meminfo`, …  

Any command matching mutate patterns (`configure`, `write`, `reload`, `set`, …) is rejected by `ReadOnlyCommandGuard`.

## Concurrency & Safety

- Per-device lock in Redis to avoid overlapping collectors  
- Global rate limits per credential/profile  
- Circuit breaker after N auth failures  
- All collector errors are typed and non-fatal to the job  

## Idempotency

Re-running discovery upserts by natural keys and refreshes `last_seen_at`. Links decay confidence if not reconfirmed within N jobs.
