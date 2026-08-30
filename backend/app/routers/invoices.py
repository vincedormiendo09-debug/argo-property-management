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


def serialize_invoice(invoice: models.Invoice, db: Session) -> Dict[str, Any]:
    """Helper to return fully serialized invoice records with tenant and unit details."""
    inv_id = str(getattr(invoice, "id", "") or "")
    code = getattr(invoice, "invoice_id", None) or getattr(invoice, "inv_id", None) or f"INV-{inv_id[:6].upper()}"

    # Extract Tenant Information
    tenant_name = getattr(invoice, "tenant_name", None)
    tenant_email = getattr(invoice, "tenant_email", None)
    tenant_obj = getattr(invoice, "tenant", None)
    if not tenant_name and tenant_obj:
        tenant_name = getattr(tenant_obj, "name", None) or getattr(tenant_obj, "full_name", None)
        tenant_email = tenant_email or getattr(tenant_obj, "email", None)

    if not tenant_name and getattr(invoice, "tenant_id", None):
        t_row = db.scalar(select(models.Tenant).where(models.Tenant.id == invoice.tenant_id))
        if t_row:
            tenant_name = t_row.name
            tenant_email = tenant_email or t_row.email
        else:
            u_row = db.scalar(select(models.User).where(models.User.id == invoice.tenant_id))
            if u_row:
                tenant_name = u_row.name or getattr(u_row, "full_name", None)
                tenant_email = tenant_email or u_row.email

    # Extract Property & Unit Information
    unit_number = getattr(invoice, "unit_number", None) or getattr(invoice, "unit_no", None)
    property_name = getattr(invoice, "property_name", None)
    unit_obj = getattr(invoice, "unit", None)
    if unit_obj:
        unit_number = unit_number or getattr(unit_obj, "unit_no", None) or getattr(unit_obj, "unit_number", None)
        prop_obj = getattr(unit_obj, "property", None)
        if prop_obj:
            property_name = property_name or getattr(prop_obj, "name", None) or getattr(prop_obj, "property_name", None)
    elif getattr(invoice, "unit_id", None):
        u_row = db.scalar(select(models.Unit).where(models.Unit.id == invoice.unit_id))
        if u_row:
            unit_number = unit_number or getattr(u_row, "unit_no", None) or getattr(u_row, "unit_number", None)
            if getattr(u_row, "property_id", None):
                p_row = db.scalar(select(models.Property).where(models.Property.id == u_row.property_id))
                if p_row:
                    property_name = property_name or getattr(p_row, "name", None) or getattr(p_row, "property_name", None)

    amount_val = float(
        getattr(invoice, "amount", None) 
        or getattr(invoice, "rent_amount", None) 
        or getattr(invoice, "total_amount", 0) 
        or 0
    )
    balance_val = float(getattr(invoice, "balance", None) or 0)
    due_d = getattr(invoice, "due_date", None)
    paid_d = getattr(invoice, "paid_at", None) or getattr(invoice, "paid_date", None)

    return {
        "id": inv_id,
        "invoice_id": code,
        "inv_id": code,
        "organization_id": str(getattr(invoice, "organization_id", "") or ""),
        "lease_id": str(getattr(invoice, "lease_id", "") or ""),
        "tenant_id": str(getattr(invoice, "tenant_id", "") or ""),
        "unit_id": str(getattr(invoice, "unit_id", "") or ""),
        "property_id": str(getattr(invoice, "property_id", "") or ""),
        "tenant_name": tenant_name or "Resident Tenant",
        "tenant_email": tenant_email or "",
        "property_name": property_name or "Property",
        "unit_number": unit_number or "Unit",
        "unit_no": unit_number or "Unit",
        "amount": amount_val,
        "total_amount": amount_val,
        "balance": balance_val,
        "payment_method": getattr(invoice, "payment_method", None) or getattr(invoice, "method", "GCash"),
        "method": getattr(invoice, "payment_method", None) or getattr(invoice, "method", "GCash"),
        "reference_number": getattr(invoice, "reference_number", None) or getattr(invoice, "ref_no", "") or "",
        "ref_no": getattr(invoice, "reference_number", None) or getattr(invoice, "ref_no", "") or "",
        "notes": getattr(invoice, "notes", None) or getattr(invoice, "remarks", "") or "",
        "type": getattr(invoice, "type", "Rent") or "Rent",
        "due_date": str(due_d) if due_d else None,
        "paid_at": str(paid_d) if paid_d else None,
        "status": getattr(invoice, "status", "Paid") or "Paid"
    }


