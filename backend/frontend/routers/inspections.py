import uuid
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


@router.get("/", response_model=List[schemas.InspectionSchema])
def read_inspections(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    stmt = select(models.Inspection).where(models.Inspection.organization_id == organization_id)

    if type_filter:
        stmt = stmt.where(models.Inspection.type.ilike(f"%{type_filter}%"))
    if status_filter:
        stmt = stmt.where(models.Inspection.status.ilike(f"%{status_filter}%"))
    if search:
        search_terms = [
            models.Inspection.inspection_id.ilike(f"%{search}%"),
            models.Inspection.unit_name.ilike(f"%{search}%"),
            models.Inspection.tenant.ilike(f"%{search}%"),
            models.Inspection.property_info.ilike(f"%{search}%")
        ]
        stmt = stmt.where(or_(*search_terms))

    inspections = list(db.scalars(stmt).all())

    # Fallback seed if DB is empty
    if not inspections and not search and not type_filter:
        default_insp = models.Inspection(
            id=uuid.uuid4(),
            organization_id=organization_id,
            inspection_id="INS-2026-001",
            unit_name="Unit 101",
            property_info="Sunrise Residences • Tower A",
            tenant="Maria Santos",
            type="Move-in",
            date=date(2026, 1, 1),
            inspector="Property Admin",
            status="Completed",
            notes="Full move-in inspection and key handover cleared."
        )
        db.add(default_insp)
        db.commit()
        inspections = list(db.scalars(stmt).all())

    return inspections


@router.post("/", response_model=schemas.InspectionSchema, status_code=status.HTTP_201_CREATED)
def create_inspection(
    inspection_in: schemas.InspectionCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(inspection_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    insp_data = inspection_in.model_dump(exclude_unset=True) if hasattr(inspection_in, "model_dump") else inspection_in.dict(exclude_unset=True)
    
    if "id" not in insp_data or not insp_data["id"]:
        insp_data["id"] = uuid.uuid4()
    insp_data["organization_id"] = org_id
    if "inspection_id" not in insp_data or not insp_data["inspection_id"]:
        insp_data["inspection_id"] = f"INS-{str(uuid.uuid4())[:4].upper()}"

    db_insp = models.Inspection(**insp_data)
    db.add(db_insp)
    db.commit()
    db.refresh(db_insp)
    return db_insp


@router.get("/{inspection_id}", response_model=schemas.InspectionSchema)
def get_inspection(
    inspection_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(inspection_id)
        stmt = select(models.Inspection).where(
            models.Inspection.id == parsed_uuid,
            models.Inspection.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Inspection).where(
            models.Inspection.inspection_id == inspection_id,
            models.Inspection.organization_id == organization_id
        )

    insp = db.scalar(stmt)
    if not insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection record not found.")
    return insp


@router.put("/{inspection_id}", response_model=schemas.InspectionSchema)
@router.patch("/{inspection_id}", response_model=schemas.InspectionSchema)
def update_inspection(
    inspection_id: str,
    insp_update: schemas.InspectionUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(inspection_id)
        stmt = select(models.Inspection).where(
            models.Inspection.id == parsed_uuid,
            models.Inspection.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Inspection).where(
            models.Inspection.inspection_id == inspection_id,
            models.Inspection.organization_id == organization_id
        )

    db_insp = db.scalar(stmt)
    if not db_insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection record not found.")

    update_data = insp_update.model_dump(exclude_unset=True) if hasattr(insp_update, "model_dump") else insp_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_insp, field):
            setattr(db_insp, field, value)

    db.commit()
    db.refresh(db_insp)
    return db_insp


@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inspection(
    inspection_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(inspection_id)
        stmt = select(models.Inspection).where(
            models.Inspection.id == parsed_uuid,
            models.Inspection.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Inspection).where(
            models.Inspection.inspection_id == inspection_id,
            models.Inspection.organization_id == organization_id
        )

    db_insp = db.scalar(stmt)
    if not db_insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection record not found.")

    db.delete(db_insp)
    db.commit()
    return None