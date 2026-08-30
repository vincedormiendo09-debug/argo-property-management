import uuid
import logging
from datetime import datetime
from typing import List, Optional, Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from .. import models, schemas

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
    """Ensures a stub Organization exists in database to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


# ---------------------------------------------------------------------
# 1. GET PROPERTIES (Matches both /api/properties and /api/properties/)
# ---------------------------------------------------------------------
@router.get("")
@router.get("/")
def read_properties(
    organization_id: Optional[str] = Query(default=None),
    owner_id: Optional[str] = Query(default=None),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    ensure_sandbox_organization(db, org_id)

    stmt = select(models.Property).where(
        or_(
            models.Property.organization_id == org_id,
            models.Property.organization_id.is_(None)
        )
    )

    if owner_id and owner_id not in ("undefined", "null", "") and hasattr(models.Property, "owner_id"):
        try:
            stmt = stmt.where(models.Property.owner_id == uuid.UUID(owner_id))
        except ValueError:
            pass

    if type_filter:
        stmt = stmt.where(models.Property.type.ilike(f"%{type_filter.strip()}%"))
        
    if status_filter:
        stmt = stmt.where(models.Property.status.ilike(f"%{status_filter.strip()}%"))

    props = list(db.scalars(stmt).all())
    results: List[Dict[str, Any]] = []

    for p in props:
        pid_str = str(p.id)
        pname = getattr(p, "name", None) or getattr(p, "property_name", None) or "Property Asset"
        results.append({
            "id": pid_str,
            "organization_id": str(getattr(p, "organization_id", None) or org_id),
            "code": getattr(p, "code", f"PROP-{pid_str[:4].upper()}"),
            "name": pname,
            "property_name": pname,
            "type": getattr(p, "type", "Residential Multi-Family") or "Residential Multi-Family",
            "location": getattr(p, "location", "Metro Manila") or "Metro Manila",
            "tct_number": getattr(p, "tct_number", "TCT-REGISTERED") or "TCT-REGISTERED",
            "units_count": int(getattr(p, "units_count", 0) or 0),
            "occupancy": getattr(p, "occupancy", "0.0%"),
            "status": getattr(p, "status", "Active") or "Active"
        })

    if search:
        s = search.strip().lower()
        results = [
            r for r in results
            if s in (r.get("name") or "").lower()
            or s in (r.get("code") or "").lower()
            or s in (r.get("location") or "").lower()
            or s in (r.get("tct_number") or "").lower()
        ]

    return results


# ---------------------------------------------------------------------
# 2. CREATE PROPERTY (Matches POST /api/properties & POST /api/properties/)
# ---------------------------------------------------------------------
@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_property(
    prop_in: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(prop_in.get("organization_id") or organization_id)
    ensure_sandbox_organization(db, org_id)

    prop_name = (prop_in.get("name") or prop_in.get("property_name") or "").strip()
    if not prop_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Property name is required."
        )

    code = (prop_in.get("code") or f"PROP-{str(uuid.uuid4())[:4].upper()}").strip()
    location = (prop_in.get("location") or "Metro Manila").strip()
    tct = (prop_in.get("tct_number") or "TCT-REGISTERED").strip()
    prop_type = prop_in.get("type") or "Residential Multi-Family"
    status_val = prop_in.get("status") or "Active"

    # Scoped duplicate check on code
    existing = db.scalar(
        select(models.Property).where(
            models.Property.organization_id == org_id,
            models.Property.code.ilike(code)
        )
    )
    if existing:
        code = f"{code}-{str(uuid.uuid4())[:3].upper()}"

    new_id = uuid.uuid4()
    if prop_in.get("id"):
        try:
            new_id = uuid.UUID(str(prop_in["id"]))
        except ValueError:
            pass

    db_prop = models.Property(
        id=new_id,
        organization_id=org_id,
        code=code,
        name=prop_name,
        property_name=prop_name,
        type=prop_type,
        location=location,
        tct_number=tct,
        units_count=int(prop_in.get("units_count") or 0),
        status=status_val
    )

    if hasattr(db_prop, "owner_id") and prop_in.get("owner_id"):
        try:
            db_prop.owner_id = uuid.UUID(str(prop_in["owner_id"]))
        except ValueError:
            pass

    db.add(db_prop)
    db.commit()
    db.refresh(db_prop)

    return {
        "id": str(db_prop.id),
        "organization_id": str(db_prop.organization_id),
        "code": db_prop.code,
        "name": db_prop.name,
        "property_name": db_prop.property_name,
        "type": db_prop.type,
        "location": db_prop.location,
        "tct_number": db_prop.tct_number,
        "units_count": db_prop.units_count,
        "status": db_prop.status
    }


# ---------------------------------------------------------------------
# 3. GET SINGLE PROPERTY
# ---------------------------------------------------------------------
@router.get("/{property_id}")
@router.get("/{property_id}/")
def get_property(
    property_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    clean_id = property_id.strip()

    prop = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        prop = db.scalar(
            select(models.Property).where(
                models.Property.id == parsed_uuid,
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not prop and hasattr(models.Property, "code"):
        prop = db.scalar(
            select(models.Property).where(
                models.Property.code.ilike(clean_id),
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )

    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    pname = getattr(prop, "name", None) or getattr(prop, "property_name", None) or "Property Asset"
    return {
        "id": str(prop.id),
        "organization_id": str(prop.organization_id or org_id),
        "code": prop.code,
        "name": pname,
        "property_name": pname,
        "type": prop.type,
        "location": prop.location,
        "tct_number": prop.tct_number,
        "units_count": prop.units_count,
        "status": prop.status
    }


# ---------------------------------------------------------------------
# 4. UPDATE PROPERTY (PUT / PATCH)
# ---------------------------------------------------------------------
@router.put("/{property_id}")
@router.put("/{property_id}/")
@router.patch("/{property_id}")
@router.patch("/{property_id}/")
def update_property(
    property_id: str,
    prop_update: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    clean_id = property_id.strip()

    db_prop = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        db_prop = db.scalar(
            select(models.Property).where(
                models.Property.id == parsed_uuid,
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not db_prop and hasattr(models.Property, "code"):
        db_prop = db.scalar(
            select(models.Property).where(
                models.Property.code.ilike(clean_id),
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )

    if not db_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    if "code" in prop_update and prop_update["code"]:
        clean_code = prop_update["code"].strip()
        if clean_code.lower() != (getattr(db_prop, "code", "") or "").lower():
            code_check = db.scalar(
                select(models.Property).where(
                    models.Property.organization_id == org_id,
                    models.Property.code.ilike(clean_code),
                    models.Property.id != db_prop.id
                )
            )
            if code_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Property code '{clean_code}' is already in use."
                )

    for field, value in prop_update.items():
        if hasattr(db_prop, field):
            setattr(db_prop, field, value)

    db.commit()
    db.refresh(db_prop)
    
    pname = getattr(db_prop, "name", None) or getattr(db_prop, "property_name", None) or "Property Asset"
    return {
        "id": str(db_prop.id),
        "organization_id": str(db_prop.organization_id),
        "code": db_prop.code,
        "name": pname,
        "property_name": pname,
        "type": db_prop.type,
        "location": db_prop.location,
        "tct_number": db_prop.tct_number,
        "units_count": db_prop.units_count,
        "status": db_prop.status
    }


# ---------------------------------------------------------------------
# 5. DELETE PROPERTY
# ---------------------------------------------------------------------
@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/{property_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(
    property_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_org_id(organization_id)
    clean_id = property_id.strip()

    db_prop = None
    try:
        parsed_uuid = uuid.UUID(clean_id)
        db_prop = db.scalar(
            select(models.Property).where(
                models.Property.id == parsed_uuid,
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )
    except ValueError:
        pass

    if not db_prop and hasattr(models.Property, "code"):
        db_prop = db.scalar(
            select(models.Property).where(
                models.Property.code.ilike(clean_id),
                or_(
                    models.Property.organization_id == org_id,
                    models.Property.organization_id.is_(None)
                )
            )
        )

    if not db_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    try:
        db.delete(db_prop)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete property because active buildings, units, or leases are linked to it."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting property: {str(e)}"
        )

    return None