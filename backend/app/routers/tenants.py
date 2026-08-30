import uuid
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# Default Organization UUID matching schema.sql
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures the Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def find_tenant_by_identifier(db: Session, tenant_id: str, organization_id: uuid.UUID):
    """Robustly locates a tenant by UUID, user_id, custom TNT string, email, or virtual user match."""
    clean_id = tenant_id.strip()
    try:
        parsed_uuid = uuid.UUID(clean_id)
        tenant = db.scalar(
            select(models.Tenant).where(
                or_(
                    models.Tenant.id == parsed_uuid,
                    models.Tenant.user_id == parsed_uuid
                ),
                models.Tenant.organization_id == organization_id
            )
        )
        if tenant:
            return tenant
    except ValueError:
        pass

    if hasattr(models.Tenant, "tnt_id"):
        tenant = db.scalar(
            select(models.Tenant).where(
                models.Tenant.tnt_id.ilike(clean_id),
                models.Tenant.organization_id == organization_id
            )
        )
        if tenant:
            return tenant

    # Fallback lookup by email
    tenant = db.scalar(
        select(models.Tenant).where(
            models.Tenant.email.ilike(clean_id),
            models.Tenant.organization_id == organization_id
        )
    )
    if tenant:
        return tenant

    # Check registered users table directly if not found in tenants table
    user = db.scalar(
        select(models.User).where(
            models.User.email.ilike(clean_id),
            models.User.organization_id == organization_id
        )
    )
    if user:
        virtual_tenant = models.Tenant(
            id=user.id,
            organization_id=organization_id,
            name=user.name or user.full_name or "Registered Tenant",
            email=user.email,
            phone=user.phone or "",
            status="Active"
        )
        if hasattr(virtual_tenant, "user_id"):
            virtual_tenant.user_id = user.id
        if hasattr(virtual_tenant, "unit"):
            virtual_tenant.unit = "No Current Unit"
        if hasattr(virtual_tenant, "type"):
            virtual_tenant.type = "Individual"
        return virtual_tenant

    return None


# 1. GET /api/tenants/ - Read real tenants with on-the-fly user merging and search
@router.get("/", response_model=List[schemas.TenantSchema])
def read_tenants(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    # 1. Fetch existing explicit tenant profiles
    tenants = list(db.scalars(select(models.Tenant).where(models.Tenant.organization_id == organization_id)).all())

    existing_user_ids = {str(t.user_id) for t in tenants if getattr(t, 'user_id', None)}
    existing_emails = {(t.email or '').lower().strip() for t in tenants if getattr(t, 'email', None)}

    # 2. Directly grab ALL users registered with client, tenant, or resident roles from index.html
    tenant_users = db.scalars(
        select(models.User).where(
            models.User.organization_id == organization_id,
            or_(
                models.User.role.ilike("%client%"),
                models.User.role.ilike("%tenant%"),
                models.User.role.ilike("%resident%")
            )
        )
    ).all()

    # 3. Merge them on the fly into the response feed so they appear instantly
    for u in tenant_users:
        u_email = (u.email or '').lower().strip()
        if str(u.id) not in existing_user_ids and u_email not in existing_emails:
            uname = getattr(u, 'name', None) or getattr(u, 'full_name', None) or 'Registered Tenant'
            uphone = getattr(u, 'phone', '') or ''

            virtual_tenant = models.Tenant(
                id=u.id,
                organization_id=organization_id,
                name=uname,
                email=u.email,
                phone=uphone,
                status='Active'
            )
            if hasattr(virtual_tenant, 'user_id'):
                virtual_tenant.user_id = u.id
            if hasattr(virtual_tenant, 'tnt_id'):
                virtual_tenant.tnt_id = f"TNT-{str(u.id)[:6].upper()}"
            if hasattr(virtual_tenant, 'unit'):
                virtual_tenant.unit = 'No Current Unit'
            if hasattr(virtual_tenant, 'type'):
                virtual_tenant.type = 'Individual'

            tenants.append(virtual_tenant)

    if status_filter:
        s_filter = status_filter.strip().lower()
        tenants = [t for t in tenants if s_filter in (t.status or '').lower()]

    if type_filter:
        t_filter = type_filter.strip().lower()
        tenants = [t for t in tenants if t_filter in (t.type or '').lower()]

    if search:
        s_term = search.strip().lower()
        tenants = [t for t in tenants if s_term in (t.name or '').lower() or s_term in (t.email or '').lower()]

    return tenants


# 2. POST /api/tenants/ - Create a new tenant
@router.post("/", response_model=schemas.TenantSchema, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant_in: schemas.TenantCreate, db: Session = Depends(get_db)):
    org_id = getattr(tenant_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    clean_email = tenant_in.email.lower().strip() if tenant_in.email else None
    tnt_id = getattr(tenant_in, "tnt_id", None) or f"TNT-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    # Scoped duplicate check
    duplicate_filters = []
    if tnt_id and hasattr(models.Tenant, "tnt_id"):
        duplicate_filters.append(models.Tenant.tnt_id.ilike(tnt_id))
    if clean_email and hasattr(models.Tenant, "email"):
        duplicate_filters.append(models.Tenant.email.ilike(clean_email))

    if duplicate_filters:
        existing = db.scalar(
            select(models.Tenant).where(
                models.Tenant.organization_id == org_id,
                or_(*duplicate_filters)
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A tenant with this ID or email already exists in this organization."
            )

    tenant_data = tenant_in.model_dump(exclude_unset=True) if hasattr(tenant_in, "model_dump") else tenant_in.dict(exclude_unset=True)
    if "id" not in tenant_data or not tenant_data["id"]:
        tenant_data["id"] = uuid.uuid4()
    tenant_data["organization_id"] = org_id
    if clean_email:
        tenant_data["email"] = clean_email
    if "tnt_id" not in tenant_data and hasattr(models.Tenant, "tnt_id"):
        tenant_data["tnt_id"] = tnt_id
    if "status" not in tenant_data or not tenant_data["status"]:
        tenant_data["status"] = "Active"

    db_tenant = models.Tenant(**tenant_data)
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant


# 3. GET /api/tenants/{tenant_id} - Fetch a single tenant
@router.get("/{tenant_id}", response_model=schemas.TenantSchema)
def get_tenant(
    tenant_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    tenant = find_tenant_by_identifier(db, tenant_id, organization_id)
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
    db_tenant = find_tenant_by_identifier(db, tenant_id, organization_id)
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


# 5. DELETE /api/tenants/{tenant_id} - Safe remove tenant record
@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_tenant = find_tenant_by_identifier(db, tenant_id, organization_id)
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found."
        )

    try:
        db.delete(db_tenant)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete tenant because they are referenced by active leases or billing records."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting tenant: {str(e)}"
        )

    return None