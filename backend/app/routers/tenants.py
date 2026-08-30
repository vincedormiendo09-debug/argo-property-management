import uuid
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# Default Organization UUID matching schema.sql
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/tenants/ - Read real tenants from database with filter & search
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
        if hasattr(models.Tenant, "full_name"):
            search_terms.append(models.Tenant.full_name.ilike(f"%{search}%"))
        if hasattr(models.Tenant, "email"):
            search_terms.append(models.Tenant.email.ilike(f"%{search}%"))
        if hasattr(models.Tenant, "phone"):
            search_terms.append(models.Tenant.phone.ilike(f"%{search}%"))
        if hasattr(models.Tenant, "tnt_id"):
            search_terms.append(models.Tenant.tnt_id.ilike(f"%{search}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    return list(db.scalars(stmt).all())


# 2. POST /api/tenants/ - Create a new tenant
@router.post("/", response_model=schemas.TenantSchema, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant_in: schemas.TenantCreate, db: Session = Depends(get_db)):
    org_id = getattr(tenant_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    clean_email = tenant_in.email.lower().strip() if tenant_in.email else None

    # Org-scoped email duplicate check
    if clean_email:
        existing = db.scalar(
            select(models.Tenant).where(
                models.Tenant.organization_id == org_id,
                models.Tenant.email.ilike(clean_email)
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant with email '{clean_email}' already exists in this organization."
            )

    tenant_data = tenant_in.model_dump(exclude_unset=True) if hasattr(tenant_in, "model_dump") else tenant_in.dict(exclude_unset=True)
    if "id" not in tenant_data or not tenant_data["id"]:
        tenant_data["id"] = uuid.uuid4()
    if "organization_id" not in tenant_data or not tenant_data["organization_id"]:
        tenant_data["organization_id"] = org_id
    if clean_email:
        tenant_data["email"] = clean_email
    if "tnt_id" not in tenant_data and hasattr(models.Tenant, "tnt_id"):
        tenant_data["tnt_id"] = f"TNT-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"
    if "status" not in tenant_data or not tenant_data["status"]:
        tenant_data["status"] = "Active"

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


# 4. PUT / PATCH /api/tenants/{tenant_id} - Update tenant record
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

    update_data = tenant_update.model_dump(exclude_unset=True) if hasattr(tenant_update, "model_dump") else tenant_update.dict(exclude_unset=True)

    if "email" in update_data and update_data["email"]:
        clean_update_email = update_data["email"].lower().strip()
        update_data["email"] = clean_update_email
        if clean_update_email != (db_tenant.email or "").lower().strip():
            email_check = db.scalar(
                select(models.Tenant).where(
                    models.Tenant.organization_id == organization_id,
                    models.Tenant.email.ilike(clean_update_email),
                    models.Tenant.id != db_tenant.id
                )
            )
            if email_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Email '{clean_update_email}' is already assigned to another tenant."
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