from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List


# ==========================================
# 1. PROPERTIES SCHEMAS
# ==========================================
class PropertyBase(BaseModel):
    code: str
    name: str
    type: str = "Residential"
    location: str
    status: str = "Active"


class PropertyCreate(PropertyBase):
    organization_id: UUID
    created_by: Optional[UUID] = None


class PropertySchema(PropertyBase):
    id: UUID
    organization_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. UNITS SCHEMAS
# ==========================================
class UnitBase(BaseModel):
    unit_no: str
    type: str = "1BR"
    rent: float = 0.0
    status: str = "VACANT"


class UnitCreate(UnitBase):
    organization_id: UUID
    property_id: UUID
    created_by: Optional[UUID] = None


class UnitSchema(UnitBase):
    id: UUID
    organization_id: UUID
    property_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. TENANTS SCHEMAS
# ==========================================
class TenantBase(BaseModel):
    name: str
    email: str
    phone: str
    status: str = "Active"


class TenantCreate(TenantBase):
    organization_id: UUID
    user_id: Optional[UUID] = None  # Loose reference to user (No FK)
    created_by: Optional[UUID] = None


class TenantSchema(TenantBase):
    id: UUID
    organization_id: UUID
    user_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. LEASES SCHEMAS
# ==========================================
class LeaseBase(BaseModel):
    start_date: str
    end_date: str
    monthly_rent: float
    status: str = "Active"


class LeaseCreate(LeaseBase):
    organization_id: UUID
    unit_id: UUID
    tenant_id: UUID
    created_by: Optional[UUID] = None


class LeaseSchema(LeaseBase):
    id: UUID
    organization_id: UUID
    unit_id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. INVOICES SCHEMAS
# ==========================================
class InvoiceBase(BaseModel):
    amount: float
    due_date: str
    status: str = "Unpaid"


class InvoiceCreate(InvoiceBase):
    organization_id: UUID
    lease_id: UUID
    created_by: Optional[UUID] = None


class InvoiceSchema(InvoiceBase):
    id: UUID
    organization_id: UUID
    lease_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 6. MAINTENANCE SCHEMAS
# ==========================================
class MaintenanceBase(BaseModel):
    description: str
    priority: str = "Medium"
    status: str = "Open"


class MaintenanceCreate(MaintenanceBase):
    organization_id: UUID
    unit_id: UUID
    created_by: Optional[UUID] = None


class MaintenanceUpdate(BaseModel):
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None


class MaintenanceSchema(MaintenanceBase):
    id: UUID
    organization_id: UUID
    unit_id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)