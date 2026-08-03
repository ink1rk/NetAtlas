"""Collector registry and base helpers."""

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
        # Last registered generic should always match; raise if empty.
        if not self._plugins:
            raise RuntimeError("No collector plugins registered")
        return self._plugins[-1]

    def all(self) -> list[CollectorPlugin]:
        return list(self._plugins)


def fingerprint_platform(fingerprint: DeviceFingerprint) -> DevicePlatform:
    blob = " ".join(
        filter(
            None,
            [fingerprint.sys_descr, fingerprint.sys_object_id, fingerprint.ssh_banner],
        )
    ).lower()
    rules: list[tuple[re.Pattern[str], DevicePlatform]] = [
        (re.compile(r"cisco|ios-xe|catalyst|nx-os"), DevicePlatform.CISCO_IOS),
        (re.compile(r"mikrotik|routeros"), DevicePlatform.MIKROTIK),
        (re.compile(r"eltex|mes\d+"), DevicePlatform.ELTEX),
        (re.compile(r"vmware|esxi"), DevicePlatform.ESXI),
        (re.compile(r"docker"), DevicePlatform.DOCKER_HOST),
        (re.compile(r"linux|ubuntu|debian|centos|rhel|red hat"), DevicePlatform.LINUX),
        (re.compile(r"windows|microsoft"), DevicePlatform.WINDOWS),
    ]
    for pattern, platform in rules:
        if pattern.search(blob):
            return platform
    return DevicePlatform.UNKNOWN


def build_default_registry() -> CollectorRegistry:
    from netatlas.infrastructure.collectors.cisco.plugin import CiscoIosCollector
    from netatlas.infrastructure.collectors.docker_host.plugin import DockerHostCollector
    from netatlas.infrastructure.collectors.eltex.plugin import EltexCollector
    from netatlas.infrastructure.collectors.esxi.plugin import EsxiCollector
    from netatlas.infrastructure.collectors.generic.plugin import GenericSnmpCollector
    from netatlas.infrastructure.collectors.linux.plugin import LinuxCollector
    from netatlas.infrastructure.collectors.mikrotik.plugin import MikrotikCollector
    from netatlas.infrastructure.collectors.windows.plugin import WindowsCollector

    registry = CollectorRegistry()
    for plugin in (
        CiscoIosCollector(),
        MikrotikCollector(),
        EltexCollector(),
        LinuxCollector(),
        WindowsCollector(),
        EsxiCollector(),
        DockerHostCollector(),
        GenericSnmpCollector(),
    ):
        registry.register(plugin)
    return registry


def oids(*values: str) -> Iterable[str]:
    return values
