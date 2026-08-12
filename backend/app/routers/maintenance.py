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


def ensure_sandbox_unit(db: Session, org_id: uuid.UUID) -> models.Unit:
    """Ensures a Property and Unit exist to attach default maintenance tickets."""
    ensure_sandbox_organization(db, org_id)

    # 1. Parent Property
    prop = db.scalar(select(models.Property).where(models.Property.organization_id == org_id))
    if not prop:
        prop = models.Property(
            id=uuid.uuid4(),
            organization_id=org_id,
            code="PROP-001",
            name="Sunrise Property",
            type="Residential",
            location="Parañaque, Metro Manila",
            status="Active"
        )
        db.add(prop)
        db.commit()
        db.refresh(prop)

    # 2. Parent Unit
    unit = db.scalar(select(models.Unit).where(models.Unit.organization_id == org_id))
    if not unit:
        unit = models.Unit(
            id=uuid.uuid4(),
            organization_id=org_id,
            property_id=prop.id,
            unit_no="Unit 101",
            type="1BR",
            rent=15000.0,
            status="OCCUPIED"
        )
        db.add(unit)
        db.commit()
        db.refresh(unit)

    return unit


# 1. GET /api/maintenance/ - Fetch all maintenance tickets for an organization
@router.get("/", response_model=List[schemas.MaintenanceSchema])
def read_maintenance_tickets(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    unit_id: Optional[uuid.UUID] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.MaintenanceRequest).where(
        models.MaintenanceRequest.organization_id == organization_id
    )
    if unit_id:
        stmt = stmt.where(models.MaintenanceRequest.unit_id == unit_id)

    tickets = list(db.scalars(stmt).all())

    # Seed default sandbox ticket if DB is empty for this org
    if not tickets and not unit_id:
        parent_unit = ensure_sandbox_unit(db, organization_id)
        default_tickets = [
            models.MaintenanceRequest(
                id=uuid.uuid4(),
                organization_id=organization_id,
                unit_id=parent_unit.id,
                description="Water dripping from Master Bedroom split-type aircon onto floor.",
                priority="High",
                status="Open"
            )
        ]
        db.add_all(default_tickets)
        db.commit()
        tickets = list(db.scalars(stmt).all())

    return tickets


# 2. POST /api/maintenance/ - Submit a new repair ticket
@router.post("/", response_model=schemas.MaintenanceSchema, status_code=status.HTTP_201_CREATED)
def create_maintenance_ticket(
    ticket_in: schemas.MaintenanceCreate,
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, ticket_in.organization_id)

    # Verify unit exists under this organization
    unit_stmt = select(models.Unit).where(
        models.Unit.id == ticket_in.unit_id,
        models.Unit.organization_id == ticket_in.organization_id
    )
    if not db.scalar(unit_stmt):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit with ID '{ticket_in.unit_id}' not found in this organization."
        )

    db_ticket = models.MaintenanceRequest(
        id=uuid.uuid4(),
        organization_id=ticket_in.organization_id,
        unit_id=ticket_in.unit_id,
        description=ticket_in.description,
        priority=ticket_in.priority,
        status=ticket_in.status,
        created_by=ticket_in.created_by
    )

    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    return db_ticket


# 3. GET /api/maintenance/{ticket_id} - Fetch a single ticket by UUID
@router.get("/{ticket_id}", response_model=schemas.MaintenanceSchema)
def get_maintenance_ticket(
    ticket_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.MaintenanceRequest).where(
        models.MaintenanceRequest.id == ticket_id,
        models.MaintenanceRequest.organization_id == organization_id
    )
    ticket = db.scalar(stmt)

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance ticket not found."
        )

    return ticket


# 4. PATCH /api/maintenance/{ticket_id} - Update status or priority
@router.patch("/{ticket_id}", response_model=schemas.MaintenanceSchema)
def update_maintenance_ticket(
    ticket_id: uuid.UUID,
    update_data: schemas.MaintenanceUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.MaintenanceRequest).where(
        models.MaintenanceRequest.id == ticket_id,
        models.MaintenanceRequest.organization_id == organization_id
    )
    db_ticket = db.scalar(stmt)

    if not db_ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance ticket not found."
        )

    if update_data.description is not None:
        db_ticket.description = update_data.description
    if update_data.priority is not None:
        db_ticket.priority = update_data.priority
    if update_data.status is not None:
        db_ticket.status = update_data.status
    if update_data.updated_by is not None:
        db_ticket.updated_by = update_data.updated_by

    db.commit()
    db.refresh(db_ticket)
    return db_ticket