from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid import UUID
from datetime import datetime, date
from typing import Optional, List, Union, Dict, Any


# ==========================================
# 0. GLOBAL HELPER FOR OPTIONAL UUIDS
# ==========================================
def convert_empty_to_none(v: Any) -> Optional[UUID]:
    if v == "" or v == "null" or v is None:
        return None
    if isinstance(v, str):
        try:
            return UUID(v)
        except ValueError:
            return None
    return v


# ==========================================
# 0. CORE USER & ORG SCHEMAS
# ==========================================
class OrganizationBase(BaseModel):
    name: str


class OrganizationSchema(OrganizationBase):
    id: UUID
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    email: str
    name: Optional[str] = "Admin User"
    full_name: Optional[str] = None
    phone: Optional[str] = None
    role: str = "admin"
    avatar: Optional[str] = "JD"
    is_active: bool = True


class UserCreate(UserBase):
    organization_id: Optional[UUID] = None
    password: Optional[str] = None

    @field_validator('organization_id', mode='before')
    @classmethod
    def clean_uuid(cls, v):
        return convert_empty_to_none(v)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    avatar: Optional[str] = None
    is_active: Optional[bool] = None


class UserSchema(UserBase):
    id: UUID
    organization_id: Optional[UUID] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 1. PROPERTIES SCHEMAS
# ==========================================
class PropertyBase(BaseModel):
    code: str
    name: str
    tct_number: Optional[str] = None
    type: str = "Residential"
    location: str
    units_count: Optional[int] = 0
    status: str = "Active"


class PropertyCreate(PropertyBase):
    organization_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class PropertyUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    tct_number: Optional[str] = None
    type: Optional[str] = None
    location: Optional[str] = None
    units_count: Optional[int] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class PropertySchema(PropertyBase):
    id: UUID
    organization_id: UUID
    tct_number: Optional[str] = None
    units_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 2. BUILDINGS SCHEMAS
# ==========================================
class BuildingBase(BaseModel):
    code: str
    name: str
    floors: int = 1
    total_units: int = 0
    floor_distribution: Optional[Dict[str, Any]] = None
    status: str = "ACTIVE"


class BuildingCreate(BuildingBase):
    organization_id: Optional[UUID] = None
    property_id: UUID
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'property_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class BuildingUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    floors: Optional[int] = None
    total_units: Optional[int] = None
    floor_distribution: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class BuildingSchema(BuildingBase):
    id: UUID
    organization_id: UUID
    property_id: UUID
    floor_distribution: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. UNITS SCHEMAS
# ==========================================
class UnitBase(BaseModel):
    unit_no: str
    type: str = "1BR"
    floor: Optional[str] = "1st Floor"
    sqm: Optional[float] = 45.0
    rent: float = 0.0
    status: str = "VACANT"
    subtitle: Optional[str] = None


