import uuid
import logging
from datetime import datetime
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def parse_org_id(org_id_raw: Optional[str]) -> uuid.UUID:
    """Safely converts string, null, or undefined organization IDs to valid UUIDs."""
    if not org_id_raw:
        return DEFAULT_ORG_ID
    clean = str(org_id_raw).strip().lower()
    if clean in ("undefined", "null", ""):
        return DEFAULT_ORG_ID
    try:
        return uuid.UUID(clean)
    except Exception:
        return DEFAULT_ORG_ID


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures the Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def find_tenant_by_identifier(db: Session, tenant_id: str, organization_id: uuid.UUID):
    """Robustly locates a tenant by UUID, user_id, custom TNT code, email, or User record."""
    clean_id = tenant_id.strip()

    # 1. Search Tenant table by UUID (id or user_id)
    try:
        parsed_uuid = uuid.UUID(clean_id)
        tenant = db.scalar(
            select(models.Tenant).where(
                or_(
                    models.Tenant.id == parsed_uuid,
                    models.Tenant.user_id == parsed_uuid
                ),
                or_(
                    models.Tenant.organization_id == organization_id,
                    models.Tenant.organization_id.is_(None)
                )
            )
        )
        if tenant:
            return tenant
    except ValueError:
        pass

    # 2. Search Tenant table by custom identifier code (tenant_id or tnt_id)
    if hasattr(models.Tenant, "tenant_id"):
        tenant = db.scalar(
            select(models.Tenant).where(
                models.Tenant.tenant_id.ilike(clean_id),
                or_(
                    models.Tenant.organization_id == organization_id,
                    models.Tenant.organization_id.is_(None)
                )
            )
        )
        if tenant:
            return tenant

    if hasattr(models.Tenant, "tnt_id"):
        tenant = db.scalar(
            select(models.Tenant).where(
                models.Tenant.tnt_id.ilike(clean_id),
                or_(
                    models.Tenant.organization_id == organization_id,
                    models.Tenant.organization_id.is_(None)
                )
            )
        )
        if tenant:
            return tenant

    # 3. Search Tenant table by email
    tenant = db.scalar(
        select(models.Tenant).where(
            models.Tenant.email.ilike(clean_id),
            or_(
                models.Tenant.organization_id == organization_id,
                models.Tenant.organization_id.is_(None)
            )
        )
    )
    if tenant:
        return tenant

    # 4. Fallback: Search User table directly if role is client/tenant
    user = None
    try:
        user_uuid = uuid.UUID(clean_id)
        user = db.scalar(
            select(models.User).where(
                models.User.id == user_uuid,
                or_(
                    models.User.role.ilike("%client%"),
                    models.User.role.ilike("%tenant%"),
                    models.User.role.ilike("%resident%")
                )
            )
        )
    except ValueError:
        pass

    if not user:
        user = db.scalar(
            select(models.User).where(
                models.User.email.ilike(clean_id),
                or_(
                    models.User.role.ilike("%client%"),
                    models.User.role.ilike("%tenant%"),
                    models.User.role.ilike("%resident%")
                )
            )
        )

    if user:
        t_id = str(user.id)
        virtual_tenant = models.Tenant(
            id=user.id,
            organization_id=organization_id,
            name=user.name or user.full_name or "Resident Tenant",
            email=user.email,
            phone=user.phone or "",
            status="Active"
        )
        if hasattr(virtual_tenant, "user_id"):
            virtual_tenant.user_id = user.id
        if hasattr(virtual_tenant, "tenant_id"):
            virtual_tenant.tenant_id = f"TNT-{t_id[:6].upper()}"
        if hasattr(virtual_tenant, "tnt_id"):
            virtual_tenant.tnt_id = f"TNT-{t_id[:6].upper()}"
        if hasattr(virtual_tenant, "unit"):
            virtual_tenant.unit = "Unassigned"
        if hasattr(virtual_tenant, "type"):
            virtual_tenant.type = "Individual"
        return virtual_tenant

    return None


