import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

# Default Organization UUID matching schema.sql and seed.py
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Sunrise Property Group")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/tenants/ - Read tenants scoped by organization_id with filter & search
@router.get("/", response_model=List[schemas.TenantSchema])
def read_tenants(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Tenant).where(models.Tenant.organization_id == organization_id)

    if status_filter:
        stmt = stmt.where(models.Tenant.status.ilike(f"%{status_filter}%"))
    if type_filter and hasattr(models.Tenant, "type"):
        stmt = stmt.where(models.Tenant.type.ilike(f"%{type_filter}%"))

    if search:
        search_terms = []
        if hasattr(models.Tenant, "name"):
            search_terms.append(models.Tenant.name.ilike(f"%{search}%"))
        if hasattr(models.Tenant, "email"):
            search_terms.append(models.Tenant.email.ilike(f"%{search}%"))
        if hasattr(models.Tenant, "phone"):
            search_terms.append(models.Tenant.phone.ilike(f"%{search}%"))
        if hasattr(models.Tenant, "tnt_id"):
            search_terms.append(models.Tenant.tnt_id.ilike(f"%{search}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    tenants = list(db.scalars(stmt).all())

    # Seed default sandbox tenant if DB is empty for this org
    if not tenants and not search and not status_filter and not type_filter:
        default_tenant_data = {
            "id": uuid.uuid4(),
            "organization_id": organization_id,
            "name": "Maria Santos",
            "email": "maria.santos@tenant.ph",
            "phone": "09171234567",
            "status": "Active"
        }
        if hasattr(models.Tenant, "tnt_id"):
            default_tenant_data["tnt_id"] = "TNT-1001"
        if hasattr(models.Tenant, "type"):
            default_tenant_data["type"] = "Individual"

        default_tenants = [models.Tenant(**default_tenant_data)]
        db.add_all(default_tenants)
        db.commit()
        tenants = list(db.scalars(stmt).all())

    return tenants


# 2. POST /api/tenants/ - Create a new tenant with org-scoped email duplicate check
@router.post("/", response_model=schemas.TenantSchema, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant_in: schemas.TenantCreate, db: Session = Depends(get_db)):
    org_id = getattr(tenant_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    # Org-scoped email duplicate check
    if tenant_in.email:
        existing_stmt = select(models.Tenant).where(
            models.Tenant.organization_id == org_id,
            models.Tenant.email == tenant_in.email
        )
        existing = db.scalar(existing_stmt)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant with email '{tenant_in.email}' already exists in this organization."
            )

    tenant_data = tenant_in.dict(exclude_unset=True)
    if "id" not in tenant_data or not tenant_data["id"]:
        tenant_data["id"] = uuid.uuid4()
    if "organization_id" not in tenant_data:
        tenant_data["organization_id"] = org_id
    if "tnt_id" not in tenant_data and hasattr(models.Tenant, "tnt_id"):
        tenant_data["tnt_id"] = f"TNT-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    db_tenant = models.Tenant(**tenant_data)
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant


# 3. GET /api/tenants/{tenant_id} - Fetch a single tenant by UUID or TNT Code
@router.get("/{tenant_id}", response_model=schemas.TenantSchema)
def get_tenant(
    tenant_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(tenant_id)
        stmt = select(models.Tenant).where(
            models.Tenant.id == parsed_uuid,
            models.Tenant.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Tenant, "tnt_id"):
            stmt = select(models.Tenant).where(
                models.Tenant.tnt_id == tenant_id,
                models.Tenant.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant identifier format."
            )

    tenant = db.scalar(stmt)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found."
        )

    return tenant


# 4. PUT /api/tenants/{tenant_id} - Update tenant profile, contact, or status
@router.put("/{tenant_id}", response_model=schemas.TenantSchema)
@router.patch("/{tenant_id}", response_model=schemas.TenantSchema)
def update_tenant(
    tenant_id: str,
    tenant_update: schemas.TenantUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(tenant_id)
        stmt = select(models.Tenant).where(
            models.Tenant.id == parsed_uuid,
            models.Tenant.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Tenant, "tnt_id"):
            stmt = select(models.Tenant).where(
                models.Tenant.tnt_id == tenant_id,
                models.Tenant.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant identifier format."
            )

    db_tenant = db.scalar(stmt)
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found."
        )

    update_data = tenant_update.dict(exclude_unset=True)

    # If updating email, check for duplicate within organization
    if "email" in update_data and update_data["email"] and update_data["email"] != db_tenant.email:
        email_check = db.scalar(
            select(models.Tenant).where(
                models.Tenant.organization_id == organization_id,
                models.Tenant.email == update_data["email"],
                models.Tenant.id != db_tenant.id
            )
        )
        if email_check:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{update_data['email']}' is already assigned to another tenant."
            )

    for field, value in update_data.items():
        if hasattr(db_tenant, field):
            setattr(db_tenant, field, value)

    db.commit()
    db.refresh(db_tenant)
    return db_tenant


# 5. DELETE /api/tenants/{tenant_id} - Archive or remove tenant record
@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(tenant_id)
        stmt = select(models.Tenant).where(
            models.Tenant.id == parsed_uuid,
            models.Tenant.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Tenant, "tnt_id"):
            stmt = select(models.Tenant).where(
                models.Tenant.tnt_id == tenant_id,
                models.Tenant.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant identifier format."
            )

    db_tenant = db.scalar(stmt)
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found."
        )

    db.delete(db_tenant)
    db.commit()
    return None