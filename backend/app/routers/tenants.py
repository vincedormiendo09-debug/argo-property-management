import uuid
import logging
from datetime import datetime
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models

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


# ---------------------------------------------------------------------
# 1. GET TENANTS (Reads Tenants + Client Users directly from Neon DB)
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
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    results: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_emails = set()

    # Step 1: Query explicit records in 'tenants' table
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
            t_id = str(t.id)
            t_user_id = str(getattr(t, "user_id", "") or t_id)
            t_email = (getattr(t, "email", "") or "").lower().strip()
            t_name = getattr(t, "name", None) or getattr(t, "full_name", None) or "Resident Tenant"
            code = getattr(t, "tenant_id", None) or getattr(t, "tnt_id", None) or f"TNT-{t_id[:6].upper()}"

            if t_id:
                seen_ids.add(t_id)
            if t_user_id:
                seen_ids.add(t_user_id)
            if t_email:
                seen_emails.add(t_email)

            results.append({
                "id": t_id,
                "user_id": t_user_id,
                "tenant_id": code,
                "tnt_id": code,
                "name": t_name,
                "full_name": t_name,
                "email": getattr(t, "email", "") or "",
                "phone": getattr(t, "phone", "") or "",
                "type": getattr(t, "type", "Individual") or "Individual",
                "unit": getattr(t, "unit", "No Current Unit") or "No Current Unit",
                "lease_id": getattr(t, "lease_id", None),
                "emergency_contact": getattr(t, "emergency_contact", ""),
                "status": getattr(t, "status", "Active") or "Active"
            })
    except Exception as e:
        logger.warning(f"Notice fetching tenants table: {e}")

    # Step 2: Query registered users with client/tenant/resident roles (Maria Santos & Carlos Mendoza)
    try:
        db_users = list(db.scalars(
            select(models.User).where(
                or_(
                    models.User.role.ilike("%client%"),
                    models.User.role.ilike("%tenant%"),
                    models.User.role.ilike("%resident%")
                )
            )
        ).all())

        for u in db_users:
            u_id = str(u.id)
            u_email = (getattr(u, "email", "") or "").lower().strip()
            u_name = getattr(u, "name", None) or getattr(u, "full_name", None) or "Resident Tenant"

            # Check if this user is already registered in the tenants table
            if u_id not in seen_ids and u_email not in seen_emails:
                seen_ids.add(u_id)
                if u_email:
                    seen_emails.add(u_email)

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
                    "unit": "No Current Unit",
                    "lease_id": None,
                    "emergency_contact": "",
                    "status": "Active"
                })
    except Exception as e:
        logger.warning(f"Notice fetching client users: {e}")

    # Step 3: Apply Filters
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
        raise HTTPException(status_code=400, detail="Tenant name is required.")

    clean_email = (tenant_in.get("email") or "").strip().lower() or None
    code = (tenant_in.get("tenant_id") or tenant_in.get("tnt_id") or f"TNT-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}").strip()

    new_id = uuid.uuid4()
    if tenant_in.get("id"):
        try:
            new_id = uuid.UUID(str(tenant_in["id"]))
        except ValueError:
            pass

    user_id_val = None
    if tenant_in.get("user_id"):
        try:
            user_id_val = uuid.UUID(str(tenant_in["user_id"]))
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

    if user_id_val and hasattr(models.Tenant, "user_id"):
        tenant_data["user_id"] = user_id_val
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
    clean_id = tenant_id.strip()

    # 1. Search in 'tenants' table
    for t in db.scalars(select(models.Tenant)).all():
        if str(t.id) == clean_id or str(getattr(t, "user_id", "")) == clean_id or (t.email or "").lower() == clean_id.lower() or str(getattr(t, "tenant_id", "")).lower() == clean_id.lower():
            code = getattr(t, "tenant_id", None) or getattr(t, "tnt_id", None) or f"TNT-{str(t.id)[:6].upper()}"
            return {
                "id": str(t.id),
                "user_id": str(getattr(t, "user_id", "") or str(t.id)),
                "tenant_id": code,
                "name": t.name,
                "email": t.email or "",
                "phone": t.phone or "",
                "type": getattr(t, "type", "Individual"),
                "unit": getattr(t, "unit", "No Current Unit"),
                "status": getattr(t, "status", "Active")
            }

    # 2. Search in 'users' table
    for u in db.scalars(select(models.User)).all():
        if str(u.id) == clean_id or (u.email or "").lower() == clean_id.lower():
            return {
                "id": str(u.id),
                "user_id": str(u.id),
                "tenant_id": f"TNT-{str(u.id)[:6].upper()}",
                "name": getattr(u, "name", None) or getattr(u, "full_name", None) or "Resident Tenant",
                "email": u.email or "",
                "phone": getattr(u, "phone", "") or "",
                "type": "Individual",
                "unit": "No Current Unit",
                "status": "Active"
            }

    raise HTTPException(status_code=404, detail="Tenant not found.")


# ---------------------------------------------------------------------
# 4. DELETE TENANT (Permanent removal from DB & Role Revocation)
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

    # Find row in tenants table
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
        db_tenant = db.scalar(select(models.Tenant).where(models.Tenant.email.ilike(clean_id)))

    # Find row in users table
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
        raise HTTPException(status_code=404, detail="Tenant record not found.")

    try:
        if db_tenant:
            db.delete(db_tenant)

        # Update user role to 'inactive' so it does not reappear in the tenant list
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