import uuid
import logging
from datetime import date, datetime
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
    """Ensures a stub Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def parse_date_value(val: Any) -> Optional[date]:
    """Safely parses string ISO dates or date objects."""
    if not val:
        return None
    if isinstance(val, (date, datetime)):
        return val if isinstance(val, date) else val.date()
    try:
        clean_str = str(val).strip()
        if not clean_str or clean_str.lower() in ("null", "undefined"):
            return None
        return datetime.fromisoformat(clean_str.replace("Z", "")).date()
    except Exception:
        try:
            return datetime.strptime(str(val).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def serialize_lease(lease: models.Lease, db: Session) -> Dict[str, Any]:
    """Helper to return fully serialized lease objects with tenant and unit details."""
    l_id = str(getattr(lease, "id", "") or "")
    code = getattr(lease, "lease_id", None) or f"LSE-{l_id[:6].upper()}"

    # Extract Tenant Name
    tenant_name = getattr(lease, "tenant_name", None)
    tenant_obj = getattr(lease, "tenant", None)
    if not tenant_name and tenant_obj:
        tenant_name = getattr(tenant_obj, "name", None) or getattr(tenant_obj, "full_name", None)
    if not tenant_name and getattr(lease, "tenant_id", None):
        t_row = db.scalar(select(models.Tenant).where(models.Tenant.id == lease.tenant_id))
        if t_row:
            tenant_name = t_row.name
        else:
            u_row = db.scalar(select(models.User).where(models.User.id == lease.tenant_id))
            if u_row:
                tenant_name = u_row.name or getattr(u_row, "full_name", None)

    # Extract Unit & Property Name
    unit_no = getattr(lease, "unit_number", None) or getattr(lease, "unit_no", None)
    prop_name = getattr(lease, "property_name", None)
    unit_obj = getattr(lease, "unit", None)
    if unit_obj:
        unit_no = unit_no or getattr(unit_obj, "unit_no", None) or getattr(unit_obj, "unit_number", None)
        prop_obj = getattr(unit_obj, "property", None)
        if prop_obj:
            prop_name = prop_name or getattr(prop_obj, "name", None) or getattr(prop_obj, "property_name", None)
    elif getattr(lease, "unit_id", None):
        u_row = db.scalar(select(models.Unit).where(models.Unit.id == lease.unit_id))
        if u_row:
            unit_no = unit_no or getattr(u_row, "unit_no", None) or getattr(u_row, "unit_number", None)
            if getattr(u_row, "property_id", None):
                p_row = db.scalar(select(models.Property).where(models.Property.id == u_row.property_id))
                if p_row:
                    prop_name = prop_name or getattr(p_row, "name", None) or getattr(p_row, "property_name", None)

    start_d = getattr(lease, "start_date", None) or getattr(lease, "lease_start", None)
    end_d = getattr(lease, "end_date", None) or getattr(lease, "lease_end", None)

    return {
        "id": l_id,
        "lease_id": code,
        "organization_id": str(getattr(lease, "organization_id", "") or ""),
        "unit_id": str(getattr(lease, "unit_id", "") or ""),
        "tenant_id": str(getattr(lease, "tenant_id", "") or ""),
        "tenant_name": tenant_name or "Resident Tenant",
        "tenant_email": getattr(lease, "tenant_email", "") or "",
        "property_name": prop_name or "Property",
        "unit_number": unit_no or "Unit",
        "unit_no": unit_no or "Unit",
        "start_date": str(start_d) if start_d else None,
        "end_date": str(end_d) if end_d else None,
        "monthly_rent": float(getattr(lease, "monthly_rent", None) or getattr(lease, "rent", None) or getattr(lease, "rent_amount", 0) or 0),
        "rent": float(getattr(lease, "rent", None) or getattr(lease, "monthly_rent", None) or getattr(lease, "rent_amount", 0) or 0),
        "deposit": float(getattr(lease, "deposit", None) or getattr(lease, "security_deposit", 0) or 0),
        "security_deposit": float(getattr(lease, "security_deposit", None) or getattr(lease, "deposit", 0) or 0),
        "status": getattr(lease, "status", "ACTIVE") or "ACTIVE"
    }


# ---------------------------------------------------------------------
# 1. GET LEASES
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_leases(
    organization_id: Optional[str] = Query(default=None),
    unit_id: Optional[str] = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve all active and draft leases scoped by organization."""
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    stmt = select(models.Lease).where(
        or_(
            models.Lease.organization_id == org_id,
            models.Lease.organization_id.is_(None)
        )
    )

    if unit_id:
        try:
            stmt = stmt.where(models.Lease.unit_id == uuid.UUID(unit_id.strip()))
        except ValueError:
            pass

    if tenant_id:
        try:
            stmt = stmt.where(models.Lease.tenant_id == uuid.UUID(tenant_id.strip()))
        except ValueError:
            pass

    if status_filter:
        stmt = stmt.where(models.Lease.status.ilike(f"%{status_filter.strip()}%"))

    leases = list(db.scalars(stmt).all())
    serialized = [serialize_lease(l, db) for l in leases]

    if search:
        s = search.strip().lower()
        serialized = [
            l for l in serialized
            if s in str(l.get("lease_id", "")).lower()
            or s in str(l.get("tenant_name", "")).lower()
            or s in str(l.get("property_name", "")).lower()
            or s in str(l.get("unit_number", "")).lower()
            or s in str(l.get("status", "")).lower()
        ]

    return serialized


