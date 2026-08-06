"""Mikrotik RouterOS read-only collector (routers / CPE / wireless)."""

from __future__ import annotations

import re

from netatlas.domain.ports import (
    ArpEntry,
    CollectorContext,
    DeviceFingerprint,
    FdbEntry,
    InventoryFacts,
    MetricsSample,
    NeighborFact,
)
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.snmp_inventory import (
    snmp_arp,
    snmp_fdb,
    snmp_inventory,
    snmp_metrics,
    snmp_neighbors,
)


class MikrotikCollector:
    vendor = "mikrotik"
    platforms = frozenset({"mikrotik"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(
            filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner, fingerprint.sys_object_id])
        ).lower()
        return "mikrotik" in blob or "routeros" in blob or "1.3.6.1.4.1.14988" in blob

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        facts = await snmp_inventory(ctx, vendor_hint="mikrotik")
        facts.platform = DevicePlatform.MIKROTIK
        facts.vendor = "mikrotik"
        # SNMP-only: pull board name from sysDescr when ENTITY-MIB is empty.
        if not facts.model or facts.model.lower() in {"unknown", "generic", ""}:
            from netatlas.infrastructure.collectors.base.snmp_inventory import _model_from_sys_descr

            parsed = _model_from_sys_descr(str((facts.attributes or {}).get("sys_descr") or facts.os_version or ""))
            if parsed:
                facts.model = parsed
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]

            async def run(cmd: str) -> str:
                return await ctx.ssh_exec(
                    ctx.target_ip,
                    cmd,
                    username=ssh.get("username", ""),
                    password=ssh.get("password"),
                    private_key=ssh.get("private_key"),
                    platform="mikrotik",
                    timeout=ctx.timeouts.get("ssh", 20.0),
                )

            identity = await run("/system identity print")
            resource = await run("/system resource print")
            routerboard = await run("/system routerboard print")
            ifaces = await run("/interface print detail without-paging")
            vlan_print = await run("/interface vlan print detail without-paging")
            bridge_ports = await run("/interface bridge port print detail without-paging")
            bridge_vlans = await run("/interface bridge vlan print detail without-paging")
            bridge_print = await run("/interface bridge print detail without-paging")
            route_print = await run("/ip route print detail without-paging")
            clock_print = await run("/system clock print")
            if identity:
                m = re.search(r'name:\s*"?([^"\n]+)"?', identity)
                if m:
                    facts.hostname = m.group(1).strip()
            if resource:
                facts.attributes["resource_print"] = resource[:4000]
                ver = re.search(r"version:\s*([^\n]+)", resource)
                if ver:
                    facts.os_version = ver.group(1).strip()[:255]
                    facts.firmware = facts.os_version
                board = re.search(r"board-name:\s*([^\n]+)", resource)
                if board:
                    facts.model = board.group(1).strip()[:128]
                cpu = re.search(r"cpu-load:\s*(\d+)", resource)
                if cpu:
                    facts.cpu_percent = float(cpu.group(1))
                free = re.search(r"free-memory:\s*(\d+)", resource)
                total = re.search(r"total-memory:\s*(\d+)", resource)
                if free and total and int(total.group(1)) > 0:
                    facts.memory_percent = 100.0 * (1 - int(free.group(1)) / int(total.group(1)))
            if routerboard:
                facts.attributes["routerboard"] = routerboard[:2000]
                serial = re.search(r"serial-number:\s*([^\n]+)", routerboard)
                if serial:
                    facts.serial = serial.group(1).strip()
            if ifaces:
                facts.attributes["interfaces_raw"] = ifaces[:8000]
                parsed = _parse_routeros_interfaces(ifaces)
                if parsed:
                    facts.interfaces = parsed
            if vlan_print:
                facts.vlans = _parse_vlan_print(vlan_print)
            if clock_print:
                tz = re.search(r"time-zone-name:\s*([^\n]+)", clock_print)
                if tz:
                    facts.attributes["timezone"] = tz.group(1).strip()
            bridge = _parse_bridge_view(bridge_print, bridge_ports, bridge_vlans)
            if bridge:
                facts.attributes["bridge"] = bridge
                # Mikrotik Bridge View — apply PVID/tagged per bridge port onto the matching interface
                by_name = {i["name"]: i for i in facts.interfaces}
                for port in bridge.get("ports", []):
                    iface = by_name.get(port["interface"])
                    if not iface:
                        continue
                    if port.get("pvid"):
                        iface["native_vlan"] = port["pvid"]
                    tagged = sorted(
                        {
                            v["vlan_id"]
                            for v in bridge.get("vlan_table", [])
                            if port["interface"] in v.get("tagged", [])
                        }
                    )
                    if tagged:
                        iface["tagged_vlans"] = tagged
                    if len(bridge.get("ports", [])) > 1:
                        iface["is_trunk"] = bool(tagged)
            if route_print:
                facts.attributes["routes"] = _parse_routes(route_print)
        return facts

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        neighbors = await snmp_neighbors(ctx)
        if neighbors:
            return neighbors
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(
                ctx.target_ip,
                "/ip neighbor print detail without-paging",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="mikrotik",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            return _parse_neighbors(out)
        return []

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]:
        entries = await snmp_fdb(ctx)
        if entries:
            return entries
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(
                ctx.target_ip,
                "/interface bridge host print detail without-paging",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="mikrotik",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            return _parse_bridge_hosts(out)
        return []

    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        entries = await snmp_arp(ctx)
        if entries:
            return entries
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(
                ctx.target_ip,
                "/ip arp print detail without-paging",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="mikrotik",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            return _parse_arp(out)
        return []

    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample:
        sample = await snmp_metrics(ctx)
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(
                ctx.target_ip,
                "/system resource print",
                username=ssh.get("username", ""),
                password=ssh.get("password"),
                private_key=ssh.get("private_key"),
                platform="mikrotik",
                timeout=ctx.timeouts.get("ssh", 20.0),
            )
            cpu = re.search(r"cpu-load:\s*(\d+)", out or "")
            if cpu:
                sample.cpu_percent = float(cpu.group(1))
        return sample


def _parse_routeros_interfaces(text: str) -> list[dict]:
    items: list[dict] = []
    current: dict | None = None
    for line in text.splitlines():
        if re.match(r"^\s*\d+\s", line) or line.strip().startswith("Flags:"):
            if current and current.get("name"):
                items.append(current)
            current = {
                "name": None,
                "if_index": None,
                "description": None,
                "mac": None,
                "mtu": None,
                "speed_bps": None,
                "admin_status": "unknown",
                "oper_status": "unknown",
                "duplex": None,
                "poe_enabled": False,
                "is_trunk": False,
                "native_vlan": None,
                "lacp_group": None,
            }
        if current is None:
            continue
        if "name=" in line:
            current["name"] = line.split("name=", 1)[1].split()[0].strip('"')
        if "mac-address=" in line:
            current["mac"] = line.split("mac-address=", 1)[1].split()[0].strip('"').lower()
        if "mtu=" in line:
            try:
                current["mtu"] = int(line.split("mtu=", 1)[1].split()[0])
            except ValueError:
                pass
        if "running" in line.lower():
            current["oper_status"] = "up"
            current["admin_status"] = "up"
        if "disabled" in line.lower():
            current["admin_status"] = "down"
    if current and current.get("name"):
        items.append(current)
    return items


def _parse_neighbors(text: str) -> list[NeighborFact]:
    facts: list[NeighborFact] = []
    for block in re.split(r"\n(?=\s*\d+\s)", text or ""):
        host = iface = local = mgmt = None
        for line in block.splitlines():
            if "identity=" in line:
                host = line.split("identity=", 1)[1].split()[0].strip('"')
            if "interface=" in line:
                local = line.split("interface=", 1)[1].split()[0].strip('"')
            if "interface-name=" in line:
                iface = line.split("interface-name=", 1)[1].split()[0].strip('"')
            if "address=" in line:
                mgmt = line.split("address=", 1)[1].split()[0].strip('"')
        if local and (host or mgmt):
            facts.append(
                NeighborFact(
                    local_interface=local,
                    remote_hostname=host,
                    remote_interface=iface,
                    remote_chassis_id=None,
                    remote_mgmt_ip=mgmt,
                    protocol="lldp",
                )
            )
    return facts


def _parse_bridge_hosts(text: str) -> list[FdbEntry]:
    entries: list[FdbEntry] = []
    for line in (text or "").splitlines():
        if "mac-address=" not in line:
            continue
        mac = line.split("mac-address=", 1)[1].split()[0].strip('"').lower()
        iface = "?"
        if "on-interface=" in line:
            iface = line.split("on-interface=", 1)[1].split()[0].strip('"')
        elif "interface=" in line:
            iface = line.split("interface=", 1)[1].split()[0].strip('"')
        entries.append(FdbEntry(mac=mac, vlan_id=None, interface=iface))
    return entries


def _parse_vlan_print(text: str) -> list[dict]:
    """`/interface vlan print detail` → [{vlan_id, name}] for VLAN Explorer."""
    items: list[dict] = []
    for block in re.split(r"\n(?=\s*\d+\s)", text or ""):
        vid = name = None
        if "vlan-id=" in block:
            m = re.search(r"vlan-id=(\d+)", block)
            if m:
                vid = int(m.group(1))
        if "name=" in block:
            m = re.search(r'name="?([^"\s]+)"?', block)
            if m:
                name = m.group(1)
        if vid is not None:
            items.append({"vlan_id": vid, "name": name})
    return items


def _parse_bridge_view(bridge_print: str | None, bridge_ports: str | None, bridge_vlans: str | None) -> dict:
    """Mikrotik Bridge View: bridges, ports (PVID/tagged/untagged/horizon), RSTP, VLAN table."""
    bridges: list[dict] = []
    for block in re.split(r"\n(?=\s*\d+\s)", bridge_print or ""):
        if "name=" not in block:
            continue
        name_m = re.search(r'name="?([^"\s]+)"?', block)
        protocol_m = re.search(r"protocol-mode=(\S+)", block)
        vlan_filtering_m = re.search(r"vlan-filtering=(yes|no)", block)
        if name_m:
            bridges.append(
                {
                    "name": name_m.group(1),
                    "rstp": (protocol_m.group(1) if protocol_m else "none"),
                    "vlan_filtering": (vlan_filtering_m.group(1) == "yes") if vlan_filtering_m else False,
                }
            )

    ports: list[dict] = []
    for block in re.split(r"\n(?=\s*\d+\s)", bridge_ports or ""):
        if "interface=" not in block:
            continue
        iface_m = re.search(r'interface="?([^"\s]+)"?', block)
        bridge_m = re.search(r'bridge="?([^"\s]+)"?', block)
        pvid_m = re.search(r"pvid=(\d+)", block)
        horizon_m = re.search(r"horizon=(\S+)", block)
        if iface_m:
            ports.append(
                {
                    "interface": iface_m.group(1),
                    "bridge": bridge_m.group(1) if bridge_m else None,
                    "pvid": int(pvid_m.group(1)) if pvid_m else 1,
                    "horizon": horizon_m.group(1) if horizon_m else None,
                }
            )

    vlan_table: list[dict] = []
    for block in re.split(r"\n(?=\s*\d+\s)", bridge_vlans or ""):
        if "vlan-ids=" not in block:
            continue
        vid_m = re.search(r"vlan-ids=(\d+)", block)
        tagged_m = re.search(r"tagged=([^\s]*)", block)
        untagged_m = re.search(r"untagged=([^\s]*)", block)
        if vid_m:
            vlan_table.append(
                {
                    "vlan_id": int(vid_m.group(1)),
                    "tagged": [p for p in (tagged_m.group(1).split(",") if tagged_m else []) if p],
                    "untagged": [p for p in (untagged_m.group(1).split(",") if untagged_m else []) if p],
                }
            )

    if not bridges and not ports and not vlan_table:
        return {}
    return {"bridges": bridges, "ports": ports, "vlan_table": vlan_table}


def _parse_routes(text: str) -> list[dict]:
    """`/ip route print detail` → normalized route facts (best-effort, active routes only)."""
    routes: list[dict] = []
    for block in re.split(r"\n(?=\s*\d+\s)", text or ""):
        if "dst-address=" not in block:
            continue
        dst_m = re.search(r"dst-address=(\S+)", block)
        gw_m = re.search(r"gateway=(\S+)", block)
        iface_m = re.search(r'(?:gateway|interface)=[^\s]*%([^\s]+)', block)
        distance_m = re.search(r"distance=(\d+)", block)
        flags_m = re.match(r"\s*\d+\s+([A-Za-z ]*?)\s+dst-address=", block)
        flags = flags_m.group(1).replace(" ", "") if flags_m else ""
        proto = "static"
        if "ospf" in block.lower():
            proto = "ospf"
        elif "bgp" in block.lower():
            proto = "bgp"
        elif "C" in flags:
            proto = "connected"
        elif "S" in flags:
            proto = "static"
        if dst_m:
            gw = gw_m.group(1) if gw_m else None
            routes.append(
                {
                    "destination": dst_m.group(1),
                    "next_hop": gw.split("%")[0] if gw else None,
                    "interface": iface_m.group(1) if iface_m else (gw.split("%")[1] if gw and "%" in gw else None),
                    "protocol": proto,
                    "metric": int(distance_m.group(1)) if distance_m else None,
                }
            )
    return routes


def _parse_arp(text: str) -> list[ArpEntry]:
    entries: list[ArpEntry] = []
    for line in (text or "").splitlines():
        if "address=" not in line or "mac-address=" not in line:
            continue
        ip = line.split("address=", 1)[1].split()[0].strip('"')
        mac = line.split("mac-address=", 1)[1].split()[0].strip('"').lower()
        iface = None
        if "interface=" in line:
            iface = line.split("interface=", 1)[1].split()[0].strip('"')
        entries.append(ArpEntry(ip=ip, mac=mac, interface=iface))
    return entries
