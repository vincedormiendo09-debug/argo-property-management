import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

# Default Organization UUID for local sandbox testing
DEFAULT_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Default Sandbox Org")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/tenants/ - Read tenants scoped by organization_id
@router.get("/", response_model=List[schemas.TenantSchema])
def read_tenants(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Tenant).where(models.Tenant.organization_id == organization_id)
    tenants = list(db.scalars(stmt).all())

    # Seed default sandbox tenant if DB is empty for this org
    if not tenants:
        default_tenants = [
            models.Tenant(
                id=uuid.uuid4(),
                organization_id=organization_id,
                name="Maria Santos",
                email="maria.santos@email.com",
                phone="+63 917 123 4567",
                status="Active"
            )
        ]
        db.add_all(default_tenants)
        db.commit()
        tenants = list(db.scalars(stmt).all())

    return tenants


# 2. POST /api/tenants/ - Create a new tenant with org-scoped email check
@router.post("/", response_model=schemas.TenantSchema, status_code=status.HTTP_201_CREATED)
def create_tenant(tenant_in: schemas.TenantCreate, db: Session = Depends(get_db)):
    ensure_sandbox_organization(db, tenant_in.organization_id)

    # Org-scoped email duplicate check
    if tenant_in.email:
        existing_stmt = select(models.Tenant).where(
            models.Tenant.organization_id == tenant_in.organization_id,
            models.Tenant.email == tenant_in.email
        )
        existing = db.scalar(existing_stmt)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant with email '{tenant_in.email}' already exists in this organization."
            )

    db_tenant = models.Tenant(
        id=uuid.uuid4(),
        organization_id=tenant_in.organization_id,
        user_id=tenant_in.user_id,
        name=tenant_in.name,
        email=tenant_in.email,
        phone=tenant_in.phone,
        status=tenant_in.status,
        created_by=tenant_in.created_by
    )

    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)
    return db_tenant


# 3. GET /api/tenants/{tenant_id} - Fetch a single tenant by UUID
@router.get("/{tenant_id}", response_model=schemas.TenantSchema)
def get_tenant(
    tenant_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.Tenant).where(
        models.Tenant.id == tenant_id,
        models.Tenant.organization_id == organization_id
    )
    tenant = db.scalar(stmt)

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found."
        )

    return tenant