def find_invoice_by_identifier(db: Session, invoice_id: str, organization_id: uuid.UUID):
    """Robustly resolves an invoice by UUID or string code."""
    clean_id = invoice_id.strip()
    try:
        parsed_uuid = uuid.UUID(clean_id)
        invoice = db.scalar(
            select(models.Invoice).where(
                models.Invoice.id == parsed_uuid,
                or_(
                    models.Invoice.organization_id == organization_id,
                    models.Invoice.organization_id.is_(None)
                )
            )
        )
        if invoice:
            return invoice
    except ValueError:
        pass

    if hasattr(models.Invoice, "invoice_id"):
        invoice = db.scalar(
            select(models.Invoice).where(
                models.Invoice.invoice_id.ilike(clean_id),
                or_(
                    models.Invoice.organization_id == organization_id,
                    models.Invoice.organization_id.is_(None)
                )
            )
        )
        if invoice:
            return invoice

    if hasattr(models.Invoice, "inv_id"):
        invoice = db.scalar(
            select(models.Invoice).where(
                models.Invoice.inv_id.ilike(clean_id),
                or_(
                    models.Invoice.organization_id == organization_id,
                    models.Invoice.organization_id.is_(None)
                )
            )
        )
        if invoice:
            return invoice

    return None


# ---------------------------------------------------------------------
# 1. GET INVOICES (Dual Route: Empty & Trailing Slash)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_invoices(
    organization_id: Optional[str] = Query(default=None),
    lease_id: Optional[str] = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Read all rent collection and billing invoice records."""
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    stmt = select(models.Invoice).where(
        or_(
            models.Invoice.organization_id == org_id,
            models.Invoice.organization_id.is_(None)
        )
    )

    if lease_id and hasattr(models.Invoice, "lease_id"):
        try:
            stmt = stmt.where(models.Invoice.lease_id == uuid.UUID(lease_id.strip()))
        except ValueError:
            pass

    if tenant_id and hasattr(models.Invoice, "tenant_id"):
        try:
            stmt = stmt.where(models.Invoice.tenant_id == uuid.UUID(tenant_id.strip()))
        except ValueError:
            pass

    if status_filter:
        s_clean = status_filter.strip().upper()
        if s_clean == "PAID":
            stmt = stmt.where(models.Invoice.status.ilike("paid"))
        elif s_clean in ("UNPAID", "OVERDUE"):
            stmt = stmt.where(or_(
                models.Invoice.status.ilike("unpaid"),
                models.Invoice.status.ilike("overdue")
            ))
        elif s_clean == "PENDING":
            stmt = stmt.where(models.Invoice.status.ilike("%pending%"))
        else:
            stmt = stmt.where(models.Invoice.status.ilike(f"%{status_filter.strip()}%"))

    invoices = list(db.scalars(stmt).all())
    serialized = [serialize_invoice(inv, db) for inv in invoices]

    if search:
        s = search.strip().lower()
        serialized = [
            inv for inv in serialized
            if s in str(inv.get("invoice_id", "")).lower()
            or s in str(inv.get("tenant_name", "")).lower()
            or s in str(inv.get("property_name", "")).lower()
            or s in str(inv.get("unit_number", "")).lower()
            or s in str(inv.get("reference_number", "")).lower()
            or s in str(inv.get("payment_method", "")).lower()
            or s in str(inv.get("status", "")).lower()
        ]

    return serialized


# ---------------------------------------------------------------------
# 2. CREATE INVOICE / RECORD PAYMENT (Dual Route: Resolves HTTP 405)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_invoice(
    invoice_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Record a rent payment or create a billing invoice."""
    org_id = parse_org_id(invoice_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    # 1. Resolve Amount & Status
    amount_val = float(invoice_in.get("amount") or invoice_in.get("rent_amount") or invoice_in.get("total_amount") or 0)
    if amount_val <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid payment amount is required."
        )

    raw_status = str(invoice_in.get("status") or "Paid").strip()
    status_clean = "Paid" if raw_status.upper() in ("PAID", "VERIFIED") else ("Pending" if "PEND" in raw_status.upper() else "Unpaid")

    # 2. Cross-reference Lease and Tenant
    lease_row = None
    lease_id_val = None
    lease_id_raw = invoice_in.get("lease_id")
    if lease_id_raw:
        try:
            lease_uuid = uuid.UUID(str(lease_id_raw).strip())
            lease_row = db.scalar(
                select(models.Lease).where(
                    models.Lease.id == lease_uuid,
                    or_(
                        models.Lease.organization_id == org_id,
                        models.Lease.organization_id.is_(None)
                    )
                )
            )
            if lease_row:
                lease_id_val = lease_row.id
        except ValueError:
            if hasattr(models.Lease, "lease_id"):
                lease_row = db.scalar(
                    select(models.Lease).where(
                        models.Lease.lease_id.ilike(str(lease_id_raw).strip()),
                        or_(
                            models.Lease.organization_id == org_id,
                            models.Lease.organization_id.is_(None)
                        )
                    )
                )
                if lease_row:
                    lease_id_val = lease_row.id

    tenant_id_val = None
    tenant_id_raw = invoice_in.get("tenant_id") or (lease_row.tenant_id if lease_row else None)
    if tenant_id_raw:
        try:
            tenant_id_val = uuid.UUID(str(tenant_id_raw).strip())
        except ValueError:
            pass

    # Extract metadata to fulfill NOT NULL database constraints
    tenant_name = (
        invoice_in.get("tenant_name")
        or (lease_row.tenant_name if lease_row and hasattr(lease_row, "tenant_name") else None)
    )
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

    unit_id_val = lease_row.unit_id if lease_row and hasattr(lease_row, "unit_id") else None
    prop_id_val = lease_row.property_id if lease_row and hasattr(lease_row, "property_id") else None

    prop_name = (
        invoice_in.get("property_name")
        or (lease_row.property_name if lease_row and hasattr(lease_row, "property_name") else None)
        or "Property"
    )
    unit_num = (
        invoice_in.get("unit_number")
        or invoice_in.get("unit_no")
        or (lease_row.unit_number if lease_row and hasattr(lease_row, "unit_number") else None)
        or "Unit"
    )

    custom_code = (
        invoice_in.get("invoice_id") 
        or invoice_in.get("inv_id") 
        or f"INV-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"
    ).strip()

    payment_method = str(invoice_in.get("payment_method") or invoice_in.get("method") or "GCash")
    ref_no = str(invoice_in.get("reference_number") or invoice_in.get("ref_no") or invoice_in.get("receipt_id") or "")
    notes = str(invoice_in.get("notes") or invoice_in.get("remarks") or "")
    due_date_val = parse_date_value(invoice_in.get("due_date") or datetime.now().date())
    paid_at_val = datetime.now() if status_clean == "Paid" else None

    # 3. Assemble Invoice Payload
    invoice_data = {
        "id": uuid.uuid4(),
        "organization_id": org_id,
        "status": status_clean
    }

    if hasattr(models.Invoice, "invoice_id"):
        invoice_data["invoice_id"] = custom_code
    if hasattr(models.Invoice, "inv_id"):
        invoice_data["inv_id"] = custom_code
    if hasattr(models.Invoice, "lease_id") and lease_id_val:
        invoice_data["lease_id"] = lease_id_val
    if hasattr(models.Invoice, "tenant_id") and tenant_id_val:
        invoice_data["tenant_id"] = tenant_id_val
    if hasattr(models.Invoice, "unit_id") and unit_id_val:
        invoice_data["unit_id"] = unit_id_val
    if hasattr(models.Invoice, "property_id") and prop_id_val:
        invoice_data["property_id"] = prop_id_val

    if hasattr(models.Invoice, "tenant_name"):
        invoice_data["tenant_name"] = tenant_name
    if hasattr(models.Invoice, "property_name"):
        invoice_data["property_name"] = prop_name
    if hasattr(models.Invoice, "unit_number"):
        invoice_data["unit_number"] = unit_num
    if hasattr(models.Invoice, "unit_no"):
        invoice_data["unit_no"] = unit_num

    if hasattr(models.Invoice, "amount"):
        invoice_data["amount"] = amount_val
    if hasattr(models.Invoice, "total_amount"):
        invoice_data["total_amount"] = amount_val
    if hasattr(models.Invoice, "rent_amount"):
        invoice_data["rent_amount"] = amount_val
    if hasattr(models.Invoice, "balance"):
        invoice_data["balance"] = 0.0 if status_clean == "Paid" else amount_val

    if hasattr(models.Invoice, "payment_method"):
        invoice_data["payment_method"] = payment_method
    if hasattr(models.Invoice, "method"):
        invoice_data["method"] = payment_method
    if hasattr(models.Invoice, "reference_number"):
        invoice_data["reference_number"] = ref_no
    if hasattr(models.Invoice, "ref_no"):
        invoice_data["ref_no"] = ref_no
    if hasattr(models.Invoice, "notes"):
        invoice_data["notes"] = notes
    if hasattr(models.Invoice, "remarks"):
        invoice_data["remarks"] = notes

    if hasattr(models.Invoice, "type"):
        invoice_data["type"] = str(invoice_in.get("type") or "Rent")
    if hasattr(models.Invoice, "due_date"):
        invoice_data["due_date"] = due_date_val
    if hasattr(models.Invoice, "paid_at"):
        invoice_data["paid_at"] = paid_at_val
    if hasattr(models.Invoice, "paid_date"):
        invoice_data["paid_date"] = paid_at_val.date() if paid_at_val else None

    db_invoice = models.Invoice(**invoice_data)
    db.add(db_invoice)

    try:
        db.commit()
        db.refresh(db_invoice)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database constraint error saving invoice: {str(e)}"
        )

    return serialize_invoice(db_invoice, db)