# ---------------------------------------------------------------------
# 2. CREATE LEASE (Fixes NotNullViolation for tenant_name)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_lease(
    lease_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Create a new lease agreement and update target unit occupancy status."""
    org_id = parse_org_id(lease_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    # 1. Parse and Validate Unit
    unit_id_raw = lease_in.get("unit_id")
    if not unit_id_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target unit is required."
        )

    try:
        unit_uuid = uuid.UUID(str(unit_id_raw).strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid unit UUID format."
        )

    unit = db.scalar(
        select(models.Unit).where(
            models.Unit.id == unit_uuid,
            or_(
                models.Unit.organization_id == org_id,
                models.Unit.organization_id.is_(None)
            )
        )
    )
    if not unit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID '{unit_id_raw}' was not found."
        )

    # 2. Parse and Validate Tenant
    tenant_id_raw = lease_in.get("tenant_id")
    if not tenant_id_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant profile is required."
        )

    try:
        tenant_uuid = uuid.UUID(str(tenant_id_raw).strip())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant UUID format."
        )

    tenant = db.scalar(
        select(models.Tenant).where(
            or_(
                models.Tenant.id == tenant_uuid,
                models.Tenant.user_id == tenant_uuid
            ),
            or_(
                models.Tenant.organization_id == org_id,
                models.Tenant.organization_id.is_(None)
            )
        )
    )

    # Auto-Materialize from Users if only registered as a User
    if not tenant:
        client_user = db.scalar(select(models.User).where(models.User.id == tenant_uuid))
        if client_user:
            t_code = f"TNT-{str(client_user.id)[:6].upper()}"
            tenant = models.Tenant(
                id=client_user.id,
                organization_id=org_id,
                name=client_user.name or getattr(client_user, "full_name", None) or "Registered Tenant",
                email=client_user.email,
                phone=getattr(client_user, "phone", "") or "",
                type="Individual",
                status="Active"
            )
            if hasattr(tenant, "user_id"):
                tenant.user_id = client_user.id
            if hasattr(tenant, "tenant_id"):
                tenant.tenant_id = t_code
            if hasattr(tenant, "tnt_id"):
                tenant.tnt_id = t_code
            db.add(tenant)
            db.flush()
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant with ID '{tenant_id_raw}' was not found."
            )

    # 3. Resolve required string metadata
    t_name = (
        lease_in.get("tenant_name") 
        or getattr(tenant, "name", None) 
        or getattr(tenant, "full_name", None) 
        or "Resident Tenant"
    )
    t_email = (
        lease_in.get("tenant_email") 
        or getattr(tenant, "email", None) 
        or ""
    )

    prop_id = getattr(unit, "property_id", None)
    prop_name = lease_in.get("property_name")
    if not prop_name and prop_id:
        p_row = db.scalar(select(models.Property).where(models.Property.id == prop_id))
        if p_row:
            prop_name = p_row.name or getattr(p_row, "property_name", None)
    if not prop_name:
        prop_name = "Property"

    u_num = (
        lease_in.get("unit_number") 
        or getattr(unit, "unit_no", None) 
        or getattr(unit, "unit_number", None) 
        or "Unit"
    )

    # 4. Assemble Lease Payload
    lease_status = (lease_in.get("status") or "ACTIVE").upper().strip()
    rent_val = float(lease_in.get("monthly_rent") or lease_in.get("rent") or lease_in.get("rent_amount") or 0)
    deposit_val = float(lease_in.get("deposit") or lease_in.get("security_deposit") or 0)
    start_date_val = parse_date_value(lease_in.get("start_date") or lease_in.get("lease_start") or datetime.now().date())
    end_date_val = parse_date_value(lease_in.get("end_date") or lease_in.get("lease_end"))
    custom_code = (lease_in.get("lease_id") or f"LSE-{datetime.now().year}-{str(uuid.uuid4())[:6].upper()}").strip()

    lease_data = {
        "id": uuid.uuid4(),
        "organization_id": org_id,
        "unit_id": unit.id,
        "tenant_id": tenant.id,
        "status": lease_status
    }

    # Populate denormalized columns to fulfill NOT NULL constraints
    if hasattr(models.Lease, "tenant_name"):
        lease_data["tenant_name"] = t_name
    if hasattr(models.Lease, "tenant_email"):
        lease_data["tenant_email"] = t_email
    if hasattr(models.Lease, "property_id") and prop_id:
        lease_data["property_id"] = prop_id
    if hasattr(models.Lease, "property_name"):
        lease_data["property_name"] = prop_name
    if hasattr(models.Lease, "unit_number"):
        lease_data["unit_number"] = u_num

    if hasattr(models.Lease, "lease_id"):
        lease_data["lease_id"] = custom_code
    if hasattr(models.Lease, "start_date"):
        lease_data["start_date"] = start_date_val
    if hasattr(models.Lease, "lease_start"):
        lease_data["lease_start"] = start_date_val
    if hasattr(models.Lease, "end_date"):
        lease_data["end_date"] = end_date_val
    if hasattr(models.Lease, "lease_end"):
        lease_data["lease_end"] = end_date_val
    if hasattr(models.Lease, "monthly_rent"):
        lease_data["monthly_rent"] = rent_val
    if hasattr(models.Lease, "rent"):
        lease_data["rent"] = rent_val
    if hasattr(models.Lease, "rent_amount"):
        lease_data["rent_amount"] = rent_val
    if hasattr(models.Lease, "deposit"):
        lease_data["deposit"] = deposit_val
    if hasattr(models.Lease, "security_deposit"):
        lease_data["security_deposit"] = deposit_val

    db_lease = models.Lease(**lease_data)
    db.add(db_lease)

    # 5. Synchronize Unit Occupancy and Tenant location
    if lease_status == "ACTIVE":
        unit.status = "OCCUPIED"
        if hasattr(tenant, "unit"):
            tenant.unit = f"{prop_name} • {u_num}"

    try:
        db.commit()
        db.refresh(db_lease)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database constraint error saving lease: {str(e)}"
        )

    return serialize_lease(db_lease, db)


# ---------------------------------------------------------------------
# 3. GET SINGLE LEASE
# ---------------------------------------------------------------------
@router.get("/{lease_id}")
@router.get("/{lease_id}/")
def get_lease(
    lease_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Fetch single lease by UUID or lease identifier code."""
    org_id = parse_org_id(organization_id)
    clean_id = lease_id.strip()

    lease = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        lease = db.scalar(
            select(models.Lease).where(
                models.Lease.id == parsed_uuid,
                or_(
                    models.Lease.organization_id == org_id,
                    models.Lease.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not lease and hasattr(models.Lease, "lease_id"):
        lease = db.scalar(
            select(models.Lease).where(
                models.Lease.lease_id.ilike(clean_id),
                or_(
                    models.Lease.organization_id == org_id,
                    models.Lease.organization_id.is_(None)
                )
            )
        )

    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    return serialize_lease(lease, db)


# ---------------------------------------------------------------------
# 4. UPDATE LEASE
# ---------------------------------------------------------------------
@router.put("/{lease_id}")
@router.put("/{lease_id}/")
@router.patch("/{lease_id}")
@router.patch("/{lease_id}/")
def update_lease(
    lease_id: str,
    lease_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Update lease status and synchronize unit occupancy."""
    org_id = parse_org_id(organization_id)
    clean_id = lease_id.strip()

    db_lease = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        db_lease = db.scalar(
            select(models.Lease).where(
                models.Lease.id == parsed_uuid,
                or_(
                    models.Lease.organization_id == org_id,
                    models.Lease.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not db_lease and hasattr(models.Lease, "lease_id"):
        db_lease = db.scalar(
            select(models.Lease).where(
                models.Lease.lease_id.ilike(clean_id),
                or_(
                    models.Lease.organization_id == org_id,
                    models.Lease.organization_id.is_(None)
                )
            )
        )

    if not db_lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    if "status" in lease_update:
        new_status = str(lease_update["status"]).upper().strip()
        db_lease.status = new_status
        if db_lease.unit_id:
            unit = db.scalar(select(models.Unit).where(models.Unit.id == db_lease.unit_id))
            if unit:
                if new_status == "ACTIVE":
                    unit.status = "OCCUPIED"
                elif new_status in ["ENDED", "TERMINATED", "EXPIRED", "CANCELLED"]:
                    unit.status = "VACANT"

    if "rent" in lease_update or "monthly_rent" in lease_update:
        val = float(lease_update.get("monthly_rent") or lease_update.get("rent") or 0)
        if hasattr(db_lease, "monthly_rent"):
            db_lease.monthly_rent = val
        if hasattr(db_lease, "rent"):
            db_lease.rent = val

    if "deposit" in lease_update or "security_deposit" in lease_update:
        val = float(lease_update.get("deposit") or lease_update.get("security_deposit") or 0)
        if hasattr(db_lease, "deposit"):
            db_lease.deposit = val
        if hasattr(db_lease, "security_deposit"):
            db_lease.security_deposit = val

    if "start_date" in lease_update or "lease_start" in lease_update:
        d = parse_date_value(lease_update.get("start_date") or lease_update.get("lease_start"))
        if hasattr(db_lease, "start_date"):
            db_lease.start_date = d
        if hasattr(db_lease, "lease_start"):
            db_lease.lease_start = d

    if "end_date" in lease_update or "lease_end" in lease_update:
        d = parse_date_value(lease_update.get("end_date") or lease_update.get("lease_end"))
        if hasattr(db_lease, "end_date"):
            db_lease.end_date = d
        if hasattr(db_lease, "lease_end"):
            db_lease.lease_end = d

    db.commit()
    db.refresh(db_lease)
    return serialize_lease(db_lease, db)


# ---------------------------------------------------------------------
# 5. DELETE LEASE
# ---------------------------------------------------------------------
@router.delete("/{lease_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{lease_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_lease(
    lease_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Delete lease agreement and revert unit status to VACANT."""
    org_id = parse_org_id(organization_id)
    clean_id = lease_id.strip()

    db_lease = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        db_lease = db.scalar(
            select(models.Lease).where(
                models.Lease.id == parsed_uuid,
                or_(
                    models.Lease.organization_id == org_id,
                    models.Lease.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not db_lease and hasattr(models.Lease, "lease_id"):
        db_lease = db.scalar(
            select(models.Lease).where(
                models.Lease.lease_id.ilike(clean_id),
                or_(
                    models.Lease.organization_id == org_id,
                    models.Lease.organization_id.is_(None)
                )
            )
        )

    if not db_lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lease not found."
        )

    if db_lease.unit_id:
        unit = db.scalar(select(models.Unit).where(models.Unit.id == db_lease.unit_id))
        if unit:
            unit.status = "VACANT"

    db.delete(db_lease)
    db.commit()
    return None