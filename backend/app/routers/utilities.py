import uuid
import logging
from datetime import date, datetime
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_, delete
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
    """Helper to return serialized utility charge dictionary with complete tenant and unit metadata."""
    u_id = str(getattr(item, "id", "") or "")
    code = (
        getattr(item, "utility_id", None) 
        or getattr(item, "invoice_id", None) 
        or getattr(item, "ref_no", None) 
        or f"UTL-{u_id[:6].upper()}"
    )

    # Extract Tenant Information
    tenant_name = getattr(item, "tenant_name", None)
    tenant_email = getattr(item, "tenant_email", None)
    tenant_obj = getattr(item, "tenant", None)
    if not tenant_name and tenant_obj:
        tenant_name = getattr(tenant_obj, "name", None) or getattr(tenant_obj, "full_name", None)
        tenant_email = tenant_email or getattr(tenant_obj, "email", None)

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

    # Extract Property & Unit Location
    unit_number = getattr(item, "unit_number", None) or getattr(item, "unit_no", None)
    property_name = getattr(item, "property_name", None)
    unit_obj = getattr(item, "unit", None)
    if unit_obj:
        unit_number = unit_number or getattr(unit_obj, "unit_no", None) or getattr(unit_obj, "unit_number", None)
        prop_obj = getattr(unit_obj, "property", None)
        if prop_obj:
            property_name = property_name or getattr(prop_obj, "name", None) or getattr(prop_obj, "property_name", None)
    elif getattr(item, "unit_id", None):
        u_row = db.scalar(select(models.Unit).where(models.Unit.id == item.unit_id))
        if u_row:
            unit_number = unit_number or getattr(u_row, "unit_no", None) or getattr(u_row, "unit_number", None)
            if getattr(u_row, "property_id", None):
                p_row = db.scalar(select(models.Property).where(models.Property.id == u_row.property_id))
                if p_row:
                    property_name = property_name or getattr(p_row, "name", None) or getattr(p_row, "property_name", None)

    amount_val = float(
        getattr(item, "amount", None) 
        or getattr(item, "charge_amount", None) 
        or getattr(item, "total_amount", 0) 
        or 0
    )
    due_d = getattr(item, "due_date", None)
    billing_period = getattr(item, "billing_period", None) or getattr(item, "period", None) or "Current Period"
    utility_type = (
        getattr(item, "utility_type", None) 
        or getattr(item, "type", None) 
        or getattr(item, "category_type", "Electricity Sub-Meter")
    )

    return {
        "id": u_id,
        "utility_id": code,
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
        "utility_type": utility_type,
        "type": utility_type,
        "billing_period": billing_period,
        "period": billing_period,
        "amount": amount_val,
        "charge_amount": amount_val,
        "reading_prev": float(getattr(item, "reading_prev", 0) or 0) if hasattr(item, "reading_prev") else None,
        "reading_curr": float(getattr(item, "reading_curr", 0) or 0) if hasattr(item, "reading_curr") else None,
        "consumption": float(getattr(item, "consumption", 0) or 0) if hasattr(item, "consumption") else None,
        "rate": float(getattr(item, "rate", 0) or 0) if hasattr(item, "rate") else None,
        "due_date": str(due_d) if due_d else None,
        "status": getattr(item, "status", "Unpaid") or "Unpaid",
        "notes": getattr(item, "notes", None) or getattr(item, "remarks", "") or ""
    }


