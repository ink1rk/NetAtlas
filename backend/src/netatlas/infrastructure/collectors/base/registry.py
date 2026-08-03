"""Collector registry and fingerprinting for the deployment stack."""

from __future__ import annotations

import logging
import re
from typing import Iterable

from netatlas.domain.ports import CollectorPlugin, DeviceFingerprint
from netatlas.domain.value_objects import DevicePlatform

logger = logging.getLogger(__name__)


class CollectorRegistry:
    def __init__(self) -> None:
        self._plugins: list[CollectorPlugin] = []

    def register(self, plugin: CollectorPlugin) -> None:
        self._plugins.append(plugin)
        logger.info("Registered collector plugin vendor=%s", plugin.vendor)

    def resolve(self, fingerprint: DeviceFingerprint) -> CollectorPlugin:
        for plugin in self._plugins:
            if plugin.supports(fingerprint):
                return plugin
        if not self._plugins:
            raise RuntimeError("No collector plugins registered")
        return self._plugins[-1]

    def all(self) -> list[CollectorPlugin]:
        return list(self._plugins)


def fingerprint_platform(fingerprint: DeviceFingerprint) -> DevicePlatform:
    hint = fingerprint.hints.get("platform")
    if isinstance(hint, str):
        try:
            return DevicePlatform(hint)
        except ValueError:
            pass
    blob = " ".join(
        filter(
            None,
            [fingerprint.sys_descr, fingerprint.sys_object_id, fingerprint.ssh_banner],
        )
    ).lower()
    rules: list[tuple[re.Pattern[str], DevicePlatform]] = [
        (re.compile(r"eltex|mes\d+|1\.3\.6\.1\.4\.1\.35265"), DevicePlatform.ELTEX),
        (re.compile(r"mikrotik|routeros|1\.3\.6\.1\.4\.1\.14988"), DevicePlatform.MIKROTIK),
        (re.compile(r"unifi|ubiquiti|\budm\b|\busw\b|\buap\b|\buxg\b"), DevicePlatform.UNIFI),
        (re.compile(r"proxmox|\bpve\b"), DevicePlatform.PROXMOX),
        (re.compile(r"vcenter|vsphere"), DevicePlatform.VSPHERE),
        (re.compile(r"esxi|vmware"), DevicePlatform.VSPHERE),
        (re.compile(r"ideco|ics-utm"), DevicePlatform.IDECO),
        (re.compile(r"kyocera|ecosys|taskalfa|1\.3\.6\.1\.4\.1\.1347"), DevicePlatform.KYOCERA),
        (re.compile(r"docker"), DevicePlatform.DOCKER_HOST),
        (re.compile(r"linux|ubuntu|debian|centos|rhel|red hat"), DevicePlatform.LINUX),
        (re.compile(r"windows|microsoft"), DevicePlatform.WINDOWS),
        (re.compile(r"cisco|ios-xe|catalyst|nx-os"), DevicePlatform.CISCO_IOS),
    ]
    for pattern, platform in rules:
        if pattern.search(blob):
            return platform
    return DevicePlatform.UNKNOWN


def build_default_registry() -> CollectorRegistry:
    """Primary stack first; Cisco kept optional at the end before generic fallback."""
    from netatlas.infrastructure.collectors.cisco.plugin import CiscoIosCollector
    from netatlas.infrastructure.collectors.docker_host.plugin import DockerHostCollector
    from netatlas.infrastructure.collectors.eltex.plugin import EltexCollector
    from netatlas.infrastructure.collectors.generic.plugin import GenericSnmpCollector
    from netatlas.infrastructure.collectors.ideco.plugin import IdecoCollector
    from netatlas.infrastructure.collectors.kyocera.plugin import KyoceraCollector
    from netatlas.infrastructure.collectors.linux.plugin import LinuxCollector
    from netatlas.infrastructure.collectors.mikrotik.plugin import MikrotikCollector
    from netatlas.infrastructure.collectors.proxmox.plugin import ProxmoxCollector
    from netatlas.infrastructure.collectors.unifi.plugin import UnifiCollector
    from netatlas.infrastructure.collectors.vsphere.plugin import VsphereCollector
    from netatlas.infrastructure.collectors.windows.plugin import WindowsCollector

    registry = CollectorRegistry()
    for plugin in (
        EltexCollector(),
        MikrotikCollector(),
        UnifiCollector(),
        ProxmoxCollector(),
        VsphereCollector(),
        IdecoCollector(),
        KyoceraCollector(),
        LinuxCollector(),
        WindowsCollector(),
        DockerHostCollector(),
        CiscoIosCollector(),  # optional legacy
        GenericSnmpCollector(),
    ):
        registry.register(plugin)
    return registry


def oids(*values: str) -> Iterable[str]:
    return values
