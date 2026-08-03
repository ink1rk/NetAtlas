# Target Deployment Stack

NetAtlas is tailored for the following production estate. Cisco is **not** part of the primary stack (collector remains optional/legacy only).

## Primary platforms

| Platform | Role | Discovery transports |
|----------|------|----------------------|
| **Eltex** (MES/ESR) | Access / aggregation / core switching | SNMPv2/v3, SSH (`show …` only), LLDP, FDB, ARP |
| **Mikrotik** (RouterOS) | Routing, CPE, wireless, bridges | SNMP, SSH RouterOS read commands, neighbor/ARP/bridge host |
| **UniFi** (Ubiquiti) | Wi‑Fi / switching / gateway | UniFi Network Application API (GET), SNMP fallback, uplink/LLDP tables |
| **Proxmox VE** | Virtualization hosts / guests | Proxmox API token (read), SSH `pvesh get` / `pveversion`, SNMP |
| **vSphere / ESXi** | VMware estate | vSphere read API (hosts/VMs/datastores/networks), SNMP |
| **Ideco** | Edge UTM / firewall | SNMP, SSH Linux-like read probes, ARP for IPAM |
| **Kyocera** | Printers / MFP | Printer-MIB + Host-Resources SNMP (serial, model, toner) |

## Topology expectations

```
Internet
   ↓
Ideco (UTM)
   ↓
Eltex core / aggregation
   ├─ Mikrotik (WAN/VPN/CPE)
   ├─ UniFi switches / APs
   ├─ Proxmox nodes (+ VMs/LXC)
   ├─ vSphere / ESXi (+ VMs)
   └─ Kyocera printers (leaf, via switch FDB)
```

Printers and APs often lack LLDP — links are inferred from **switch FDB** and **ARP**.

## Credential profiles (examples)

- `snmp_v2c` / `snmp_v3` — Eltex, Mikrotik, Ideco, Kyocera, fallbacks  
- `ssh` — Eltex, Mikrotik, Ideco, Proxmox shell  
- `unifi` — `{base_url, site, api_key|cookie}`  
- `proxmox` — `{base_url, token_id, token_secret, node?}`  
- `vsphere` — `{base_url, session_id|authorization, mode?}`  

All secrets stored AES-256-GCM encrypted. Collectors never receive write API verbs.