def find_utility_record(db: Session, utility_id: str, org_id: uuid.UUID):
    """Finds a utility charge across models.Utility or models.Invoice."""
    clean_id = utility_id.strip()

    # 1. If dedicated Utility model exists
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

    # 2. Fallback to Invoice model
    if hasattr(models, "Invoice"):
        try:
            parsed_uuid = uuid.UUID(clean_id)
            record = db.scalar(
                select(models.Invoice).where(
                    models.Invoice.id == parsed_uuid,
                    or_(
                        models.Invoice.organization_id == org_id,
                        models.Invoice.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record
        except ValueError:
            pass

        if hasattr(models.Invoice, "invoice_id"):
            record = db.scalar(
                select(models.Invoice).where(
                    models.Invoice.invoice_id.ilike(clean_id),
                    or_(
                        models.Invoice.organization_id == org_id,
                        models.Invoice.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record

    return None


# ---------------------------------------------------------------------
# 1. GET UTILITY CHARGES (Dual Route)
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
    """Retrieve all utility charges and meter readings."""
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    records = []

    # Query from Utility table if exists
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
        records.extend(list(db.scalars(stmt).all()))

    # Also query utility-type invoices from Invoice table
    if hasattr(models, "Invoice"):
        inv_stmt = select(models.Invoice).where(
            or_(
                models.Invoice.organization_id == org_id,
                models.Invoice.organization_id.is_(None)
            ),
            or_(
                models.Invoice.type.ilike("%elec%"),
                models.Invoice.type.ilike("%water%"),
                models.Invoice.type.ilike("%util%"),
                models.Invoice.type.ilike("%hoa%"),
                models.Invoice.type.ilike("%meter%")
            )
        )
        records.extend(list(db.scalars(inv_stmt).all()))

    serialized = [serialize_utility(r, db) for r in records]

    # Deduplicate by ID
    unique_map = {}
    for item in serialized:
        unique_map[item["id"]] = item
    results = list(unique_map.values())

    # Apply Filters
    if status_filter:
        s_clean = status_filter.strip().upper()
        results = [r for r in results if s_clean in (r.get("status") or "").upper()]

    if search:
        s = search.strip().lower()
        results = [
            r for r in results
            if s in str(r.get("utility_id", "")).lower()
            or s in str(r.get("tenant_name", "")).lower()
            or s in str(r.get("property_name", "")).lower()
            or s in str(r.get("unit_number", "")).lower()
            or s in str(r.get("utility_type", "")).lower()
        ]

    return results


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
    """Creates a new utility charge and saves it to the database."""
    org_id = parse_org_id(charge_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    amount_val = float(charge_in.get("amount") or charge_in.get("charge_amount") or charge_in.get("total_amount") or 0)
    if amount_val <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Charge amount must be greater than zero."
        )

    # Resolve Unit & Lease & Tenant
    unit_id_val = None
    unit_id_raw = charge_in.get("unit_id")
    if unit_id_raw:
        try:
            unit_id_val = uuid.UUID(str(unit_id_raw).strip())
        except ValueError:
            pass

    tenant_id_val = None
    tenant_id_raw = charge_in.get("tenant_id")
    if tenant_id_raw:
        try:
            tenant_id_val = uuid.UUID(str(tenant_id_raw).strip())
        except ValueError:
            pass

    lease_id_val = None
    lease_id_raw = charge_in.get("lease_id")
    if lease_id_raw:
        try:
            lease_id_val = uuid.UUID(str(lease_id_raw).strip())
        except ValueError:
            pass

    # Resolve Denormalized Metadata for NOT NULL constraint safety
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

    prop_name = charge_in.get("property_name")
    unit_num = charge_in.get("unit_number") or charge_in.get("unit_no")

    if (not prop_name or not unit_num) and unit_id_val:
        u_row = db.scalar(select(models.Unit).where(models.Unit.id == unit_id_val))
        if u_row:
            unit_num = unit_num or u_row.unit_no or u_row.unit_number or "Unit"
            if getattr(u_row, "property_id", None):
                p_row = db.scalar(select(models.Property).where(models.Property.id == u_row.property_id))
                if p_row:
                    prop_name = prop_name or p_row.name
    
    if not prop_name:
        prop_name = "Property"
    if not unit_num:
        unit_num = "Unit"

    u_type = charge_in.get("utility_type") or charge_in.get("type") or "Electricity Sub-Meter"
    b_period = charge_in.get("billing_period") or charge_in.get("period") or datetime.now().strftime("%B %Y")
    d_date = parse_date_value(charge_in.get("due_date") or datetime.now().date())
    notes_val = str(charge_in.get("notes") or charge_in.get("remarks") or "")
    status_val = "Paid" if "PAID" in str(charge_in.get("status", "")).upper() else "Unpaid"
    code = f"UTL-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    # Determine primary model to instantiate
    target_model = models.Utility if hasattr(models, "Utility") else models.Invoice

    record_data = {
        "id": uuid.uuid4(),
        "organization_id": org_id,
        "status": status_val
    }

    # Safe dynamic field assignment
    if hasattr(target_model, "utility_id"):
        record_data["utility_id"] = code
    if hasattr(target_model, "invoice_id"):
        record_data["invoice_id"] = code
    if hasattr(target_model, "ref_no"):
        record_data["ref_no"] = code

    if hasattr(target_model, "unit_id") and unit_id_val:
        record_data["unit_id"] = unit_id_val
    if hasattr(target_model, "tenant_id") and tenant_id_val:
        record_data["tenant_id"] = tenant_id_val
    if hasattr(target_model, "lease_id") and lease_id_val:
        record_data["lease_id"] = lease_id_val

    if hasattr(target_model, "tenant_name"):
        record_data["tenant_name"] = tenant_name
    if hasattr(target_model, "property_name"):
        record_data["property_name"] = prop_name
    if hasattr(target_model, "unit_number"):
        record_data["unit_number"] = unit_num
    if hasattr(target_model, "unit_no"):
        record_data["unit_no"] = unit_num

    if hasattr(target_model, "amount"):
        record_data["amount"] = amount_val
    if hasattr(target_model, "charge_amount"):
        record_data["charge_amount"] = amount_val
    if hasattr(target_model, "total_amount"):
        record_data["total_amount"] = amount_val

    if hasattr(target_model, "utility_type"):
        record_data["utility_type"] = u_type
    if hasattr(target_model, "type"):
        record_data["type"] = u_type
    if hasattr(target_model, "category_type"):
        record_data["category_type"] = "Utility"

    if hasattr(target_model, "billing_period"):
        record_data["billing_period"] = b_period
    if hasattr(target_model, "period"):
        record_data["period"] = b_period
    if hasattr(target_model, "due_date"):
        record_data["due_date"] = d_date
    if hasattr(target_model, "notes"):
        record_data["notes"] = notes_val
    if hasattr(target_model, "remarks"):
        record_data["remarks"] = notes_val

    # Optional meter reading fields
    for field in ["reading_prev", "reading_curr", "consumption", "rate"]:
        if hasattr(target_model, field) and charge_in.get(field) is not None:
            record_data[field] = float(charge_in[field])

    db_record = target_model(**record_data)
    db.add(db_record)

    try:
        db.commit()
        db.refresh(db_record)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database constraint error saving utility charge: {str(e)}"
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
    """Fetch single utility charge by UUID or identifier code."""
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
    """Update utility charge status or meter reading details."""
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
    record = find_utility_record(db, utility_id, org_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utility record not found."
        )

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