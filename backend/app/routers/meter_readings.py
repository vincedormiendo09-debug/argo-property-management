import uuid
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
        sandbox_org = models.Organization(id=org_id, name="Sunrise Property Group")
        db.add(sandbox_org)
        db.commit()


@router.get("/", response_model=List[schemas.MeterReadingSchema])
def read_meter_readings(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    utility: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    period: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    stmt = select(models.MeterReading).where(models.MeterReading.organization_id == organization_id)

    if utility:
        stmt = stmt.where(models.MeterReading.utility.ilike(f"%{utility}%"))
    if status_filter:
        stmt = stmt.where(models.MeterReading.status.ilike(f"%{status_filter}%"))
    if period:
        stmt = stmt.where(models.MeterReading.period.ilike(f"%{period}%"))

    if search:
        search_terms = [
            models.MeterReading.tenant_name.ilike(f"%{search}%"),
            models.MeterReading.unit_location.ilike(f"%{search}%"),
            models.MeterReading.serial.ilike(f"%{search}%"),
            models.MeterReading.period.ilike(f"%{search}%")
        ]
        stmt = stmt.where(or_(*search_terms))

    readings = list(db.scalars(stmt).all())

    # Fallback seed if DB is empty
    if not readings and not search and not utility:
        default_readings = [
            models.MeterReading(
                id=uuid.uuid4(),
                organization_id=organization_id,
                tenant_name="Maria Santos",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                utility="Meralco",
                serial="MER-992810",
                prev_dial=1420.50,
                curr_dial=1610.00,
                consumption=189.50,
                unit_symbol="kWh",
                period="August 2026",
                status="Billed to Ledger"
            ),
            models.MeterReading(
                id=uuid.uuid4(),
                organization_id=organization_id,
                tenant_name="Maria Santos",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                utility="Maynilad",
                serial="MAY-441209",
                prev_dial=312.00,
                curr_dial=328.50,
                consumption=16.50,
                unit_symbol="cu.m",
                period="August 2026",
                status="Billed to Ledger"
            )
        ]
        db.add_all(default_readings)
        db.commit()
        readings = list(db.scalars(stmt).all())

    return readings


@router.post("/", response_model=schemas.MeterReadingSchema, status_code=status.HTTP_201_CREATED)
def create_meter_reading(
    reading_in: schemas.MeterReadingCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(reading_in, "organization_id", DEFAULT_ORG_ID)
    ensure_sandbox_organization(db, org_id)

    reading_data = reading_in.dict(exclude_unset=True)
    if "id" not in reading_data or not reading_data["id"]:
        reading_data["id"] = uuid.uuid4()
    reading_data["organization_id"] = org_id

    # Auto-calculate consumption if dials provided
    prev = float(reading_data.get("prev_dial", 0.0))
    curr = float(reading_data.get("curr_dial", 0.0))
    if curr >= prev and (not reading_data.get("consumption") or reading_data["consumption"] == 0.0):
        reading_data["consumption"] = round(curr - prev, 2)

    db_reading = models.MeterReading(**reading_data)
    db.add(db_reading)
    db.commit()
    db.refresh(db_reading)
    return db_reading


@router.get("/{reading_id}", response_model=schemas.MeterReadingSchema)
def get_meter_reading(
    reading_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.MeterReading).where(
        models.MeterReading.id == reading_id,
        models.MeterReading.organization_id == organization_id
    )
    reading = db.scalar(stmt)
    if not reading:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter reading not found.")
    return reading


@router.put("/{reading_id}", response_model=schemas.MeterReadingSchema)
@router.patch("/{reading_id}", response_model=schemas.MeterReadingSchema)
def update_meter_reading(
    reading_id: uuid.UUID,
    reading_update: schemas.MeterReadingUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.MeterReading).where(
        models.MeterReading.id == reading_id,
        models.MeterReading.organization_id == organization_id
    )
    db_reading = db.scalar(stmt)
    if not db_reading:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter reading not found.")

    update_data = reading_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(db_reading, field):
            setattr(db_reading, field, value)

    # Recalculate consumption if current dial updated
    if "curr_dial" in update_data and float(db_reading.curr_dial) >= float(db_reading.prev_dial):
        db_reading.consumption = round(float(db_reading.curr_dial) - float(db_reading.prev_dial), 2)

    db.commit()
    db.refresh(db_reading)
    return db_reading


@router.delete("/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meter_reading(
    reading_id: uuid.UUID,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    stmt = select(models.MeterReading).where(
        models.MeterReading.id == reading_id,
        models.MeterReading.organization_id == organization_id
    )
    db_reading = db.scalar(stmt)
    if not db_reading:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter reading not found.")

    db.delete(db_reading)
    db.commit()
    return None