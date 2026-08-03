"""Shared value objects."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from enum import StrEnum


_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}([-:])){5}[0-9A-Fa-f]{2}$|^([0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}$")


class DevicePlatform(StrEnum):
    ELTEX = "eltex"
    MIKROTIK = "mikrotik"
    UNIFI = "unifi"
    PROXMOX = "proxmox"
    VSPHERE = "vsphere"
    ESXI = "esxi"
    IDECO = "ideco"
    KYOCERA = "kyocera"
    LINUX = "linux"
    WINDOWS = "windows"
    DOCKER_HOST = "docker_host"
    CISCO_IOS = "cisco_ios"  # optional / not in primary deployment stack
    UNKNOWN = "unknown"


class DeviceStatus(StrEnum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class DiscoveryMethod(StrEnum):
    LLDP = "lldp"
    CDP = "cdp"
    FDB = "fdb"
    ARP = "arp"
    MANUAL_SEED = "manual_seed"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IpAddressStatus(StrEnum):
    USED = "used"
    FREE = "free"
    RESERVED = "reserved"
    CONFLICT = "conflict"


class CredentialProtocol(StrEnum):
    SNMP_V2C = "snmp_v2c"
    SNMP_V3 = "snmp_v3"
    SSH = "ssh"
    UNIFI = "unifi"
    PROXMOX = "proxmox"
    VSPHERE = "vsphere"
    ESXI = "esxi"
    IDECO = "ideco"
    DOCKER = "docker"


@dataclass(frozen=True, slots=True)
class MacAddress:
    value: str

    def __post_init__(self) -> None:
        normalized = self._normalize(self.value)
        object.__setattr__(self, "value", normalized)

    @staticmethod
    def _normalize(raw: str) -> str:
        cleaned = raw.strip().lower().replace("-", ":").replace(".", "")
        if "." in raw and len(raw.replace(".", "")) == 12:
            cleaned = raw.lower().replace(".", "")
        if ":" not in cleaned and len(cleaned) == 12:
            cleaned = ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
        if not _MAC_RE.match(cleaned.replace("-", ":")) and not re.match(
            r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$", cleaned
        ):
            raise ValueError(f"Invalid MAC address: {raw}")
        return cleaned

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IpAddressVO:
    value: str

    def __post_init__(self) -> None:
        addr = ipaddress.ip_address(self.value.strip())
        object.__setattr__(self, "value", str(addr))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class IpNetworkVO:
    value: str

    def __post_init__(self) -> None:
        net = ipaddress.ip_network(self.value.strip(), strict=False)
        object.__setattr__(self, "value", str(net))

    def network(self) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
        return ipaddress.ip_network(self.value, strict=False)

    def hosts(self) -> list[str]:
        net = self.network()
        if isinstance(net, ipaddress.IPv4Network) and net.prefixlen >= 31:
            return [str(a) for a in net]
        return [str(a) for a in net.hosts()]


@dataclass(frozen=True, slots=True)
class VlanId:
    value: int

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 4094:
            raise ValueError("VLAN must be 0..4094")
