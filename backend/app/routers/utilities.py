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


def serialize_utility(item: Any, db: Session) -> Dict[str, Any]:
    """Helper to return a fully serialized utility dictionary compatible with frontend views."""
    u_id = str(getattr(item, "id", "") or "")
    code = (
        getattr(item, "utility_id", None)
        or getattr(item, "charge_id", None)
        or getattr(item, "invoice_id", None)
        or getattr(item, "ref_no", None)
        or f"UTL-{u_id[:6].upper()}"
    )

    tenant_name = getattr(item, "tenant_name", None)
    tenant_email = getattr(item, "tenant_email", None)
    unit_number = getattr(item, "unit_number", None) or getattr(item, "unit_no", None)
    property_name = getattr(item, "property_name", None)
    unit_loc = getattr(item, "unit_location", None)

    if not tenant_name and getattr(item, "tenant_id", None):
        t_row = db.scalar(select(models.Tenant).where(models.Tenant.id == item.tenant_id))
        if t_row:
            tenant_name = t_row.name
            tenant_email = tenant_email or t_row.email
        else:
            u_row = db.scalar(select(models.User).where(models.User.id == item.tenant_id))
            if u_row:
                tenant_name = u_row.name or getattr(u_row, "full_name", None)
                tenant_email = tenant_email or u_row.email

    amount_val = float(
        getattr(item, "amount", None)
        or getattr(item, "charge_amount", None)
        or getattr(item, "total_amount", 0)
        or 0
    )
    due_d = getattr(item, "due_date", None)
    b_period = getattr(item, "billing_period", None) or getattr(item, "period", None) or "Current Period"
    u_type = (
        getattr(item, "utility_type", None)
        or getattr(item, "type", None)
        or "Electricity Sub-Meter"
    )

    return {
        "id": u_id,
        "utility_id": code,
        "charge_id": code,
        "invoice_id": code,
        "ref_no": code,
        "organization_id": str(getattr(item, "organization_id", "") or ""),
        "lease_id": str(getattr(item, "lease_id", "") or ""),
        "tenant_id": str(getattr(item, "tenant_id", "") or ""),
        "unit_id": str(getattr(item, "unit_id", "") or ""),
        "tenant_name": tenant_name or "Resident Tenant",
        "tenant_email": tenant_email or "",
        "property_name": property_name or "Property",
        "unit_number": unit_number or "Unit",
        "unit_no": unit_number or "Unit",
        "unit_location": unit_loc or f"{property_name or 'Property'} • {unit_number or 'Unit'}",
        "utility_type": u_type,
        "type": u_type,
        "billing_period": b_period,
        "period": b_period,
        "amount": amount_val,
        "charge_amount": amount_val,
        "total_amount": amount_val,
        "reading_prev": float(getattr(item, "reading_prev", 0) or 0),
        "reading_curr": float(getattr(item, "reading_curr", 0) or 0),
        "consumption": float(getattr(item, "consumption", 0) or 0),
        "rate": float(getattr(item, "rate", 0) or 0),
        "due_date": str(due_d) if due_d else None,
        "status": getattr(item, "status", "Unpaid") or "Unpaid",
        "notes": getattr(item, "notes", None) or getattr(item, "breakdown", "") or "",
        "breakdown": getattr(item, "breakdown", None) or getattr(item, "notes", "") or ""
    }


