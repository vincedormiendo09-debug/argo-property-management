import uuid
import logging
from datetime import datetime
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

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


def serialize_ticket(item: Any, db: Session) -> Dict[str, Any]:
    """Standardizes ticket representation across frontend views."""
    t_id = str(getattr(item, "id", "") or "")
    code = getattr(item, "ticket_id", None) or f"TKT-{t_id[:6].upper()}"

    created_dt = getattr(item, "created_at", None)
    created_str = str(created_dt) if created_dt else datetime.now().isoformat()

    return {
        "id": t_id,
        "ticket_id": code,
        "organization_id": str(getattr(item, "organization_id", "") or ""),
        "unit_id": str(getattr(item, "unit_id", "") or ""),
        "tenant_name": getattr(item, "tenant_name", None) or "Resident Occupant",
        "tenant_email": getattr(item, "tenant_email", None) or "",
        "property_location": getattr(item, "property_location", None) or "Property / Unit",
        "category": getattr(item, "category", "General") or "General",
        "title": getattr(item, "title", "Maintenance Request") or "Maintenance Request",
        "description": getattr(item, "description", "") or "",
        "priority": getattr(item, "priority", "Normal") or "Normal",
        "status": getattr(item, "status", "Open") or "Open",
        "technician": getattr(item, "technician", "Unassigned") or "Unassigned",
        "scheduled_time": getattr(item, "scheduled_time", None) or "Pending Dispatch",
        "cost": float(getattr(item, "cost", 0.0) or 0.0),
        "created_at": created_str
    }


