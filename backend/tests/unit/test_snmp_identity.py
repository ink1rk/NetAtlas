"""Unit tests for SNMP identity helpers and generic-signal gating."""

from __future__ import annotations

from netatlas.application.use_cases.discovery import _is_generic_signal
from netatlas.domain.ports import InventoryFacts
from netatlas.domain.value_objects import DevicePlatform
from netatlas.infrastructure.collectors.base.snmp_inventory import _model_from_sys_descr
from netatlas.infrastructure.collectors.base.snmp_transport import _clean_snmp_value


def test_model_from_sys_descr_mikrotik_crs() -> None:
    assert _model_from_sys_descr("RouterOS CRS354-48P-4S+2Q+") == "CRS354-48P-4S+2Q+"
    assert _model_from_sys_descr("MikroTik CRS326-24G-2S+") == "CRS326-24G-2S+"
    assert _model_from_sys_descr("RouterOS CCR2004-1G-12S+2XS") == "CCR2004-1G-12S+2XS"


def test_model_from_sys_descr_eltex() -> None:
    assert _model_from_sys_descr("Eltex MES3324 28-port") == "MES3324"


def test_clean_snmp_null_values() -> None:
    assert _clean_snmp_value("No Such Object currently exists at this OID") is None
    assert _clean_snmp_value("NoSuchInstance") is None
    assert _clean_snmp_value("CRS354-48P-4S+2Q+") == "CRS354-48P-4S+2Q+"


def test_is_generic_signal_treats_nosuch_model_as_empty() -> None:
    facts = InventoryFacts(
        hostname="10.0.0.1",
        vendor="generic",
        model="No Such Object currently exists at this OID",
        serial=None,
        firmware=None,
        os_version=None,
        management_mac=None,
        platform=DevicePlatform.UNKNOWN,
        interfaces=[{"name": ""}],
    )
    assert _is_generic_signal(facts) is True


def test_is_generic_signal_false_when_interfaces_present() -> None:
    facts = InventoryFacts(
        hostname="sw1",
        vendor="mikrotik",
        model="CRS354-48P-4S+2Q+",
        serial=None,
        firmware=None,
        os_version=None,
        management_mac="4c:5e:0c:11:22:33",
        platform=DevicePlatform.MIKROTIK,
        interfaces=[{"name": "ether1"}],
    )
    assert _is_generic_signal(facts) is False
