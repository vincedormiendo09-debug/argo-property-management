from __future__ import annotations

import uuid
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    String, Text, Boolean, DateTime, Date, Numeric, Integer, ForeignKey, Index, UniqueConstraint, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


# =====================================================================
# CORE ORGANIZATION & USER IDENTITY
# =====================================================================
class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, default="Admin User")
    full_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="client")
    avatar: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="U")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# =====================================================================
# PROPERTY MANAGEMENT MODULE
# =====================================================================

class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_properties_org_code"),
        Index("ix_properties_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    property_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, default="Residential Multi-Family")
    location: Mapped[str] = mapped_column(Text, nullable=False)
    tct_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    units_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occupancy: Mapped[str] = mapped_column(String(20), nullable=False, default="0.0%")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    buildings: Mapped[list["Building"]] = relationship("Building", back_populates="property", cascade="all, delete-orphan")
    units: Mapped[list["Unit"]] = relationship("Unit", back_populates="property", cascade="all, delete-orphan")


class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_buildings_org_code"),
        Index("ix_buildings_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    floors: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occupied_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")
    floor_distribution: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    property: Mapped["Property"] = relationship("Property", back_populates="buildings")
    units: Mapped[list["Unit"]] = relationship("Unit", back_populates="building")


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (
        UniqueConstraint("organization_id", "property_id", "unit_no", name="uq_units_org_prop_unitno"),
        Index("ix_units_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    building_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True, index=True
    )

    unit_no: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, default="1-Bedroom Apartment")
    floor: Mapped[str] = mapped_column(String(50), nullable=False, default="1st Floor")
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sqm: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True, default=45.0)
    rent: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    rent_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Available")
    tenant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    property: Mapped["Property"] = relationship("Property", back_populates="units")
    building: Mapped[Optional["Building"]] = relationship("Building", back_populates="units")


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        UniqueConstraint("organization_id", "tenant_id", name="uq_tenants_org_tenant_id"),
        Index("ix_tenants_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    tenant_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tnt_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="Individual")
    unit: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    lease_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    emergency_contact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Owner(Base):
    __tablename__ = "owners"
    __table_args__ = (
        UniqueConstraint("organization_id", "own_id", name="uq_owners_org_own_id"),
        Index("ix_owners_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    own_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="INDIVIDUAL")
    tin: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class PropertyOwnership(Base):
    __tablename__ = "property_ownership"
    __table_args__ = (
        Index("ix_property_ownership_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), nullable=False, index=True
    )

    share_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=100.00)
    role: Mapped[str] = mapped_column(String(100), nullable=False, default="Primary Managing Owner")
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    contract_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Lease(Base):
    __tablename__ = "leases"
    __table_args__ = (
        UniqueConstraint("organization_id", "lease_id", name="uq_leases_org_lease_id"),
        Index("ix_leases_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )

    lease_id: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    property_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unit_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    rent: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    deposit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# =====================================================================
# UTILITIES & METERING MODULE
# =====================================================================

class Utility(Base):
    __tablename__ = "utilities"
    __table_args__ = (
        Index("ix_utilities_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lease_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leases.id", ondelete="SET NULL"), nullable=True, index=True
    )

    utility_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    utility_type: Mapped[str] = mapped_column(String(100), nullable=False, default="Electricity Sub-Meter")
    billing_period: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)

    reading_prev: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, default=0.0)
    reading_curr: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, default=0.0)
    consumption: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, default=0.0)
    rate: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, default=0.0)

    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Unpaid")

    tenant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tenant_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    property_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unit_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_id", name="uq_invoices_org_inv_id"),
        Index("ix_invoices_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lease_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True
    )
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id", ondelete="SET NULL"), nullable=True, index=True
    )

    invoice_id: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tenant_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    property_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unit_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    type: Mapped[str] = mapped_column(String(150), nullable=False, default="Rent")
    sub: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    property_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Rent")
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    balance: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="UNPAID")
    channel: Mapped[str] = mapped_column(String(100), nullable=False, default="GCASH")
    payment_method: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ref_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reference_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("organization_id", "txn_id", name="uq_transactions_org_txn_id"),
        Index("ix_transactions_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    txn_id: Mapped[str] = mapped_column(String(50), nullable=False)
    ref_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    payer: Mapped[str] = mapped_column(String(150), nullable=False)
    property_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="INFLOW")
    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    channel: Mapped[str] = mapped_column(String(100), nullable=False, default="Bank Transfer")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Completed")
    timestamp: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MaintenanceTicket(Base):
    __tablename__ = "maintenance_tickets"
    __table_args__ = (
        UniqueConstraint("organization_id", "ticket_id", name="uq_tickets_org_ticket_id"),
        Index("ix_maintenance_tickets_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True
    )

    ticket_id: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    tenant_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    property_location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="General")
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="Medium")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Open")
    technician: Mapped[str] = mapped_column(String(150), nullable=False, default="Unassigned")
    scheduled_time: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, default=0.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (
        Index("ix_meter_readings_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True
    )

    reading_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tenant_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    unit_location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    utility: Mapped[str] = mapped_column(String(50), nullable=False)
    serial: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    prev_dial: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    curr_dial: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    consumption: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    unit_symbol: Mapped[str] = mapped_column(String(20), nullable=False, default="kWh")
    period: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Billed")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = (
        Index("ix_inspections_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("units.id", ondelete="SET NULL"), nullable=True, index=True
    )

    inspection_id: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(100), nullable=False)
    property_info: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tenant: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="Routine")
    date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    inspector: Mapped[str] = mapped_column(String(150), nullable=False, default="Property Manager")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Passed")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    doc_id: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(150), nullable=False)
    entity_sub: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploader: Mapped[str] = mapped_column(String(150), nullable=False, default="Property Admin")
    file_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Verified")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    pov: Mapped[str] = mapped_column(String(20), nullable=False, default="all")
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="general")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    property: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    amount: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    action_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    action_text: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    author: Mapped[str] = mapped_column(String(150), nullable=False, default="Property Manager")
    date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    scope: Mapped[str] = mapped_column(String(255), nullable=False, default="Entire Portfolio")
    format: Mapped[str] = mapped_column(String(50), nullable=False, default="Summary (.txt)")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Completed")

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


# Backward-compatible aliases
UtilityCharge = Utility
MaintenanceRequest = MaintenanceTicket
PropertyOwner = Owner