class UnitCreate(UnitBase):
    organization_id: Optional[UUID] = None
    property_id: Optional[UUID] = None
    building_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'property_id', 'building_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class UnitUpdate(BaseModel):
    unit_no: Optional[str] = None
    type: Optional[str] = None
    floor: Optional[str] = None
    sqm: Optional[float] = None
    rent: Optional[float] = None
    rent_amount: Optional[float] = None
    status: Optional[str] = None
    subtitle: Optional[str] = None
    building_id: Optional[UUID] = None
    property_id: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    @field_validator('building_id', 'property_id', 'updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class UnitSchema(UnitBase):
    id: UUID
    organization_id: UUID
    property_id: UUID
    building_id: Optional[UUID] = None
    floor: str = "1st Floor"
    sqm: Optional[float] = 45.0
    subtitle: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 4. TENANTS SCHEMAS
# ==========================================
class TenantBase(BaseModel):
    name: str
    email: str
    phone: str
    tnt_id: Optional[str] = None
    type: str = "Individual"
    status: str = "Active"


class TenantCreate(TenantBase):
    organization_id: Optional[UUID] = None
    user_id: Optional[UUID] = None  # Loose reference to user (No FK)
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'user_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    tnt_id: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class TenantSchema(TenantBase):
    id: UUID
    organization_id: UUID
    tnt_id: Optional[str] = None
    type: str = "Individual"
    user_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 5. OWNERS & FRACTIONAL EQUITY SCHEMAS
# ==========================================
class OwnerBase(BaseModel):
    name: str
    email: str
    phone: str
    own_id: Optional[str] = None
    type: str = "INDIVIDUAL"
    status: str = "ACTIVE"


class OwnerCreate(OwnerBase):
    organization_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'user_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class OwnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    own_id: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class OwnerSchema(OwnerBase):
    id: UUID
    organization_id: UUID
    own_id: Optional[str] = None
    user_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class PropertyOwnershipBase(BaseModel):
    share_percent: float = 100.00
    role: str = "Primary"


class PropertyOwnershipCreate(PropertyOwnershipBase):
    organization_id: Optional[UUID] = None
    property_id: UUID
    owner_id: UUID
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'property_id', 'owner_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class PropertyOwnershipUpdate(BaseModel):
    share_percent: Optional[float] = None
    role: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class PropertyOwnershipSchema(PropertyOwnershipBase):
    id: UUID
    organization_id: UUID
    property_id: UUID
    owner_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 6. LEASES SCHEMAS
# ==========================================
class LeaseBase(BaseModel):
    start_date: Union[date, str]
    end_date: Union[date, str]
    rent: float = 0.0
    monthly_rent: Optional[float] = None
    deposit: Optional[float] = 0.0
    lease_id: Optional[str] = None
    status: str = "ACTIVE"


class LeaseCreate(LeaseBase):
    organization_id: Optional[UUID] = None
    unit_id: UUID
    tenant_id: UUID
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'unit_id', 'tenant_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class LeaseUpdate(BaseModel):
    start_date: Optional[Union[date, str]] = None
    end_date: Optional[Union[date, str]] = None
    rent: Optional[float] = None
    monthly_rent: Optional[float] = None
    deposit: Optional[float] = None
    lease_id: Optional[str] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class LeaseSchema(LeaseBase):
    id: UUID
    organization_id: UUID
    unit_id: UUID
    tenant_id: UUID
    lease_id: Optional[str] = None
    rent: float = 0.0
    deposit: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 7. INVOICES & BILLING SCHEMAS
# ==========================================
class InvoiceBase(BaseModel):
    amount: float
    due_date: Union[date, str]
    invoice_id: Optional[str] = None
    type: str = "Monthly Base Rent"
    sub: Optional[str] = None
    category_type: str = "Rent"
    status: str = "Unpaid"
    channel: str = "Pending Payment"
    ref_no: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    organization_id: Optional[UUID] = None
    lease_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'lease_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class InvoiceUpdate(BaseModel):
    amount: Optional[float] = None
    due_date: Optional[Union[date, str]] = None
    type: Optional[str] = None
    sub: Optional[str] = None
    category_type: Optional[str] = None
    status: Optional[str] = None
    channel: Optional[str] = None
    ref_no: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class InvoiceSchema(InvoiceBase):
    id: UUID
    organization_id: UUID
    lease_id: Optional[UUID] = None
    invoice_id: Optional[str] = None
    type: str = "Monthly Base Rent"
    sub: Optional[str] = None
    category_type: str = "Rent"
    channel: str = "Pending Payment"
    ref_no: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 8. MASTER TRANSACTIONS SCHEMAS
# ==========================================
class TransactionBase(BaseModel):
    txn_id: str
    ref_code: str
    payer: str
    property_location: str
    category: str
    direction: str = "INFLOW"
    gross_amount: float
    channel: str = "Bank Transfer"
    status: str = "Pending Audit"


class TransactionCreate(TransactionBase):
    organization_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class TransactionUpdate(BaseModel):
    status: Optional[str] = None
    gross_amount: Optional[float] = None
    channel: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class TransactionSchema(TransactionBase):
    id: UUID
    organization_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 9. MAINTENANCE SCHEMAS
# ==========================================
class MaintenanceBase(BaseModel):
    description: str
    title: Optional[str] = "Maintenance Request"
    category: Optional[str] = "General"
    tenant_name: Optional[str] = "Tenant"
    priority: str = "Medium"
    status: str = "Open"
    technician: Optional[str] = "Unassigned"
    cost: Optional[float] = 0.0


class MaintenanceCreate(MaintenanceBase):
    organization_id: Optional[UUID] = None
    unit_id: Optional[UUID] = None
    ticket_id: Optional[str] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'unit_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class MaintenanceUpdate(BaseModel):
    description: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    technician: Optional[str] = None
    cost: Optional[float] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class MaintenanceSchema(MaintenanceBase):
    id: UUID
    organization_id: UUID
    unit_id: Optional[UUID] = None
    ticket_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 10. SUB-METER READINGS SCHEMAS
# ==========================================
class MeterReadingBase(BaseModel):
    tenant_name: str
    unit_location: str
    utility: str = "Meralco"
    serial: str
    prev_dial: float = 0.0
    curr_dial: float = 0.0
    consumption: float = 0.0
    unit_symbol: str = "kWh"
    period: str = "August 2026"
    status: str = "Unbilled / Ready for Billing"


class MeterReadingCreate(MeterReadingBase):
    organization_id: Optional[UUID] = None
    unit_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'unit_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class MeterReadingUpdate(BaseModel):
    curr_dial: Optional[float] = None
    consumption: Optional[float] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class MeterReadingSchema(MeterReadingBase):
    id: UUID
    organization_id: UUID
    unit_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 11. INSPECTIONS & CHECKLISTS SCHEMAS
# ==========================================
class InspectionBase(BaseModel):
    inspection_id: str
    unit_name: str
    property_info: str
    tenant: str
    type: str = "Move-in"
    date: Union[date, str]
    inspector: str = "Property Admin"
    status: str = "Pending"
    notes: Optional[str] = None


class InspectionCreate(InspectionBase):
    organization_id: Optional[UUID] = None
    unit_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'unit_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class InspectionUpdate(BaseModel):
    status: Optional[str] = None
    inspector: Optional[str] = None
    notes: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class InspectionSchema(InspectionBase):
    id: UUID
    organization_id: UUID
    unit_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 12. LEGAL VAULT & DOCUMENTS SCHEMAS
# ==========================================
class DocumentBase(BaseModel):
    doc_id: str
    title: str
    file_type: str
    entity_name: str
    entity_sub: Optional[str] = None
    type: str = "Title"
    uploader: str = "Property Admin"
    date: Union[date, str]
    status: str = "Active"


class DocumentCreate(DocumentBase):
    organization_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class DocumentSchema(DocumentBase):
    id: UUID
    organization_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 13. NOTIFICATIONS SCHEMAS
# ==========================================
class NotificationBase(BaseModel):
    pov: str = "admin"
    category: str = "system"
    status: str = "unread"
    is_read: bool = False
    title: str
    description: str
    property: Optional[str] = None
    tag: Optional[str] = None
    urgent: bool = False


class NotificationCreate(NotificationBase):
    organization_id: Optional[UUID] = None
    created_by: Optional[UUID] = None

    @field_validator('organization_id', 'created_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class NotificationUpdate(BaseModel):
    status: Optional[str] = None
    is_read: Optional[bool] = None
    updated_by: Optional[UUID] = None

    @field_validator('updated_by', mode='before')
    @classmethod
    def clean_uuids(cls, v):
        return convert_empty_to_none(v)


class NotificationSchema(NotificationBase):
    id: UUID
    organization_id: UUID
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)