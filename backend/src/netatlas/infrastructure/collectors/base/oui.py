"""Static OUI (Organizationally Unique Identifier) vendor lookup.

Used to classify devices that cannot be fingerprinted via SNMP/SSH (closed
appliances, IoT, cameras, phones, printers from vendors without SNMP enabled,
etc.) so Discovery can still create a useful "Unknown Device" record instead
of silently dropping the host.

Not exhaustive — covers the vendors most commonly seen on corporate LANs.
Extend freely; this is a plain data table, no external dependency required.
"""

from __future__ import annotations

# MAC prefix (first 3 octets, uppercase, colon-free) → vendor label
OUI_MAP: dict[str, str] = {
    "000C29": "VMware",
    "005056": "VMware",
    "000569": "VMware",
    "001C42": "Parallels",
    "080027": "VirtualBox",
    "525400": "QEMU/KVM",
    "00155D": "Microsoft Hyper-V",
    "0003FF": "Microsoft",
    "B827EB": "Raspberry Pi",
    "DCA632": "Raspberry Pi",
    "E45F01": "Raspberry Pi",
    "3C5AB4": "Google",
    "F4F5D8": "Google",
    "AC67B2": "Google Nest",
    "18B430": "Nest Labs",
    "F0272D": "Apple",
    "F4F1E1": "Apple",
    "A45E60": "Apple",
    "BC926B": "Apple",
    "DCA904": "Apple",
    "001E52": "Apple",
    "0050F2": "Microsoft",
    "6C3BE5": "Huawei",
    "00E0FC": "Huawei",
    "F8A2D6": "Huawei",
    "001788": "H3C/HP",
    "0018E7": "Cameo Communications",
    "00259C": "Cisco",
    "0025B4": "Cisco",
    "00265A": "Cisco",
    "1C1D86": "Cisco",
    "58971E": "Cisco",
    "F87B7A": "Cisco",
    "6C9CED": "Cisco",
    "3417EB": "Cisco",
    "F0F755": "Ubiquiti",
    "24A43C": "Ubiquiti",
    "788A20": "Ubiquiti",
    "802AA8": "Ubiquiti",
    "AC8BA9": "Ubiquiti",
    "DC9FDB": "Ubiquiti",
    "E063DA": "Ubiquiti",
    "F09FC2": "Ubiquiti",
    "4C5E0C": "Mikrotik",
    "6C3B6B": "Mikrotik",
    "B869F4": "Mikrotik",
    "D4CA6D": "Mikrotik",
    "E48D8C": "Mikrotik",
    "CC2DE0": "Mikrotik",
    "482CA0": "Mikrotik",
    "000C42": "Mikrotik",
    "744D28": "Eltex",
    "00C0B7": "Eltex",
    "20AF6C": "Eltex",
    "F02FA7": "Eltex",
    "18A6F7": "Kyocera",
    "00E057": "Kyocera",
    "005006": "Kyocera",
    "883CDB": "Kyocera",
    "0800BE": "Hewlett Packard (Printer)",
    "3C4A92": "HP",
    "9C8E99": "HP",
    "D89D67": "HP",
    "0004E2": "Canon",
    "00A0DE": "Canon",
    "182666": "Canon",
    "0080F0": "Panasonic",
    "708BCD": "Ricoh",
    "00265D": "Ricoh",
    "F4A7C6": "Ricoh",
    "5CE0C5": "Xerox",
    "0000AA": "Xerox",
    "00207B": "Xerox",
    "000FE2": "Hikvision",
    "4C1121": "Hikvision",
    "544A16": "Hikvision",
    "8CE748": "Hikvision",
    "A4142F": "Hikvision",
    "BC9911": "Hikvision",
    "3C6105": "Dahua",
    "9C8ECD": "Dahua",
    "E82725": "Dahua",
    "001395": "Axis Communications",
    "ACCC8E": "Axis Communications",
    "B8A44F": "Axis Communications",
    "00179A": "D-Link",
    "1C7EE5": "D-Link",
    "CCB255": "D-Link",
    "F0B4D2": "TP-Link",
    "50C7BF": "TP-Link",
    "B0487A": "TP-Link",
    "C46E1F": "TP-Link",
    "EC086B": "TP-Link",
    "9C53CD": "Netgear",
    "A040A0": "Netgear",
    "204E7F": "Netgear",
    "E4F4C6": "Netgear",
    "F87394": "Zyxel",
    "5C6A80": "Zyxel",
    "001349": "Zyxel",
    "000C6E": "Asustek",
    "1C872C": "Asustek",
    "AC220B": "Grandstream",
    "000B82": "Grandstream",
    "00107B": "Cisco (VoIP)",
    "00036B": "Cisco",
    "3065EC": "Polycom",
    "0004F2": "Polycom",
    "64168D": "Yealink",
    "805EC0": "Yealink",
    "001565": "Fanvil",
    "0C383E": "Synology",
    "001132": "Synology",
    "24BEC7": "QNAP",
    "0008A2": "QNAP",
    "B0EE7B": "TrueNAS/iXsystems",
    "080069": "Silicon Graphics",
    "000E58": "Aruba Networks",
    "24DEC6": "Aruba Networks",
    "1C28AF": "Aruba Networks",
    "94B40F": "Aruba Networks",
    "F0921C": "Aruba Networks",
    "0021A0": "Juniper Networks",
    "2C6BF5": "Juniper Networks",
    "8CB64F": "Ideco",
    "0021B7": "Fortinet",
    "906CAC": "Fortinet",
    "A2E9FF": "Espressif (IoT)",
    "3C71BF": "Espressif (IoT)",
    "24A160": "Espressif (IoT)",
    "AC670D": "Sonos",
    "5CAAFD": "Sonos",
    "000E8F": "Extreme Networks",
    "00E02B": "Extreme Networks",
}


