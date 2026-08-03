"""Generic SNMP fallback collector."""
from __future__ import annotations
from netatlas.domain.ports import *
from netatlas.infrastructure.collectors.base.snmp_inventory import snmp_arp, snmp_fdb, snmp_inventory, snmp_metrics, snmp_neighbors

class GenericSnmpCollector:
    vendor = "generic"
    platforms = frozenset({"unknown", "generic"})

    def supports(self, fingerprint: DeviceFingerprint) -> bool:
        return True

    async def collect_inventory(self, ctx: CollectorContext) -> InventoryFacts:
        return await snmp_inventory(ctx, vendor_hint="generic")
    async def collect_neighbors(self, ctx: CollectorContext) -> list[NeighborFact]: return await snmp_neighbors(ctx)
    async def collect_fdb(self, ctx: CollectorContext) -> list[FdbEntry]: return await snmp_fdb(ctx)
    async def collect_arp(self, ctx: CollectorContext) -> list[ArpEntry]: return await snmp_arp(ctx)
    async def collect_metrics(self, ctx: CollectorContext) -> MetricsSample: return await snmp_metrics(ctx)
