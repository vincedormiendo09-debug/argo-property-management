import uuid
import logging
from datetime import date, datetime
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


def serialize_reading(item: Any, db: Session) -> Dict[str, Any]:
    """Helper to return a standardized meter reading dictionary for frontend views."""
    r_id = str(getattr(item, "id", "") or "")
    code = getattr(item, "reading_id", None) or f"RDR-{r_id[:6].upper()}"

    prev_d = float(getattr(item, "prev_dial", 0) or 0)
    curr_d = float(getattr(item, "curr_dial", 0) or 0)
    cons = float(getattr(item, "consumption", 0) or max(0.0, curr_d - prev_d))

    return {
        "id": r_id,
        "reading_id": code,
        "organization_id": str(getattr(item, "organization_id", "") or ""),
        "unit_id": str(getattr(item, "unit_id", "") or ""),
        "tenant_name": getattr(item, "tenant_name", None) or "Resident Tenant",
        "unit_location": getattr(item, "unit_location", None) or "Unit Location",
        "utility": getattr(item, "utility", "Electricity") or "Electricity",
        "serial": getattr(item, "serial", "") or "",
        "prev_dial": prev_d,
        "curr_dial": curr_d,
        "consumption": cons,
        "unit_symbol": getattr(item, "unit_symbol", "kWh") or "kWh",
        "period": getattr(item, "period", None) or "Current Period",
        "status": getattr(item, "status", "Billed") or "Billed",
        "notes": getattr(item, "notes", None) or ""
    }