def find_utility_record(db: Session, utility_id: str, org_id: uuid.UUID):
    """Finds a utility charge across models.Utility safely."""
    clean_id = utility_id.strip()

    if hasattr(models, "Utility"):
        try:
            parsed_uuid = uuid.UUID(clean_id)
            record = db.scalar(
                select(models.Utility).where(
                    models.Utility.id == parsed_uuid,
                    or_(
                        models.Utility.organization_id == org_id,
                        models.Utility.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record
        except ValueError:
            pass

        if hasattr(models.Utility, "utility_id"):
            record = db.scalar(
                select(models.Utility).where(
                    models.Utility.utility_id.ilike(clean_id),
                    or_(
                        models.Utility.organization_id == org_id,
                        models.Utility.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record

    return None


# ---------------------------------------------------------------------
# 1. GET UTILITY CHARGES (Dual Route: with and without trailing slash)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_utilities(
    organization_id: Optional[str] = Query(default=None),
    unit_id: Optional[str] = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve all utility charges and meter statements."""
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    records = []
    if hasattr(models, "Utility"):
        stmt = select(models.Utility).where(
            or_(
                models.Utility.organization_id == org_id,
                models.Utility.organization_id.is_(None)
            )
        )
        if unit_id and hasattr(models.Utility, "unit_id"):
            try:
                stmt = stmt.where(models.Utility.unit_id == uuid.UUID(unit_id.strip()))
            except ValueError:
                pass
        if tenant_id and hasattr(models.Utility, "tenant_id"):
            try:
                stmt = stmt.where(models.Utility.tenant_id == uuid.UUID(tenant_id.strip()))
            except ValueError:
                pass

        records = list(db.scalars(stmt).all())

    serialized = [serialize_utility(r, db) for r in records]

    if status_filter:
        s_clean = status_filter.strip().upper()
        serialized = [r for r in serialized if s_clean in str(r.get("status", "")).upper()]

    if search:
        s = search.strip().lower()
        serialized = [
            r for r in serialized
            if s in str(r.get("utility_id", "")).lower()
            or s in str(r.get("tenant_name", "")).lower()
            or s in str(r.get("property_name", "")).lower()
            or s in str(r.get("unit_number", "")).lower()
            or s in str(r.get("unit_location", "")).lower()
            or s in str(r.get("type", "")).lower()
            or s in str(r.get("notes", "")).lower()
        ]

    return serialized


# ---------------------------------------------------------------------
# 2. CREATE UTILITY CHARGE (Dual Route: Resolves HTTP 405)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_utility_charge(
    charge_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Creates a new utility charge with safe foreign-key validation and dynamic attribute filtering."""
    org_id = parse_org_id(charge_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    amount_val = float(charge_in.get("amount") or charge_in.get("charge_amount") or charge_in.get("total_amount") or 0)
    if amount_val <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Utility charge amount must be greater than zero."
        )

    # 1. Foreign-Key Safe UUID Resolution (Avoids PostgreSQL ForeignKeyViolation)
    unit_id_val = None
    if charge_in.get("unit_id"):
        try:
            parsed_u = uuid.UUID(str(charge_in["unit_id"]).strip())
            if db.scalar(select(models.Unit).where(models.Unit.id == parsed_u)):
                unit_id_val = parsed_u
        except ValueError:
            pass

    tenant_id_val = None
    if charge_in.get("tenant_id"):
        try:
            parsed_t = uuid.UUID(str(charge_in["tenant_id"]).strip())
            if db.scalar(select(models.Tenant).where(models.Tenant.id == parsed_t)):
                tenant_id_val = parsed_t
        except ValueError:
            pass

    lease_id_val = None
    if charge_in.get("lease_id"):
        try:
            parsed_l = uuid.UUID(str(charge_in["lease_id"]).strip())
            if db.scalar(select(models.Lease).where(models.Lease.id == parsed_l)):
                lease_id_val = parsed_l
        except ValueError:
            pass

    # 2. Resolve Denormalized Metadata for UI and NOT NULL Constraints
    tenant_name = charge_in.get("tenant_name")
    if not tenant_name and tenant_id_val:
        t_row = db.scalar(select(models.Tenant).where(models.Tenant.id == tenant_id_val))
        if t_row:
            tenant_name = t_row.name
        else:
            u_row = db.scalar(select(models.User).where(models.User.id == tenant_id_val))
            if u_row:
                tenant_name = u_row.name or getattr(u_row, "full_name", None)
    if not tenant_name:
        tenant_name = "Resident Tenant"

    tenant_email = charge_in.get("tenant_email") or ""
    prop_name = charge_in.get("property_name") or "Property"
    unit_num = charge_in.get("unit_number") or charge_in.get("unit_no") or "Unit"
    unit_loc = charge_in.get("unit_location") or f"{prop_name} • {unit_num}"
    u_type = charge_in.get("utility_type") or charge_in.get("type") or "Electricity Sub-Meter"
    b_period = charge_in.get("billing_period") or charge_in.get("period") or datetime.now().strftime("%B %Y")
    notes_val = str(charge_in.get("notes") or charge_in.get("breakdown") or "")
    status_val = "Paid" if "PAID" in str(charge_in.get("status", "")).upper() else "Unpaid"
    code = charge_in.get("utility_id") or charge_in.get("charge_id") or f"UTL-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    # 3. Assemble Record Data
    record_data = {
        "id": uuid.uuid4(),
        "organization_id": org_id,
        "utility_id": code,
        "charge_id": code,
        "utility_type": u_type,
        "type": u_type,
        "billing_period": b_period,
        "period": b_period,
        "amount": amount_val,
        "charge_amount": amount_val,
        "total_amount": amount_val,
        "status": status_val,
        "tenant_name": tenant_name,
        "tenant_email": tenant_email,
        "property_name": prop_name,
        "unit_number": unit_num,
        "unit_no": unit_num,
        "unit_location": unit_loc,
        "breakdown": notes_val,
        "notes": notes_val,
        "due_date": parse_date_value(charge_in.get("due_date") or datetime.now().date())
    }

    if unit_id_val:
        record_data["unit_id"] = unit_id_val
    if tenant_id_val:
        record_data["tenant_id"] = tenant_id_val
    if lease_id_val:
        record_data["lease_id"] = lease_id_val

    # Optional meter attributes
    for field in ["reading_prev", "reading_curr", "consumption", "rate"]:
        if charge_in.get(field) is not None:
            try:
                record_data[field] = float(charge_in[field])
            except (ValueError, TypeError):
                pass

    # 4. Filter attributes against models.Utility columns to prevent unexpected kwarg crashes
    filtered_kwargs = {k: v for k, v in record_data.items() if hasattr(models.Utility, k)}
    db_record = models.Utility(**filtered_kwargs)
    db.add(db_record)

    try:
        db.commit()
        db.refresh(db_record)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database error saving utility: {str(e)}"
        )

    return serialize_utility(db_record, db)


# ---------------------------------------------------------------------
# 3. GET SINGLE UTILITY CHARGE
# ---------------------------------------------------------------------
@router.get("/{utility_id}")
@router.get("/{utility_id}/")
def get_utility(
    utility_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Fetch a single utility record by UUID or code."""
    org_id = parse_org_id(organization_id)
    record = find_utility_record(db, utility_id, org_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utility record not found."
        )
    return serialize_utility(record, db)


# ---------------------------------------------------------------------
# 4. UPDATE UTILITY STATUS / CHARGE (PUT / PATCH)
# ---------------------------------------------------------------------
@router.put("/{utility_id}")
@router.put("/{utility_id}/")
@router.patch("/{utility_id}")
@router.patch("/{utility_id}/")
def update_utility(
    utility_id: str,
    utility_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Update utility charge status or remarks."""
    org_id = parse_org_id(organization_id)
    record = find_utility_record(db, utility_id, org_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utility record not found."
        )

    for field, val in utility_update.items():
        if hasattr(record, field):
            setattr(record, field, val)

    if "status" in utility_update:
        s = str(utility_update["status"]).strip().upper()
        if hasattr(record, "status"):
            record.status = "Paid" if "PAID" in s else "Unpaid"

    db.commit()
    db.refresh(record)
    return serialize_utility(record, db)


# ---------------------------------------------------------------------
# 5. DELETE UTILITY CHARGE
# ---------------------------------------------------------------------
@router.delete("/{utility_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{utility_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_utility(
    utility_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Permanently delete a utility charge record."""
    org_id = parse_org_id(organization_id)
    clean_id = utility_id.strip()

    record = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        record = db.scalar(
            select(models.Utility).where(
                models.Utility.id == parsed_uuid,
                or_(
                    models.Utility.organization_id == org_id,
                    models.Utility.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not record and hasattr(models.Utility, "utility_id"):
        record = db.scalar(
            select(models.Utility).where(
                models.Utility.utility_id.ilike(clean_id),
                or_(
                    models.Utility.organization_id == org_id,
                    models.Utility.organization_id.is_(None)
                )
            )
        )

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utility record not found.")

    try:
        db.delete(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting utility record: {str(e)}"
        )

    return None