# ---------------------------------------------------------------------
# 3. GET SINGLE INVOICE
# ---------------------------------------------------------------------
@router.get("/{invoice_id}")
@router.get("/{invoice_id}/")
def get_invoice(
    invoice_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Fetch single invoice record by UUID or custom invoice code."""
    org_id = parse_org_id(organization_id)
    invoice = find_invoice_by_identifier(db, invoice_id, org_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )
    return serialize_invoice(invoice, db)


# ---------------------------------------------------------------------
# 4. UPDATE INVOICE STATUS (UNPAID -> PENDING -> PAID)
# ---------------------------------------------------------------------
@router.put("/{invoice_id}")
@router.put("/{invoice_id}/")
@router.patch("/{invoice_id}")
@router.patch("/{invoice_id}/")
def update_invoice(
    invoice_id: str,
    invoice_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Update invoice verification or payment status."""
    org_id = parse_org_id(organization_id)
    db_invoice = find_invoice_by_identifier(db, invoice_id, org_id)
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    if "status" in invoice_update:
        s = str(invoice_update["status"]).strip().upper()
        if s in ("PAID", "VERIFIED"):
            db_invoice.status = "Paid"
            if hasattr(db_invoice, "paid_at"):
                db_invoice.paid_at = datetime.now()
            if hasattr(db_invoice, "balance"):
                db_invoice.balance = 0.0
        elif s in ("PENDING", "PENDING VERIFICATION", "PENDING_VERIFICATION"):
            db_invoice.status = "Pending"
        else:
            db_invoice.status = "Unpaid"

    if "reference_number" in invoice_update or "ref_no" in invoice_update:
        ref = str(invoice_update.get("reference_number") or invoice_update.get("ref_no") or "")
        if hasattr(db_invoice, "reference_number"):
            db_invoice.reference_number = ref
        if hasattr(db_invoice, "ref_no"):
            db_invoice.ref_no = ref

    if "payment_method" in invoice_update or "method" in invoice_update:
        m = str(invoice_update.get("payment_method") or invoice_update.get("method") or "GCash")
        if hasattr(db_invoice, "payment_method"):
            db_invoice.payment_method = m
        if hasattr(db_invoice, "method"):
            db_invoice.method = m

    if "notes" in invoice_update or "remarks" in invoice_update:
        n = str(invoice_update.get("notes") or invoice_update.get("remarks") or "")
        if hasattr(db_invoice, "notes"):
            db_invoice.notes = n
        if hasattr(db_invoice, "remarks"):
            db_invoice.remarks = n

    db.commit()
    db.refresh(db_invoice)
    return serialize_invoice(db_invoice, db)


# ---------------------------------------------------------------------
# 5. DELETE INVOICE
# ---------------------------------------------------------------------
@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{invoice_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(
    invoice_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Delete an invoice record."""
    org_id = parse_org_id(organization_id)
    db_invoice = find_invoice_by_identifier(db, invoice_id, org_id)
    if not db_invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found."
        )

    try:
        db.delete(db_invoice)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete invoice because it is tied to active ledger transactions."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting invoice: {str(e)}"
        )

    return None