def find_reading_record(db: Session, reading_id: str, org_id: uuid.UUID):
    """Locates a meter reading record by UUID or reading_id code."""
    clean_id = reading_id.strip()

    if hasattr(models, "MeterReading"):
        try:
            parsed_uuid = uuid.UUID(clean_id)
            record = db.scalar(
                select(models.MeterReading).where(
                    models.MeterReading.id == parsed_uuid,
                    or_(
                        models.MeterReading.organization_id == org_id,
                        models.MeterReading.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record
        except ValueError:
            pass

        if hasattr(models.MeterReading, "reading_id"):
            record = db.scalar(
                select(models.MeterReading).where(
                    models.MeterReading.reading_id.ilike(clean_id),
                    or_(
                        models.MeterReading.organization_id == org_id,
                        models.MeterReading.organization_id.is_(None)
                    )
                )
            )
            if record:
                return record

    return None


# ---------------------------------------------------------------------
# 1. GET METER READINGS (Dual Route)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_meter_readings(
    organization_id: Optional[str] = Query(default=None),
    unit_id: Optional[str] = Query(default=None),
    utility: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    period: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Retrieve all logged meter readings."""
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    stmt = select(models.MeterReading).where(
        or_(
            models.MeterReading.organization_id == org_id,
            models.MeterReading.organization_id.is_(None)
        )
    )

    if unit_id:
        try:
            stmt = stmt.where(models.MeterReading.unit_id == uuid.UUID(unit_id.strip()))
        except ValueError:
            pass

    if utility:
        stmt = stmt.where(models.MeterReading.utility.ilike(f"%{utility.strip()}%"))

    if status_filter:
        stmt = stmt.where(models.MeterReading.status.ilike(f"%{status_filter.strip()}%"))

    if period:
        stmt = stmt.where(models.MeterReading.period.ilike(f"%{period.strip()}%"))

    readings = list(db.scalars(stmt).all())
    serialized = [serialize_reading(r, db) for r in readings]

    if search:
        s = search.strip().lower()
        serialized = [
            r for r in serialized
            if s in str(r.get("reading_id", "")).lower()
            or s in str(r.get("tenant_name", "")).lower()
            or s in str(r.get("unit_location", "")).lower()
            or s in str(r.get("serial", "")).lower()
            or s in str(r.get("utility", "")).lower()
            or s in str(r.get("period", "")).lower()
        ]

    return serialized


# ---------------------------------------------------------------------
# 2. CREATE METER READING (Dual Route: Resolves HTTP 405)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_meter_reading(
    reading_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Log a new baseline / sub-meter reading."""
    org_id = parse_org_id(reading_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    prev_dial = float(reading_in.get("prev_dial") or reading_in.get("reading_prev") or 0.0)
    curr_dial = float(reading_in.get("curr_dial") or reading_in.get("reading_curr") or 0.0)
    consumption = float(reading_in.get("consumption") or max(0.0, curr_dial - prev_dial))

    # Safe FK Validation for Unit ID
    unit_id_val = None
    if reading_in.get("unit_id"):
        try:
            parsed_u = uuid.UUID(str(reading_in["unit_id"]).strip())
            if db.scalar(select(models.Unit).where(models.Unit.id == parsed_u)):
                unit_id_val = parsed_u
        except ValueError:
            pass

    tenant_name = reading_in.get("tenant_name") or "Resident Tenant"
    unit_location = reading_in.get("unit_location") or "Unit Location"
    utility_type = reading_in.get("utility") or reading_in.get("utility_type") or "Electricity"
    serial = str(reading_in.get("serial") or reading_in.get("serial_number") or "")
    unit_symbol = "cu.m" if "water" in utility_type.lower() or "maynilad" in utility_type.lower() else "kWh"
    period = reading_in.get("period") or reading_in.get("billing_period") or datetime.now().strftime("%B %Y")
    reading_code = reading_in.get("reading_id") or f"RDR-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"
    status_val = str(reading_in.get("status") or "Billed")
    notes_val = str(reading_in.get("notes") or reading_in.get("remarks") or "")

    record_data = {
        "id": uuid.uuid4(),
        "organization_id": org_id,
        "unit_id": unit_id_val,
        "reading_id": reading_code,
        "tenant_name": tenant_name,
        "unit_location": unit_location,
        "utility": utility_type,
        "serial": serial,
        "prev_dial": prev_dial,
        "curr_dial": curr_dial,
        "consumption": consumption,
        "unit_symbol": unit_symbol,
        "period": period,
        "status": status_val,
        "notes": notes_val
    }

    filtered_kwargs = {k: v for k, v in record_data.items() if hasattr(models.MeterReading, k)}
    db_record = models.MeterReading(**filtered_kwargs)
    db.add(db_record)

    try:
        db.commit()
        db.refresh(db_record)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Database error saving meter reading: {str(e)}"
        )

    return serialize_reading(db_record, db)


# ---------------------------------------------------------------------
# 3. GET SINGLE METER READING
# ---------------------------------------------------------------------
@router.get("/{reading_id}")
@router.get("/{reading_id}/")
def get_meter_reading(
    reading_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Fetch a single meter reading record."""
    org_id = parse_org_id(organization_id)
    record = find_reading_record(db, reading_id, org_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter reading not found.")
    return serialize_reading(record, db)


# ---------------------------------------------------------------------
# 4. UPDATE METER READING (PUT / PATCH)
# ---------------------------------------------------------------------
@router.put("/{reading_id}")
@router.put("/{reading_id}/")
@router.patch("/{reading_id}")
@router.patch("/{reading_id}/")
def update_meter_reading(
    reading_id: str,
    reading_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Update existing meter reading and recalculate net consumption."""
    org_id = parse_org_id(organization_id)
    record = find_reading_record(db, reading_id, org_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter reading not found.")

    for field, val in reading_update.items():
        if hasattr(record, field):
            setattr(record, field, val)

    if "curr_dial" in reading_update or "prev_dial" in reading_update:
        prev_d = float(getattr(record, "prev_dial", 0) or 0)
        curr_d = float(getattr(record, "curr_dial", 0) or 0)
        record.consumption = max(0.0, curr_d - prev_d)

    db.commit()
    db.refresh(record)
    return serialize_reading(record, db)


# ---------------------------------------------------------------------
# 5. DELETE METER READING
# ---------------------------------------------------------------------
@router.delete("/{reading_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{reading_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_meter_reading(
    reading_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """Delete a meter reading record."""
    org_id = parse_org_id(organization_id)
    record = find_reading_record(db, reading_id, org_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meter reading not found.")

    try:
        db.delete(record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting record: {str(e)}"
        )

    return None