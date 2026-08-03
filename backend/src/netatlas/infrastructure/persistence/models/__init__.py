"""ORM models for NetAtlas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, CIDR, INET, JSONB, MACADDR, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from netatlas.infrastructure.persistence.models.base import Base, TimestampMixin


class UserModel(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    roles: Mapped[list[UserRoleModel]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RoleModel(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class PermissionModel(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))


class UserRoleModel(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))

    user: Mapped[UserModel] = relationship(back_populates="roles")
    role: Mapped[RoleModel] = relationship()


class RolePermissionModel(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    permission_id: Mapped[UUID] = mapped_column(ForeignKey("permissions.id", ondelete="CASCADE"))


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SiteModel(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)


class DeviceModel(Base, TimestampMixin):
    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_management_ip", "management_ip"),
        Index("ix_devices_hostname", "hostname"),
        Index("ix_devices_serial", "serial"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    vendor: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="unknown")
    serial: Mapped[str | None] = mapped_column(String(128))
    firmware: Mapped[str | None] = mapped_column(String(128))
    os_version: Mapped[str | None] = mapped_column(String(128))
    management_ip: Mapped[str | None] = mapped_column(INET)
    management_mac: Mapped[str | None] = mapped_column(MACADDR)
    platform: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    site_id: Mapped[UUID | None] = mapped_column(ForeignKey("sites.id"))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    interfaces: Mapped[list[InterfaceModel]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class InterfaceModel(Base, TimestampMixin):
    __tablename__ = "interfaces"
    __table_args__ = (UniqueConstraint("device_id", "name"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    if_index: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(255))
    mac: Mapped[str | None] = mapped_column(MACADDR)
    mtu: Mapped[int | None] = mapped_column(Integer)
    duplex: Mapped[str | None] = mapped_column(String(32))
    speed_bps: Mapped[int | None] = mapped_column(BigInteger)
    poe_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    oper_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    is_trunk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    native_vlan: Mapped[int | None] = mapped_column(Integer)
    lacp_group: Mapped[str | None] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    device: Mapped[DeviceModel] = relationship(back_populates="interfaces")


class VlanModel(Base):
    __tablename__ = "vlans"
    __table_args__ = (UniqueConstraint("device_id", "vlan_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    vlan_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(128))


class InterfaceVlanModel(Base):
    __tablename__ = "interface_vlans"
    __table_args__ = (UniqueConstraint("interface_id", "vlan_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    interface_id: Mapped[UUID] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"))
    vlan_id: Mapped[UUID] = mapped_column(ForeignKey("vlans.id", ondelete="CASCADE"))
    tagged: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LinkModel(Base, TimestampMixin):
    __tablename__ = "links"
    __table_args__ = (UniqueConstraint("interface_a_id", "interface_b_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    interface_a_id: Mapped[UUID] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"))
    interface_b_id: Mapped[UUID] = mapped_column(ForeignKey("interfaces.id", ondelete="CASCADE"))
    discovery_method: Mapped[str] = mapped_column(String(32), nullable=False)
    speed_bps: Mapped[int | None] = mapped_column(BigInteger)
    is_lacp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lacp_key: Mapped[str | None] = mapped_column(String(64))
    is_trunk: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vlans: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LldpNeighborModel(Base):
    __tablename__ = "lldp_neighbors"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    local_interface: Mapped[str] = mapped_column(String(128), nullable=False)
    remote_hostname: Mapped[str | None] = mapped_column(String(255))
    remote_interface: Mapped[str | None] = mapped_column(String(128))
    remote_chassis_id: Mapped[str | None] = mapped_column(String(128))
    remote_mgmt_ip: Mapped[str | None] = mapped_column(INET)
    protocol: Mapped[str] = mapped_column(String(16), nullable=False, default="lldp")
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FdbEntryModel(Base):
    __tablename__ = "fdb_entries"
    __table_args__ = (Index("ix_fdb_mac", "mac"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    mac: Mapped[str] = mapped_column(MACADDR, nullable=False)
    vlan_id: Mapped[int | None] = mapped_column(Integer)
    interface: Mapped[str] = mapped_column(String(128), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArpEntryModel(Base):
    __tablename__ = "arp_entries"
    __table_args__ = (Index("ix_arp_ip", "ip"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    ip: Mapped[str] = mapped_column(INET, nullable=False)
    mac: Mapped[str] = mapped_column(MACADDR, nullable=False)
    interface: Mapped[str | None] = mapped_column(String(128))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RouteModel(Base):
    __tablename__ = "routes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    destination: Mapped[str] = mapped_column(CIDR, nullable=False)
    next_hop: Mapped[str | None] = mapped_column(INET)
    interface: Mapped[str | None] = mapped_column(String(128))
    protocol: Mapped[str | None] = mapped_column(String(64))
    metric: Mapped[int | None] = mapped_column(Integer)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DeviceMetricModel(Base):
    __tablename__ = "device_metrics"
    __table_args__ = (Index("ix_device_metrics_collected", "collected_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    cpu_percent: Mapped[float | None] = mapped_column(Float)
    memory_percent: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    extras: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CredentialProfileModel(Base, TimestampMixin):
    __tablename__ = "credential_profiles"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    protocol: Mapped[str] = mapped_column(String(32), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")


class DeviceCredentialModel(Base):
    __tablename__ = "device_credentials"
    __table_args__ = (UniqueConstraint("device_id", "credential_profile_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    credential_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("credential_profiles.id", ondelete="CASCADE")
    )


class DiscoverySeedModel(Base, TimestampMixin):
    __tablename__ = "discovery_seeds"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    credential_profile_ids: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class DiscoveryJobModel(Base):
    __tablename__ = "discovery_jobs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SnapshotModel(Base):
    __tablename__ = "snapshots"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    discovery_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("discovery_jobs.id"))
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class IpPrefixModel(Base, TimestampMixin):
    __tablename__ = "ip_prefixes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    prefix: Mapped[str] = mapped_column(CIDR, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("ip_prefixes.id"))
    site_id: Mapped[UUID | None] = mapped_column(ForeignKey("sites.id"))


class IpAddressModel(Base, TimestampMixin):
    __tablename__ = "ip_addresses"
    __table_args__ = (UniqueConstraint("address"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    prefix_id: Mapped[UUID | None] = mapped_column(ForeignKey("ip_prefixes.id"))
    address: Mapped[str] = mapped_column(INET, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="used")
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"))
    interface_id: Mapped[UUID | None] = mapped_column(ForeignKey("interfaces.id"))
    mac: Mapped[str | None] = mapped_column(MACADDR)
    is_conflict: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_created", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64))
    source_ip: Mapped[str | None] = mapped_column(INET)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DockerHostModel(Base):
    __tablename__ = "docker_hosts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), unique=True)
    docker_version: Mapped[str | None] = mapped_column(String(64))
    api_endpoint: Mapped[str | None] = mapped_column(String(255))


class DockerNetworkModel(Base):
    __tablename__ = "docker_networks"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    docker_host_id: Mapped[UUID] = mapped_column(ForeignKey("docker_hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    driver: Mapped[str | None] = mapped_column(String(64))
    subnet: Mapped[str | None] = mapped_column(CIDR)
    gateway: Mapped[str | None] = mapped_column(INET)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class DockerContainerModel(Base):
    __tablename__ = "docker_containers"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    docker_host_id: Mapped[UUID] = mapped_column(ForeignKey("docker_hosts.id", ondelete="CASCADE"))
    docker_network_id: Mapped[UUID | None] = mapped_column(ForeignKey("docker_networks.id"))
    container_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    image: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str | None] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(INET)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class EsxiHostModel(Base):
    __tablename__ = "esxi_hosts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), unique=True)
    version: Mapped[str | None] = mapped_column(String(64))
    build: Mapped[str | None] = mapped_column(String(64))
    api_endpoint: Mapped[str | None] = mapped_column(String(255))


class VirtualMachineModel(Base):
    __tablename__ = "virtual_machines"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    esxi_host_id: Mapped[UUID] = mapped_column(ForeignKey("esxi_hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    power_state: Mapped[str | None] = mapped_column(String(32))
    cpu_count: Mapped[int | None] = mapped_column(Integer)
    memory_mb: Mapped[int | None] = mapped_column(Integer)
    guest_os: Mapped[str | None] = mapped_column(String(128))
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class DatastoreModel(Base):
    __tablename__ = "datastores"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    esxi_host_id: Mapped[UUID] = mapped_column(ForeignKey("esxi_hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    capacity_bytes: Mapped[int | None] = mapped_column(BigInteger)
    free_bytes: Mapped[int | None] = mapped_column(BigInteger)
    type: Mapped[str | None] = mapped_column(String(64))


class VSwitchModel(Base):
    __tablename__ = "vswitches"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    esxi_host_id: Mapped[UUID] = mapped_column(ForeignKey("esxi_hosts.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class PortGroupModel(Base):
    __tablename__ = "port_groups"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    vswitch_id: Mapped[UUID] = mapped_column(ForeignKey("vswitches.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    vlan_id: Mapped[int | None] = mapped_column(Integer)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class ObservabilityEventModel(Base):
    """Normalized syslog / SIEM event."""

    __tablename__ = "observability_events"
    __table_args__ = (
        Index("ix_obs_events_received", "received_at"),
        Index("ix_obs_events_source_ip", "source_ip"),
        Index("ix_obs_events_severity", "severity"),
        Index("ix_obs_events_category", "category"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"), index=True)
    source_ip: Mapped[str | None] = mapped_column(INET)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    facility: Mapped[int | None] = mapped_column(Integer)
    severity: Mapped[int | None] = mapped_column(Integer)
    hostname: Mapped[str | None] = mapped_column(String(255))
    app_name: Mapped[str | None] = mapped_column(String(128))
    proc_id: Mapped[str | None] = mapped_column(String(64))
    msg_id: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="syslog")
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    extras: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class TriggerDefinitionModel(Base, TimestampMixin):
    __tablename__ = "trigger_definitions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="warning")
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    # Expression JSON: metric_threshold / syslog_match / interface_status / absence / siem_correlation
    expression: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    recovery_expression: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notify_smtp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_telegram: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_element: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok|problem
    last_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_value: Mapped[str | None] = mapped_column(Text)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"))


class TriggerEventModel(Base):
    __tablename__ = "trigger_events"
    __table_args__ = (Index("ix_trigger_events_created", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    trigger_id: Mapped[UUID] = mapped_column(ForeignKey("trigger_definitions.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)  # PROBLEM|OK
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    extras: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AlertNotificationModel(Base):
    __tablename__ = "alert_notifications"
    __table_args__ = (Index("ix_alert_notifications_created", "created_at"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    trigger_event_id: Mapped[UUID | None] = mapped_column(ForeignKey("trigger_events.id"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="smtp")
    destination: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SiemCorrelationHitModel(Base):
    __tablename__ = "siem_correlation_hits"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="warning")
    source_ip: Mapped[str | None] = mapped_column(INET)
    device_id: Mapped[UUID | None] = mapped_column(ForeignKey("devices.id"))
    event_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=list)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
