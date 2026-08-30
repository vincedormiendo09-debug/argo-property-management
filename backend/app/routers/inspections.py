import uuid
from datetime import date, datetime
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()

DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def parse_org_id(org_id_raw: Optional[Any]) -> uuid.UUID:
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
    """Ensures a stub Organization exists in local DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def parse_date_value(val: Any) -> date:
    """Safely parses string dates into Python date objects."""
    if not val:
        return date.today()
    if isinstance(val, (date, datetime)):
        return val if isinstance(val, date) else val.date()
    try:
        clean_str = str(val).strip()
        if not clean_str or clean_str.lower() in ("null", "undefined"):
            return date.today()
        return datetime.fromisoformat(clean_str.replace("Z", "")).date()
    except Exception:
        try:
            return datetime.strptime(str(val).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            return date.today()


# 1. GET /api/inspections/ - Fetch all inspection records
@router.get("", response_model=List[schemas.InspectionSchema])
@router.get("/", response_model=List[schemas.InspectionSchema])
def read_inspections(
    organization_id: Optional[str] = Query(default=None),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)
    stmt = select(models.Inspection).where(models.Inspection.organization_id == org_id)

    if type_filter:
        stmt = stmt.where(models.Inspection.type.ilike(f"%{type_filter.strip()}%"))
    if status_filter:
        stmt = stmt.where(models.Inspection.status.ilike(f"%{status_filter.strip()}%"))
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
            organization_id=org_id,
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


# 2. POST /api/inspections/ - Record a new inspection (Dual route prevents 405)
@router.post("", response_model=schemas.InspectionSchema, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=schemas.InspectionSchema, status_code=status.HTTP_201_CREATED)
def create_inspection(
    inspection_in: Any,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    if hasattr(inspection_in, "model_dump"):
        insp_data = inspection_in.model_dump(exclude_unset=True)
    elif hasattr(inspection_in, "dict"):
        insp_data = inspection_in.dict(exclude_unset=True)
    elif isinstance(inspection_in, dict):
        insp_data = inspection_in
    else:
        insp_data = {}

    org_id = parse_org_id(insp_data.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    if "id" not in insp_data or not insp_data["id"]:
        insp_data["id"] = uuid.uuid4()
    else:
        try:
            insp_data["id"] = uuid.UUID(str(insp_data["id"]))
        except ValueError:
            insp_data["id"] = uuid.uuid4()

    insp_data["organization_id"] = org_id

    if "inspection_id" not in insp_data or not insp_data["inspection_id"]:
        insp_data["inspection_id"] = f"INS-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    if "date" in insp_data:
        insp_data["date"] = parse_date_value(insp_data["date"])
    elif "inspection_date" in insp_data:
        insp_data["date"] = parse_date_value(insp_data["inspection_date"])

    filtered_kwargs = {k: v for k, v in insp_data.items() if hasattr(models.Inspection, k)}
    db_insp = models.Inspection(**filtered_kwargs)
    db.add(db_insp)
    db.commit()
    db.refresh(db_insp)
    return db_insp


# 3. GET /api/inspections/{inspection_id} - Fetch single inspection
@router.get("/{inspection_id}", response_model=schemas.InspectionSchema)
@router.get("/{inspection_id}/", response_model=schemas.InspectionSchema)
def get_inspection(
    inspection_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    try:
        parsed_uuid = uuid.UUID(inspection_id)
        stmt = select(models.Inspection).where(
            models.Inspection.id == parsed_uuid,
            models.Inspection.organization_id == org_id
        )
    except ValueError:
        stmt = select(models.Inspection).where(
            models.Inspection.inspection_id.ilike(inspection_id),
            models.Inspection.organization_id == org_id
        )

    insp = db.scalar(stmt)
    if not insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection record not found.")
    return insp


# 4. PUT / PATCH /api/inspections/{inspection_id} - Update inspection details
@router.put("/{inspection_id}", response_model=schemas.InspectionSchema)
@router.put("/{inspection_id}/", response_model=schemas.InspectionSchema)
@router.patch("/{inspection_id}", response_model=schemas.InspectionSchema)
@router.patch("/{inspection_id}/", response_model=schemas.InspectionSchema)
def update_inspection(
    inspection_id: str,
    insp_update: Any,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    try:
        parsed_uuid = uuid.UUID(inspection_id)
        stmt = select(models.Inspection).where(
            models.Inspection.id == parsed_uuid,
            models.Inspection.organization_id == org_id
        )
    except ValueError:
        stmt = select(models.Inspection).where(
            models.Inspection.inspection_id.ilike(inspection_id),
            models.Inspection.organization_id == org_id
        )

    db_insp = db.scalar(stmt)
    if not db_insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection record not found.")

    if hasattr(insp_update, "model_dump"):
        update_data = insp_update.model_dump(exclude_unset=True)
    elif hasattr(insp_update, "dict"):
        update_data = insp_update.dict(exclude_unset=True)
    elif isinstance(insp_update, dict):
        update_data = insp_update
    else:
        update_data = {}

    for field, value in update_data.items():
        if hasattr(db_insp, field):
            if field in ("date", "inspection_date") and value:
                setattr(db_insp, field, parse_date_value(value))
            else:
                setattr(db_insp, field, value)

    db.commit()
    db.refresh(db_insp)
    return db_insp


# 5. DELETE /api/inspections/{inspection_id} - Remove an inspection record
@router.delete("/{inspection_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{inspection_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_inspection(
    inspection_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    try:
        parsed_uuid = uuid.UUID(inspection_id)
        stmt = select(models.Inspection).where(
            models.Inspection.id == parsed_uuid,
            models.Inspection.organization_id == org_id
        )
    except ValueError:
        stmt = select(models.Inspection).where(
            models.Inspection.inspection_id.ilike(inspection_id),
            models.Inspection.organization_id == org_id
        )

    db_insp = db.scalar(stmt)
    if not db_insp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inspection record not found.")

    db.delete(db_insp)
    db.commit()
    return None