def normalize_mac(mac: str | None) -> str | None:
    if not mac:
        return None
    hex_only = "".join(c for c in mac.upper() if c in "0123456789ABCDEF")
    if len(hex_only) != 12:
        return None
    return ":".join(hex_only[i : i + 2] for i in range(0, 12, 2)).lower()


def lookup_oui(mac: str | None) -> str | None:
    """Return the vendor label for a MAC address, or None if unmapped."""
    if not mac:
        return None
    hex_only = "".join(c for c in mac.upper() if c in "0123456789ABCDEF")
    if len(hex_only) < 6:
        return None
    prefix = hex_only[:6]
    return OUI_MAP.get(prefix)


_PRINTER_HINTS = ("kyocera", "hp", "canon", "ricoh", "xerox", "panasonic", "printer")
_CAMERA_HINTS = ("hikvision", "dahua", "axis")
_AP_HINTS = ("ubiquiti", "aruba", "extreme")
_ROUTER_HINTS = ("mikrotik", "eltex", "juniper", "fortinet", "zyxel", "cisco")
_VOIP_HINTS = ("polycom", "yealink", "grandstream", "fanvil")
_NAS_HINTS = ("synology", "qnap", "truenas")
_VM_HINTS = ("vmware", "virtualbox", "qemu", "hyper-v", "parallels")
_IOT_HINTS = ("espressif", "sonos", "nest")


def guess_device_type(oui_vendor: str | None, *, hostname: str | None = None) -> str:
    """Heuristic device-class classification for Unknown Devices.

    Returns one of: printer, camera, access_point, router, voip_phone, nas,
    virtual_machine, iot, unknown.
    """
    blob = f"{oui_vendor or ''} {hostname or ''}".lower()
    for hints, label in (
        (_PRINTER_HINTS, "printer"),
        (_CAMERA_HINTS, "camera"),
        (_AP_HINTS, "access_point"),
        (_VOIP_HINTS, "voip_phone"),
        (_NAS_HINTS, "nas"),
        (_VM_HINTS, "virtual_machine"),
        (_ROUTER_HINTS, "router"),
        (_IOT_HINTS, "iot"),
    ):
        if any(h in blob for h in hints):
            return label
    return "unknown"
