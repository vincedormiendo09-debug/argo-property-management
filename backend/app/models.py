import uuid
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    String, Text, Boolean, DateTime, Date, Numeric, Integer, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base  # Clean import for Alembic


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
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="admin")
    avatar: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="JD")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# =====================================================================
# DORMIENDO PROPERTY MGMT MODULE (Prefix: property_)
# =====================================================================

# 1. PROPERTIES TABLE
class Property(Base):
    __tablename__ = "property_properties"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_property_properties_org_code"),
        Index("ix_property_properties_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="Residential")
    location: Mapped[str] = mapped_column(Text, nullable=False)
    units_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    buildings: Mapped[list["Building"]] = relationship("Building", back_populates="property", cascade="all, delete-orphan")
    units: Mapped[list["Unit"]] = relationship("Unit", back_populates="property", cascade="all, delete-orphan")


# 2. BUILDINGS TABLE
class Building(Base):
    __tablename__ = "property_buildings"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_property_buildings_org_code"),
        Index("ix_property_buildings_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_properties.id", ondelete="CASCADE"), nullable=False, index=True
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    floors: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    property: Mapped["Property"] = relationship("Property", back_populates="buildings")
    units: Mapped[list["Unit"]] = relationship("Unit", back_populates="building")


# 3. UNITS TABLE
class Unit(Base):
    __tablename__ = "property_units"
    __table_args__ = (
        UniqueConstraint("organization_id", "property_id", "unit_no", name="uq_property_units_org_prop_unitno"),
        Index("ix_property_units_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    building_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_buildings.id", ondelete="SET NULL"), nullable=True, index=True
    )

    unit_no: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="1BR")
    floor: Mapped[str] = mapped_column(String(50), nullable=False, default="1")
    rent: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="VACANT")
    subtitle: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    property: Mapped["Property"] = relationship("Property", back_populates="units")
    building: Mapped[Optional["Building"]] = relationship("Building", back_populates="units")


# 4. TENANTS TABLE
class Tenant(Base):
    __tablename__ = "property_tenants"
    __table_args__ = (
        UniqueConstraint("organization_id", "tnt_id", name="uq_property_tenants_org_tnt_id"),
        Index("ix_property_tenants_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)  # Loose UUID

    tnt_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="Individual")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 5. OWNERS TABLE
class Owner(Base):
    __tablename__ = "property_owners"
    __table_args__ = (
        UniqueConstraint("organization_id", "own_id", name="uq_property_owners_org_own_id"),
        Index("ix_property_owners_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)  # Loose UUID

    own_id: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="INDIVIDUAL")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 6. PROPERTY OWNERSHIP TABLE
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
        UUID(as_uuid=True), ForeignKey("property_properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_owners.id", ondelete="CASCADE"), nullable=False, index=True
    )

    share_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="Primary")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 7. LEASES TABLE
class Lease(Base):
    __tablename__ = "property_leases"
    __table_args__ = (
        UniqueConstraint("organization_id", "lease_id", name="uq_property_leases_org_lease_id"),
        Index("ix_property_leases_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_units.id", ondelete="CASCADE"), nullable=False, index=True
    )

    lease_id: Mapped[str] = mapped_column(String(50), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    rent: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    deposit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="DRAFT")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 8. INVOICES TABLE
class Invoice(Base):
    __tablename__ = "property_invoices"
    __table_args__ = (
        UniqueConstraint("organization_id", "invoice_id", name="uq_property_invoices_org_inv_id"),
        Index("ix_property_invoices_org_status", "organization_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lease_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_leases.id", ondelete="CASCADE"), nullable=True, index=True
    )

    invoice_id: Mapped[str] = mapped_column(String(50), nullable=False)
    type: Mapped[str] = mapped_column(String(150), nullable=False)
    sub: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_type: Mapped[str] = mapped_column(String(50), nullable=False, default="Rent")
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Unpaid")
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending Payment")
    ref_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 9. MASTER TRANSACTIONS TABLE
class Transaction(Base):
    __tablename__ = "property_transactions"
    __table_args__ = (
        UniqueConstraint("organization_id", "ref_code", name="uq_property_transactions_org_ref"),
        Index("ix_property_transactions_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    txn_id: Mapped[str] = mapped_column(String(50), nullable=False)
    ref_code: Mapped[str] = mapped_column(String(100), nullable=False)
    payer: Mapped[str] = mapped_column(String(150), nullable=False)
    property_location: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    gross_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending Audit")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 10. MAINTENANCE TICKETS TABLE
class MaintenanceTicket(Base):
    __tablename__ = "property_maintenance_tickets"
    __table_args__ = (
        UniqueConstraint("organization_id", "ticket_id", name="uq_property_tickets_org_ticket_id"),
        Index("ix_property_tickets_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_units.id", ondelete="CASCADE"), nullable=True, index=True
    )

    ticket_id: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="Medium")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Open")
    technician: Mapped[str] = mapped_column(String(150), nullable=False, default="Unassigned")
    cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True, default=0.0)

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 11. SUB-METER READINGS TABLE
class MeterReading(Base):
    __tablename__ = "property_meter_readings"
    __table_args__ = (
        Index("ix_property_meter_readings_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_units.id", ondelete="CASCADE"), nullable=True, index=True
    )

    tenant_name: Mapped[str] = mapped_column(String(150), nullable=False)
    unit_location: Mapped[str] = mapped_column(String(200), nullable=False)
    utility: Mapped[str] = mapped_column(String(50), nullable=False)  # 'Meralco' or 'Maynilad'
    serial: Mapped[str] = mapped_column(String(100), nullable=False)
    prev_dial: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    curr_dial: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    consumption: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    unit_symbol: Mapped[str] = mapped_column(String(20), nullable=False, default="kWh")
    period: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Unbilled / Ready for Billing")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 12. INSPECTIONS & HANDOVERS TABLE
class Inspection(Base):
    __tablename__ = "property_inspections"
    __table_args__ = (
        Index("ix_property_inspections_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("property_units.id", ondelete="CASCADE"), nullable=True, index=True
    )

    inspection_id: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_name: Mapped[str] = mapped_column(String(100), nullable=False)
    property_info: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant: Mapped[str] = mapped_column(String(150), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'Move-in', 'Move-out', 'Routine'
    date: Mapped[date] = mapped_column(Date, nullable=False)
    inspector: Mapped[str] = mapped_column(String(150), nullable=False, default="Property Admin")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Pending")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 13. LEGAL VAULT & DOCUMENTS TABLE
class Document(Base):
    __tablename__ = "property_documents"
    __table_args__ = (
        Index("ix_property_documents_org", "organization_id"),
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
    type: Mapped[str] = mapped_column(String(100), nullable=False)  # 'Title', 'Insurance', 'Tax', 'Lease Contract'
    uploader: Mapped[str] = mapped_column(String(150), nullable=False, default="Property Admin")
    date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Active")

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# 14. REAL-TIME NOTIFICATIONS TABLE
class Notification(Base):
    __tablename__ = "property_notifications"
    __table_args__ = (
        Index("ix_property_notifications_org", "organization_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    pov: Mapped[str] = mapped_column(String(20), nullable=False, default="admin")  # 'admin', 'owner', 'client'
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="system")  # 'payment', 'maintenance', 'asset'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unread")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    property: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    tag: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    urgent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Audit Block
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)


# Backward-compatible model aliases across routers
MaintenanceRequest = MaintenanceTicket