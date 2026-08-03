"""Linux host read-only collector."""
from __future__ import annotations
import json
from netatlas.domain.ports import *
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.snmp_inventory import snmp_arp, snmp_fdb, snmp_inventory, snmp_metrics, snmp_neighbors

class LinuxCollector:
    vendor = "linux"
    platforms = frozenset({"linux"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        blob = " ".join(filter(None, [fingerprint.sys_descr, fingerprint.ssh_banner])).lower()
        return any(x in blob for x in ("linux", "ubuntu", "debian", "centos", "rhel", "red hat"))

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            async def run(cmd: str) -> str:
                return await ctx.ssh_exec(ctx.target_ip, cmd, username=ssh.get("username",""), password=ssh.get("password"), private_key=ssh.get("private_key"), platform="linux", timeout=ctx.timeouts.get("ssh", 20.0))
            hostname = (await run("hostnamectl --static")).strip() or ctx.target_ip
            uname = await run("uname -a")
            links_raw = await run("ip -j link")
            interfaces=[]
            try:
                for item in json.loads(links_raw or "[]"):
                    interfaces.append({
                        "name": item.get("ifname"),
                        "if_index": str(item.get("ifindex")),
                        "description": None,
                        "mac": item.get("address"),
                        "mtu": item.get("mtu"),
                        "speed_bps": None,
                        "admin_status": "up" if "UP" in (item.get("flags") or []) else "down",
                        "oper_status": "up" if "LOWER_UP" in (item.get("flags") or []) else "down",
                        "duplex": None, "poe_enabled": False, "is_trunk": False, "native_vlan": None, "lacp_group": None,
                    })
            except json.JSONDecodeError:
                pass
            mem = await run("cat /proc/meminfo")
            return InventoryFacts(hostname=hostname, vendor="linux", model="linux-host", serial=None, firmware=None, os_version=uname.strip()[:255], management_mac=None, platform=DevicePlatform.LINUX, attributes={"meminfo": mem[:2000]}, interfaces=interfaces)
        return await snmp_inventory(ctx, vendor_hint="linux")

    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]:
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(ctx.target_ip, "lldpctl -f json", username=ssh.get("username",""), password=ssh.get("password"), private_key=ssh.get("private_key"), platform="linux", timeout=ctx.timeouts.get("ssh", 20.0))
            try:
                data = json.loads(out or "{}")
                facts=[]
                ifaces = data.get("lldp", {}).get("interface", {})
                if isinstance(ifaces, dict):
                    for name, payload in ifaces.items():
                        chassis = payload.get("chassis", {})
                        port = payload.get("port", {})
                        remote = next(iter(chassis.values()), {}) if isinstance(chassis, dict) and chassis else {}
                        facts.append(NeighborFact(local_interface=name, remote_hostname=remote.get("name") or remote.get("descr"), remote_interface=port.get("id",{}).get("value") if isinstance(port.get("id"), dict) else port.get("id"), remote_chassis_id=None, remote_mgmt_ip=None, protocol="lldp"))
                return facts
            except Exception:
                pass
        return await snmp_neighbors(ctx)

    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]: return await snmp_fdb(ctx)
    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]:
        if ctx.ssh_exec and ctx.credentials.get("ssh"):
            ssh = ctx.credentials["ssh"]
            out = await ctx.ssh_exec(ctx.target_ip, "ip -j neigh", username=ssh.get("username",""), password=ssh.get("password"), private_key=ssh.get("private_key"), platform="linux", timeout=ctx.timeouts.get("ssh", 20.0))
            try:
                return [ArpEntry(ip=i.get("dst"), mac=i.get("lladdr") or "", interface=i.get("dev")) for i in json.loads(out or "[]") if i.get("dst") and i.get("lladdr")]
            except Exception:
                pass
        return await snmp_arp(ctx)
    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample: return await snmp_metrics(ctx)
