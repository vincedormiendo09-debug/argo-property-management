import uuid
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

# Default Organization UUID matching schema.sql and seed.py
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

# Model resolver to support both MaintenanceTicket and MaintenanceRequest models
MaintenanceModel = getattr(models, "MaintenanceTicket", getattr(models, "MaintenanceRequest", None))


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="Sunrise Property Group")
        db.add(sandbox_org)
        db.commit()


def ensure_sandbox_unit(db: Session, org_id: uuid.UUID) -> models.Unit:
    """Ensures a Property, Building, and Unit exist to attach default maintenance tickets."""
    ensure_sandbox_organization(db, org_id)

    # 1. Parent Property
    prop = db.scalar(select(models.Property).where(models.Property.organization_id == org_id))
    if not prop:
        prop = models.Property(
            id=uuid.uuid4(),
            organization_id=org_id,
            code="PROP-001",
            name="Sunrise Residences",
            type="Residential",
            location="Parañaque, Metro Manila",
            units_count=2,
            status="Active"
        )
        db.add(prop)
        db.commit()
        db.refresh(prop)

    # 2. Parent Building
    bldg = db.scalar(select(models.Building).where(models.Building.organization_id == org_id))
    if not bldg:
        bldg = models.Building(
            id=uuid.uuid4(),
            organization_id=org_id,
            property_id=prop.id,
            code="BLDG-A",
            name="Tower A",
            floors=10,
            total_units=50,
            status="ACTIVE"
        )
        db.add(bldg)
        db.commit()
        db.refresh(bldg)

    # 3. Parent Unit
    unit = db.scalar(select(models.Unit).where(models.Unit.organization_id == org_id))
    if not unit:
        unit = models.Unit(
            id=uuid.uuid4(),
            organization_id=org_id,
            property_id=prop.id,
            building_id=bldg.id,
            unit_no="Unit 101",
            type="1BR",
            floor="1st Floor",
            rent=15000.0,
            status="OCCUPIED",
            subtitle="Sunrise Residences • Tower A • Unit 101"
        )
        db.add(unit)
        db.commit()
        db.refresh(unit)

    return unit