# ---------------------------------------------------------------------
# 1. GET TENANTS (Supports both /api/tenants and /api/tenants/)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_tenants(
    organization_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Returns database tenant profiles merged with registered client/tenant user accounts.
    """
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    results: List[Dict[str, Any]] = []
    seen_identifiers = set()

    # 1. Query explicit 'tenants' table records from Neon DB
    try:
        db_tenants = list(db.scalars(
            select(models.Tenant).where(
                or_(
                    models.Tenant.organization_id == org_id,
                    models.Tenant.organization_id.is_(None)
                )
            )
        ).all())

        for t in db_tenants:
            t_id = str(getattr(t, "id", "") or "")
            t_user_id = str(getattr(t, "user_id", "") or "")
            t_email = (getattr(t, "email", "") or "").lower().strip()
            t_name = getattr(t, "name", "") or getattr(t, "full_name", "") or "Resident Tenant"
            code = getattr(t, "tenant_id", None) or getattr(t, "tnt_id", None) or f"TNT-{t_id[:6].upper()}"

            if t_id:
                seen_identifiers.add(t_id)
            if t_user_id:
                seen_identifiers.add(t_user_id)
            if t_email:
                seen_identifiers.add(t_email)

            results.append({
                "id": t_id,
                "user_id": t_user_id or t_id,
                "tenant_id": code,
                "tnt_id": code,
                "name": t_name,
                "full_name": t_name,
                "email": getattr(t, "email", "") or "",
                "phone": getattr(t, "phone", "") or "",
                "type": getattr(t, "type", "Individual") or "Individual",
                "unit": getattr(t, "unit", "") or "Unassigned",
                "lease_id": getattr(t, "lease_id", None),
                "emergency_contact": getattr(t, "emergency_contact", ""),
                "status": getattr(t, "status", "Active") or "Active"
            })
    except Exception as e:
        logger.warning(f"Notice querying tenants table: {e}")

    # 2. Query registered users with active client/tenant/resident roles
    try:
        tenant_users = list(db.scalars(
            select(models.User).where(
                or_(
                    models.User.role.ilike("%client%"),
                    models.User.role.ilike("%tenant%"),
                    models.User.role.ilike("%resident%")
                )
            )
        ).all())

        for u in tenant_users:
            u_id = str(getattr(u, "id", "") or "")
            u_email = (getattr(u, "email", "") or "").lower().strip()
            u_name = getattr(u, "name", "") or getattr(u, "full_name", "") or "Resident Tenant"

            if u_id not in seen_identifiers and u_email not in seen_identifiers:
                if u_id:
                    seen_identifiers.add(u_id)
                if u_email:
                    seen_identifiers.add(u_email)

                code = f"TNT-{u_id[:6].upper()}"
                results.append({
                    "id": u_id,
                    "user_id": u_id,
                    "tenant_id": code,
                    "tnt_id": code,
                    "name": u_name,
                    "full_name": u_name,
                    "email": getattr(u, "email", "") or "",
                    "phone": getattr(u, "phone", "") or "",
                    "type": "Individual",
                    "unit": "Unassigned",
                    "lease_id": None,
                    "emergency_contact": "",
                    "status": "Active"
                })
    except Exception as e:
        logger.warning(f"Notice querying users table: {e}")

    # 3. Apply optional filters
    if status_filter:
        s_filt = status_filter.strip().lower()
        results = [r for r in results if s_filt in (r.get("status") or "").lower()]

    if type_filter:
        t_filt = type_filter.strip().lower()
        results = [r for r in results if t_filt in (r.get("type") or "").lower()]

    if search:
        s_term = search.strip().lower()
        results = [
            r for r in results
            if s_term in (r.get("name") or "").lower()
            or s_term in (r.get("full_name") or "").lower()
            or s_term in (r.get("email") or "").lower()
            or s_term in (r.get("phone") or "").lower()
            or s_term in (r.get("tenant_id") or "").lower()
            or s_term in (r.get("unit") or "").lower()
        ]

    return results


# ---------------------------------------------------------------------
# 2. CREATE TENANT (Matches POST /api/tenants & POST /api/tenants/)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(tenant_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    name = (tenant_in.get("name") or tenant_in.get("full_name") or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant name is required."
        )

    clean_email = (tenant_in.get("email") or "").strip().lower() or None
    code = (tenant_in.get("tenant_id") or tenant_in.get("tnt_id") or f"TNT-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}").strip()

    duplicate_filters = []
    if hasattr(models.Tenant, "tenant_id"):
        duplicate_filters.append(models.Tenant.tenant_id.ilike(code))
    if hasattr(models.Tenant, "tnt_id"):
        duplicate_filters.append(models.Tenant.tnt_id.ilike(code))
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
            code = f"{code}-{str(uuid.uuid4())[:3].upper()}"

    new_id = uuid.uuid4()
    if tenant_in.get("id"):
        try:
            new_id = uuid.UUID(str(tenant_in["id"]))
        except ValueError:
            pass

    tenant_data = {
        "id": new_id,
        "organization_id": org_id,
        "name": name,
        "email": clean_email or "",
        "phone": tenant_in.get("phone") or "",
        "type": tenant_in.get("type") or "Individual",
        "status": tenant_in.get("status") or "Active",
        "emergency_contact": tenant_in.get("emergency_contact") or ""
    }

    if hasattr(models.Tenant, "tenant_id"):
        tenant_data["tenant_id"] = code
    if hasattr(models.Tenant, "tnt_id"):
        tenant_data["tnt_id"] = code
    if hasattr(models.Tenant, "unit") and tenant_in.get("unit"):
        tenant_data["unit"] = str(tenant_in["unit"])
    if hasattr(models.Tenant, "lease_id") and tenant_in.get("lease_id"):
        tenant_data["lease_id"] = str(tenant_in["lease_id"])

    db_tenant = models.Tenant(**tenant_data)
    db.add(db_tenant)
    db.commit()
    db.refresh(db_tenant)

    return {
        "id": str(db_tenant.id),
        "organization_id": str(db_tenant.organization_id),
        "tenant_id": code,
        "name": db_tenant.name,
        "email": db_tenant.email,
        "phone": db_tenant.phone,
        "type": getattr(db_tenant, "type", "Individual"),
        "status": db_tenant.status
    }


# ---------------------------------------------------------------------
# 3. GET SINGLE TENANT
# ---------------------------------------------------------------------
@router.get("/{tenant_id}")
@router.get("/{tenant_id}/")
def get_tenant(
    tenant_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    tenant = find_tenant_by_identifier(db, tenant_id, org_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found."
        )

    t_id = str(getattr(tenant, "id", "") or "")
    code = getattr(tenant, "tenant_id", None) or getattr(tenant, "tnt_id", None) or f"TNT-{t_id[:6].upper()}"
    return {
        "id": t_id,
        "user_id": str(getattr(tenant, "user_id", "") or t_id),
        "tenant_id": code,
        "tnt_id": code,
        "name": getattr(tenant, "name", "") or getattr(tenant, "full_name", "") or "Resident Tenant",
        "email": getattr(tenant, "email", "") or "",
        "phone": getattr(tenant, "phone", "") or "",
        "type": getattr(tenant, "type", "Individual") or "Individual",
        "unit": getattr(tenant, "unit", "") or "Unassigned",
        "status": getattr(tenant, "status", "Active") or "Active"
    }


# ---------------------------------------------------------------------
# 4. UPDATE TENANT (PUT / PATCH)
# ---------------------------------------------------------------------
@router.put("/{tenant_id}")
@router.put("/{tenant_id}/")
@router.patch("/{tenant_id}")
@router.patch("/{tenant_id}/")
def update_tenant(
    tenant_id: str,
    tenant_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    db_tenant = find_tenant_by_identifier(db, tenant_id, org_id)
    if not db_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found."
        )

    for field, value in tenant_update.items():
        if hasattr(db_tenant, field):
            setattr(db_tenant, field, value)

    db.commit()
    db.refresh(db_tenant)

    t_id = str(getattr(db_tenant, "id", "") or "")
    code = getattr(db_tenant, "tenant_id", None) or getattr(db_tenant, "tnt_id", None) or f"TNT-{t_id[:6].upper()}"
    return {
        "id": t_id,
        "tenant_id": code,
        "name": getattr(db_tenant, "name", "") or getattr(db_tenant, "full_name", "") or "Resident Tenant",
        "email": getattr(db_tenant, "email", "") or "",
        "phone": getattr(db_tenant, "phone", "") or "",
        "status": getattr(db_tenant, "status", "Active") or "Active"
    }


# ---------------------------------------------------------------------
# 5. DELETE TENANT (Completely removes tenant profile & client role)
# ---------------------------------------------------------------------
@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{tenant_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_tenant(
    tenant_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    clean_id = tenant_id.strip()

    # 1. Locate explicit Tenant table row
    db_tenant = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        db_tenant = db.scalar(
            select(models.Tenant).where(
                or_(
                    models.Tenant.id == parsed_uuid,
                    models.Tenant.user_id == parsed_uuid
                )
            )
        )
    except ValueError:
        pass

    if not db_tenant:
        if hasattr(models.Tenant, "tenant_id"):
            db_tenant = db.scalar(select(models.Tenant).where(models.Tenant.tenant_id.ilike(clean_id)))
        if not db_tenant and hasattr(models.Tenant, "tnt_id"):
            db_tenant = db.scalar(select(models.Tenant).where(models.Tenant.tnt_id.ilike(clean_id)))
        if not db_tenant:
            db_tenant = db.scalar(select(models.Tenant).where(models.Tenant.email.ilike(clean_id)))

    # 2. Locate corresponding User record to revoke client role
    target_email = getattr(db_tenant, "email", clean_id) if db_tenant else clean_id
    target_user = None

    try:
        parsed_uuid = uuid.UUID(clean_id)
        target_user = db.scalar(select(models.User).where(models.User.id == parsed_uuid))
    except ValueError:
        pass

    if not target_user and target_email:
        target_user = db.scalar(select(models.User).where(models.User.email.ilike(target_email)))

    if not db_tenant and not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant record not found."
        )

    try:
        # Delete row from tenants table
        if db_tenant:
            db.delete(db_tenant)

        # Revoke the client role from the User row so they do not regenerate in the tenant feed
        if target_user and any(k in (target_user.role or "").lower() for k in ["client", "tenant", "resident"]):
            target_user.role = "inactive"

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete tenant because active leases or invoice records are attached."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting tenant: {str(e)}"
        )

    return None