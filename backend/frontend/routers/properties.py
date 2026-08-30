import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from ..database import get_db
from .. import models, schemas

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

# Default Organization UUID matching schema.sql and seed.py
DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures a stub Organization exists in database to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


# 1. GET /api/properties/ - Read real properties with owner, type, status, and search filters
@router.get("/", response_model=List[schemas.PropertySchema])
def read_properties(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    owner_id: Optional[uuid.UUID] = Query(default=None),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)

    stmt = select(models.Property).where(models.Property.organization_id == organization_id)

    # Filter by specific Owner (used by Owner portal views)
    if owner_id and hasattr(models.Property, "owner_id"):
        stmt = stmt.where(models.Property.owner_id == owner_id)

    if type_filter:
        stmt = stmt.where(models.Property.type.ilike(f"%{type_filter.strip()}%"))
        
    if status_filter:
        stmt = stmt.where(models.Property.status.ilike(f"%{status_filter.strip()}%"))

    if search:
        search_term = search.strip()
        search_terms = []
        if hasattr(models.Property, "name"):
            search_terms.append(models.Property.name.ilike(f"%{search_term}%"))
        if hasattr(models.Property, "code"):
            search_terms.append(models.Property.code.ilike(f"%{search_term}%"))
        if hasattr(models.Property, "location"):
            search_terms.append(models.Property.location.ilike(f"%{search_term}%"))
        if hasattr(models.Property, "address"):
            search_terms.append(models.Property.address.ilike(f"%{search_term}%"))
        if hasattr(models.Property, "tct_number"):
            search_terms.append(models.Property.tct_number.ilike(f"%{search_term}%"))
            
        if search_terms:
            stmt = stmt.where(or_(*search_terms))

    return list(db.scalars(stmt).all())


# 2. POST /api/properties/ - Create a property with org-scoped duplicate check
@router.post("/", response_model=schemas.PropertySchema, status_code=status.HTTP_201_CREATED)
def create_property(prop_in: schemas.PropertyCreate, db: Session = Depends(get_db)):
    org_id = getattr(prop_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    prop_data = prop_in.model_dump(exclude_unset=True) if hasattr(prop_in, "model_dump") else prop_in.dict(exclude_unset=True)
    
    prop_code = prop_data.get("code") or f"PROP-{str(uuid.uuid4())[:4].upper()}"

    # Scoped duplicate check: (organization_id, code) must be unique
    existing = db.scalar(
        select(models.Property).where(
            models.Property.organization_id == org_id,
            models.Property.code.ilike(prop_code.strip())
        )
    )

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Property code '{prop_code}' already exists for this organization."
        )

    if "id" not in prop_data or not prop_data["id"]:
        prop_data["id"] = uuid.uuid4()
    if "organization_id" not in prop_data or not prop_data["organization_id"]:
        prop_data["organization_id"] = org_id
        
    prop_data["code"] = prop_code.strip()
    
    if "status" not in prop_data or not prop_data["status"]:
        prop_data["status"] = "Active"

    db_prop = models.Property(**prop_data)
    db.add(db_prop)
    db.commit()
    db.refresh(db_prop)
    return db_prop


# 3. GET /api/properties/{property_id} - Fetch a single property by UUID or Property Code
@router.get("/{property_id}", response_model=schemas.PropertySchema)
def get_property(
    property_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(property_id)
        stmt = select(models.Property).where(
            models.Property.id == parsed_uuid,
            models.Property.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Property, "code"):
            stmt = select(models.Property).where(
                models.Property.code.ilike(property_id.strip()),
                models.Property.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid property identifier format."
            )

    prop = db.scalar(stmt)
    if not prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    return prop


# 4. PUT / PATCH /api/properties/{property_id} - Update property specifications
@router.put("/{property_id}", response_model=schemas.PropertySchema)
@router.patch("/{property_id}", response_model=schemas.PropertySchema)
def update_property(
    property_id: str,
    prop_update: schemas.PropertyUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(property_id)
        stmt = select(models.Property).where(
            models.Property.id == parsed_uuid,
            models.Property.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Property, "code"):
            stmt = select(models.Property).where(
                models.Property.code.ilike(property_id.strip()),
                models.Property.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid property identifier format."
            )

    db_prop = db.scalar(stmt)
    if not db_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    update_data = prop_update.model_dump(exclude_unset=True) if hasattr(prop_update, "model_dump") else prop_update.dict(exclude_unset=True)

    # Check for duplicate property code if code is being updated
    if "code" in update_data and update_data["code"]:
        clean_code = update_data["code"].strip()
        update_data["code"] = clean_code
        if clean_code != (db_prop.code or ""):
            code_check = db.scalar(
                select(models.Property).where(
                    models.Property.organization_id == organization_id,
                    models.Property.code.ilike(clean_code),
                    models.Property.id != db_prop.id
                )
            )
            if code_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Property code '{clean_code}' is already in use."
                )

    for field, value in update_data.items():
        if hasattr(db_prop, field):
            setattr(db_prop, field, value)

    db.commit()
    db.refresh(db_prop)
    return db_prop


# 5. DELETE /api/properties/{property_id} - Delete property record
@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(
    property_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(property_id)
        stmt = select(models.Property).where(
            models.Property.id == parsed_uuid,
            models.Property.organization_id == organization_id
        )
    except ValueError:
        if hasattr(models.Property, "code"):
            stmt = select(models.Property).where(
                models.Property.code.ilike(property_id.strip()),
                models.Property.organization_id == organization_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid property identifier format."
            )

    db_prop = db.scalar(stmt)
    if not db_prop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found."
        )

    db.delete(db_prop)
    db.commit()
    return None