def find_ticket_record(db: Session, ticket_id: str, org_id: uuid.UUID):
    """Locates a maintenance ticket by UUID or alphanumeric ticket_id code."""
    clean_id = ticket_id.strip()

    if hasattr(models, "MaintenanceTicket"):
        try:
            parsed_uuid = uuid.UUID(clean_id)
            record = db.scalar(
                select(models.MaintenanceTicket).where(
                    models.MaintenanceTicket.id == parsed_uuid,
                    or_(
                        models.MaintenanceTicket.organization_id == org_id,
                        models.MaintenanceTicket.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record
        except ValueError:
            pass

        if hasattr(models.MaintenanceTicket, "ticket_id"):
            record = db.scalar(
                select(models.MaintenanceTicket).where(
                    models.MaintenanceTicket.ticket_id.ilike(clean_id),
                    or_(
                        models.MaintenanceTicket.organization_id == org_id,
                        models.MaintenanceTicket.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record

    return None


# ---------------------------------------------------------------------
# 1. GET MAINTENANCE TICKETS (Dual Route)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_maintenance_tickets(
    organization_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    priority_filter: Optional[str] = Query(default=None, alias="priority"),
    category: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Fetch all logged operations and maintenance tickets."""
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    stmt = select(models.MaintenanceTicket).where(
        or_(
            models.MaintenanceTicket.organization_id == org_id,
            models.MaintenanceTicket.organization_id.is_(None)
        )
    )

    if status_filter:
        stmt = stmt.where(models.MaintenanceTicket.status.ilike(f"%{status_filter.strip()}%"))
    if priority_filter:
        stmt = stmt.where(models.MaintenanceTicket.priority.ilike(f"%{priority_filter.strip()}%"))
    if category:
        stmt = stmt.where(models.MaintenanceTicket.category.ilike(f"%{category.strip()}%"))

    tickets = list(db.scalars(stmt).all())
    serialized = [serialize_ticket(t, db) for t in tickets]

    if search:
        s = search.strip().lower()
        serialized = [
            t for t in serialized
            if s in str(t.get("ticket_id", "")).lower()
            or s in str(t.get("title", "")).lower()
            or s in str(t.get("tenant_name", "")).lower()
            or s in str(t.get("property_location", "")).lower()
            or s in str(t.get("technician", "")).lower()
            or s in str(t.get("category", "")).lower()
        ]

    return serialized


# ---------------------------------------------------------------------
# 2. CREATE MAINTENANCE TICKET (Dual Route: Resolves HTTP 405)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_maintenance_ticket(
    ticket_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Creates a new maintenance/operations ticket."""
    org_id = parse_org_id(ticket_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    title = str(ticket_in.get("title") or ticket_in.get("issue_title") or "").strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Issue title / short summary is required."
        )

    # Safe Foreign Key Unit Resolution
    unit_id_val = None
    if ticket_in.get("unit_id"):
        try:
            parsed_u = uuid.UUID(str(ticket_in["unit_id"]).strip())
            if db.scalar(select(models.Unit).where(models.Unit.id == parsed_u)):
                unit_id_val = parsed_u
        except ValueError:
            pass

    cost_val = float(ticket_in.get("cost") or ticket_in.get("estimated_cost") or 0.0)
    ticket_code = (
        ticket_in.get("ticket_id") 
        or f"TKT-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"
    )

    record_data = {
        "id": uuid.uuid4(),
        "organization_id": org_id,
        "unit_id": unit_id_val,
        "ticket_id": ticket_code,
        "title": title,
        "tenant_name": ticket_in.get("tenant_name") or "Resident Occupant",
        "tenant_email": ticket_in.get("tenant_email") or "",
        "property_location": ticket_in.get("property_location") or ticket_in.get("location") or "Property / Unit",
        "category": ticket_in.get("category") or "General Maintenance",
        "priority": ticket_in.get("priority") or "Normal",
        "status": ticket_in.get("status") or "Open",
        "technician": ticket_in.get("technician") or ticket_in.get("contractor") or "Unassigned",
        "scheduled_time": ticket_in.get("scheduled_time") or "Pending Dispatch",
        "description": ticket_in.get("description") or "",
        "cost": cost_val
    }

    filtered_kwargs = {k: v for k, v in record_data.items() if hasattr(models.MaintenanceTicket, k)}
    db_ticket = models.MaintenanceTicket(**filtered_kwargs)
    db.add(db_ticket)

    # Automatically notify admins
    if hasattr(models, "Notification"):
        prio_str = str(record_data.get("priority", "")).lower()
        is_urgent = prio_str in ["high", "urgent", "emergency"]
        notif = models.Notification(
            id=uuid.uuid4(),
            organization_id=org_id,
            pov="admin",
            category="maintenance",
            status="unread",
            is_read=False,
            title=f"New Maintenance Ticket ({ticket_code})",
            description=f"Repair request: '{title}' assigned to {record_data['technician']}.",
            property=record_data["property_location"],
            tag=f"Priority: {record_data['priority']}",
            urgent=is_urgent
        )
        db.add(notif)

    try:
        db.commit()
        db.refresh(db_ticket)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database error creating ticket: {str(e)}"
        )

    return serialize_ticket(db_ticket, db)


# ---------------------------------------------------------------------
# 3. GET SINGLE MAINTENANCE TICKET
# ---------------------------------------------------------------------
@router.get("/{ticket_id}")
@router.get("/{ticket_id}/")
def get_maintenance_ticket(
    ticket_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve single ticket by UUID or alphanumeric code."""
    org_id = parse_org_id(organization_id)
    record = find_ticket_record(db, ticket_id, org_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance ticket not found.")
    return serialize_ticket(record, db)


# ---------------------------------------------------------------------
# 4. UPDATE MAINTENANCE TICKET (PUT / PATCH)
# ---------------------------------------------------------------------
@router.put("/{ticket_id}")
@router.put("/{ticket_id}/")
@router.patch("/{ticket_id}")
@router.patch("/{ticket_id}/")
def update_maintenance_ticket(
    ticket_id: str,
    ticket_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Update ticket status, technician assignment, priority, or cost."""
    org_id = parse_org_id(organization_id)
    record = find_ticket_record(db, ticket_id, org_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance ticket not found.")

    old_status = getattr(record, "status", "")
    old_tech = getattr(record, "technician", "")

    for field, val in ticket_update.items():
        if hasattr(record, field):
            setattr(record, field, val)

    new_status = getattr(record, "status", old_status)
    new_tech = getattr(record, "technician", old_tech)

    # Trigger notification on status change or tech assignment
    if hasattr(models, "Notification") and (old_status != new_status or old_tech != new_tech):
        t_id = getattr(record, "ticket_id", "TCK")
        notif = models.Notification(
            id=uuid.uuid4(),
            organization_id=org_id,
            pov="admin",
            category="maintenance",
            status="unread",
            is_read=False,
            title=f"Maintenance Update ({t_id}): {new_status}",
            description=f"Ticket status changed to '{new_status}'. Assigned technician: {new_tech}.",
            property=getattr(record, "property_location", "Property Location"),
            tag=f"Status: {new_status}",
            urgent=str(new_status).lower() in ["urgent", "escalated"]
        )
        db.add(notif)

    db.commit()
    db.refresh(record)
    return serialize_ticket(record, db)


# ---------------------------------------------------------------------
# 5. DELETE MAINTENANCE TICKET
# ---------------------------------------------------------------------
@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{ticket_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance_ticket(
    ticket_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Permanently delete a maintenance ticket."""
    org_id = parse_org_id(organization_id)
    record = find_ticket_record(db, ticket_id, org_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance ticket not found.")

    try:
        db.delete(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting maintenance ticket: {str(e)}"
        )

    return None