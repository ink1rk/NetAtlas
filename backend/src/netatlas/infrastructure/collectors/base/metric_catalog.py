"""Named monitoring metrics backed by standard MIBs (not a full MIB compiler).

Operators build triggers against `name` fields. Collectors populate the same names
on DeviceMetricModel columns or extras.
"""

from __future__ import annotations

from typing import Any

METRIC_CATALOG: list[dict[str, Any]] = [
    {
        "name": "cpu_percent",
        "label": "CPU utilization",
        "mib": "HOST-RESOURCES-MIB",
        "oid": "1.3.6.1.2.1.25.3.3.1.2",
        "unit": "%",
        "kind": "gauge",
        "description": "Average hrProcessorLoad",
    },
    {
        "name": "memory_percent",
        "label": "Memory utilization",
        "mib": "HOST-RESOURCES-MIB",
        "oid": "1.3.6.1.2.1.25.2.3.1",
        "unit": "%",
        "kind": "gauge",
        "description": "RAM used from hrStorage table",
    },
    {
        "name": "uptime_seconds",
        "label": "System uptime",
        "mib": "SNMPv2-MIB",
        "oid": "1.3.6.1.2.1.1.3.0",
        "unit": "s",
        "kind": "counter",
        "description": "sysUpTime (converted from timeticks)",
    },
    {
        "name": "interfaces_total",
        "label": "Interfaces total",
        "mib": "IF-MIB",
        "oid": "1.3.6.1.2.1.2.2.1.8",
        "unit": "count",
        "kind": "gauge",
        "description": "Count of interfaces in ifOperStatus walk",
    },
    {
        "name": "interfaces_down",
        "label": "Interfaces down",
        "mib": "IF-MIB",
        "oid": "1.3.6.1.2.1.2.2.1.8",
        "unit": "count",
        "kind": "gauge",
        "description": "ifOperStatus == down (2)",
    },
    {
        "name": "if_in_errors",
        "label": "Interface in errors (sum)",
        "mib": "IF-MIB",
        "oid": "1.3.6.1.2.1.2.2.1.14",
        "unit": "count",
        "kind": "counter",
        "description": "Sum of ifInErrors",
    },
    {
        "name": "if_out_errors",
        "label": "Interface out errors (sum)",
        "mib": "IF-MIB",
        "oid": "1.3.6.1.2.1.2.2.1.20",
        "unit": "count",
        "kind": "counter",
        "description": "Sum of ifOutErrors",
    },
    {
        "name": "temperature_c",
        "label": "Temperature",
        "mib": "ENTITY-SENSOR-MIB / vendor",
        "oid": "vendor-specific",
        "unit": "°C",
        "kind": "gauge",
        "description": "When exposed by vendor collector",
    },
]


def catalog_by_name() -> dict[str, dict[str, Any]]:
    return {m["name"]: m for m in METRIC_CATALOG}