# 1. GET /api/maintenance/ - Fetch all maintenance tickets with filter and search capabilities
@router.get("/", response_model=List[schemas.MaintenanceSchema])
def read_maintenance_tickets(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    unit_id: Optional[uuid.UUID] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    priority: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(MaintenanceModel).where(
        MaintenanceModel.organization_id == organization_id
    )

    if unit_id:
        stmt = stmt.where(MaintenanceModel.unit_id == unit_id)
    if status_filter:
        stmt = stmt.where(MaintenanceModel.status.ilike(f"%{status_filter}%"))
    if priority:
        stmt = stmt.where(MaintenanceModel.priority.ilike(f"%{priority}%"))
    if category and hasattr(MaintenanceModel, "category"):
        stmt = stmt.where(MaintenanceModel.category.ilike(f"%{category}%"))

    if search:
        search_terms = []
        if hasattr(MaintenanceModel, "ticket_id"):
            search_terms.append(MaintenanceModel.ticket_id.ilike(f"%{search}%"))
        if hasattr(MaintenanceModel, "title"):
            search_terms.append(MaintenanceModel.title.ilike(f"%{search}%"))
        if hasattr(MaintenanceModel, "description"):
            search_terms.append(MaintenanceModel.description.ilike(f"%{search}%"))
        if hasattr(MaintenanceModel, "tenant_name"):
            search_terms.append(MaintenanceModel.tenant_name.ilike(f"%{search}%"))
        if hasattr(MaintenanceModel, "technician"):
            search_terms.append(MaintenanceModel.technician.ilike(f"%{search}%"))
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    tickets = list(db.scalars(stmt).all())

    # Seed default sandbox ticket if DB is empty for this organization
    if not tickets and not unit_id and not search:
        parent_unit = ensure_sandbox_unit(db, organization_id)
        default_ticket_data = {
            "id": uuid.uuid4(),
            "organization_id": organization_id,
            "unit_id": parent_unit.id,
            "description": "Master bedroom AC unit is dripping water onto floor.",
            "priority": "High",
            "status": "In Progress"
        }

        if hasattr(MaintenanceModel, "ticket_id"):
            default_ticket_data["ticket_id"] = "TCK-2026-001"
        if hasattr(MaintenanceModel, "title"):
            default_ticket_data["title"] = "AC Unit Leaking Water"
        if hasattr(MaintenanceModel, "category"):
            default_ticket_data["category"] = "HVAC / Aircon"
        if hasattr(MaintenanceModel, "tenant_name"):
            default_ticket_data["tenant_name"] = "Maria Santos"
        if hasattr(MaintenanceModel, "technician"):
            default_ticket_data["technician"] = "Roldan HVAC Services"
        if hasattr(MaintenanceModel, "cost"):
            default_ticket_data["cost"] = 1500.00

        default_tickets = [MaintenanceModel(**default_ticket_data)]
        db.add_all(default_tickets)
        db.commit()
        tickets = list(db.scalars(stmt).all())

    return tickets


# 2. POST /api/maintenance/ - Submit a new repair ticket with FK validation
@router.post("/", response_model=schemas.MaintenanceSchema, status_code=status.HTTP_201_CREATED)
def create_maintenance_ticket(
    ticket_in: schemas.MaintenanceCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(ticket_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    # Verify unit exists under this organization if unit_id is provided
    if ticket_in.unit_id:
        unit_stmt = select(models.Unit).where(
            models.Unit.id == ticket_in.unit_id,
            models.Unit.organization_id == org_id
        )
        unit = db.scalar(unit_stmt)
        if not unit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unit with ID '{ticket_in.unit_id}' not found in this organization."
            )

    ticket_data = ticket_in.dict(exclude_unset=True)
    if "id" not in ticket_data or not ticket_data["id"]:
        ticket_data["id"] = uuid.uuid4()
    if "organization_id" not in ticket_data:
        ticket_data["organization_id"] = org_id
    if "ticket_id" not in ticket_data and hasattr(MaintenanceModel, "ticket_id"):
        ticket_data["ticket_id"] = f"TCK-{datetime.now().year}-{str(uuid.uuid4())[:6].upper()}"

    db_ticket = MaintenanceModel(**ticket_data)
    db.add(db_ticket)

    # Automatically notify admins if high priority or urgent
    if hasattr(models, "Notification"):
        prio_str = str(ticket_data.get("priority", "")).lower()
        if prio_str in ["high", "urgent", "emergency"]:
            notif = models.Notification(
                id=uuid.uuid4(),
                organization_id=org_id,
                pov="admin",
                category="maintenance",
                status="unread",
                is_read=False,
                title="Urgent Maintenance Dispatch Logged",
                description=f"New urgent repair ticket submitted: '{ticket_data.get('title', ticket_data.get('description', 'Maintenance Request'))}'.",
                property=getattr(db_ticket, "unit_id", "Property Unit"),
                tag="Priority: Urgent",
                urgent=True
            )
            db.add(notif)

    db.commit()
    db.refresh(db_ticket)
    return db_ticket


# 3. GET /api/maintenance/{ticket_id} - Fetch single ticket by UUID or Ticket Code
@router.get("/{ticket_id}", response_model=schemas.MaintenanceSchema)
def get_maintenance_ticket(
    ticket_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(ticket_id)
        stmt = select(MaintenanceModel).where(
            MaintenanceModel.id == parsed_uuid,
            MaintenanceModel.organization_id == organization_id
        )
    except ValueError:
        if hasattr(MaintenanceModel, "ticket_id"):
            stmt = select(MaintenanceModel).where(
                MaintenanceModel.ticket_id == ticket_id,
                MaintenanceModel.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid maintenance ticket identifier format."
            )

    ticket = db.scalar(stmt)

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance ticket not found."
        )

    return ticket


# 4. PATCH & PUT /api/maintenance/{ticket_id} - Update status, technician, priority, or notes
@router.patch("/{ticket_id}", response_model=schemas.MaintenanceSchema)
@router.put("/{ticket_id}", response_model=schemas.MaintenanceSchema)
def update_maintenance_ticket(
    ticket_id: str,
    update_data: schemas.MaintenanceUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(ticket_id)
        stmt = select(MaintenanceModel).where(
            MaintenanceModel.id == parsed_uuid,
            MaintenanceModel.organization_id == organization_id
        )
    except ValueError:
        if hasattr(MaintenanceModel, "ticket_id"):
            stmt = select(MaintenanceModel).where(
                MaintenanceModel.ticket_id == ticket_id,
                MaintenanceModel.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid maintenance ticket identifier format."
            )

    db_ticket = db.scalar(stmt)

    if not db_ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance ticket not found."
        )

    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        if hasattr(db_ticket, field):
            setattr(db_ticket, field, value)

    db.commit()
    db.refresh(db_ticket)
    return db_ticket


# 5. DELETE /api/maintenance/{ticket_id} - Delete or archive maintenance ticket
@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_maintenance_ticket(
    ticket_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(ticket_id)
        stmt = select(MaintenanceModel).where(
            MaintenanceModel.id == parsed_uuid,
            MaintenanceModel.organization_id == organization_id
        )
    except ValueError:
        if hasattr(MaintenanceModel, "ticket_id"):
            stmt = select(MaintenanceModel).where(
                MaintenanceModel.ticket_id == ticket_id,
                MaintenanceModel.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid maintenance ticket identifier format."
            )

    db_ticket = db.scalar(stmt)
    if not db_ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance ticket not found."
        )

    db.delete(db_ticket)
    db.commit()
    return None