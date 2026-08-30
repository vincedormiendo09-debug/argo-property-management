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


def ensure_sandbox_organization(db: Session, org_id: uuid.UUID):
    """Ensures the Organization exists in DB to satisfy FK constraints."""
    org = db.scalar(select(models.Organization).where(models.Organization.id == org_id))
    if not org:
        sandbox_org = models.Organization(id=org_id, name="ARGO Property Management Corp.")
        db.add(sandbox_org)
        db.commit()


def find_owner_by_identifier(db: Session, owner_id: str, organization_id: uuid.UUID):
    """Robustly locates an owner by UUID, user_id, custom own_id, or email."""
    clean_id = owner_id.strip()

    # 1. Search Owner table by UUID (id or user_id)
    try:
        parsed_uuid = uuid.UUID(clean_id)
        owner = db.scalar(
            select(models.Owner).where(
                or_(
                    models.Owner.id == parsed_uuid,
                    models.Owner.user_id == parsed_uuid
                ),
                or_(
                    models.Owner.organization_id == organization_id,
                    models.Owner.organization_id.is_(None)
                )
            )
        )
        if owner:
            return owner
    except ValueError:
        pass

    # 2. Search Owner table by own_id
    if hasattr(models.Owner, "own_id"):
        owner = db.scalar(
            select(models.Owner).where(
                models.Owner.own_id.ilike(clean_id),
                or_(
                    models.Owner.organization_id == organization_id,
                    models.Owner.organization_id.is_(None)
                )
            )
        )
        if owner:
            return owner

    # 3. Search Owner table by email
    owner = db.scalar(
        select(models.Owner).where(
            models.Owner.email.ilike(clean_id),
            or_(
                models.Owner.organization_id == organization_id,
                models.Owner.organization_id.is_(None)
            )
        )
    )
    if owner:
        return owner

    # 4. Fallback: Search User table directly and build dynamic Owner
    user = db.scalar(
        select(models.User).where(
            or_(
                models.User.email.ilike(clean_id),
                models.User.id == (uuid.UUID(clean_id) if len(clean_id) == 36 else None)
            )
        )
    )
    if user:
        name_parts = (user.name or user.full_name or "Registered Owner").strip().split(maxsplit=1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        virtual_owner = models.Owner(
            id=user.id,
            organization_id=organization_id,
            name=user.name or user.full_name or "Registered Owner",
            email=user.email,
            phone=user.phone or "",
            status="Active"
        )
        if hasattr(virtual_owner, "user_id"):
            virtual_owner.user_id = user.id
        if hasattr(virtual_owner, "full_name"):
            virtual_owner.full_name = user.name or user.full_name or "Registered Owner"
        if hasattr(virtual_owner, "first_name"):
            virtual_owner.first_name = first_name
        if hasattr(virtual_owner, "last_name"):
            virtual_owner.last_name = last_name
        if hasattr(virtual_owner, "own_id"):
            virtual_owner.own_id = f"OWN-{str(user.id)[:6].upper()}"
        if hasattr(virtual_owner, "type"):
            virtual_owner.type = "Individual"
        return virtual_owner

    return None


# ---------------------------------------------------------------------
# FRACTIONAL EQUITY OWNERSHIP ENDPOINTS
# ---------------------------------------------------------------------
@router.get("/shares/all", response_model=List[schemas.PropertyOwnershipSchema])
def read_property_ownerships(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    property_id: Optional[uuid.UUID] = Query(default=None),
    owner_id: Optional[uuid.UUID] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    stmt = select(models.PropertyOwnership).where(
        or_(
            models.PropertyOwnership.organization_id == organization_id,
            models.PropertyOwnership.organization_id.is_(None)
        )
    )
    if property_id:
        stmt = stmt.where(models.PropertyOwnership.property_id == property_id)
    if owner_id:
        stmt = stmt.where(models.PropertyOwnership.owner_id == owner_id)

    return list(db.scalars(stmt).all())


@router.post("/shares/assign", response_model=schemas.PropertyOwnershipSchema, status_code=status.HTTP_201_CREATED)
def assign_property_ownership(
    share_in: schemas.PropertyOwnershipCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(share_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    share_data = share_in.model_dump(exclude_unset=True) if hasattr(share_in, "model_dump") else share_in.dict(exclude_unset=True)
    if "id" not in share_data or not share_data["id"]:
        share_data["id"] = uuid.uuid4()
    share_data["organization_id"] = org_id

    db_share = models.PropertyOwnership(**share_data)
    db.add(db_share)
    db.commit()
    db.refresh(db_share)
    return db_share


# ---------------------------------------------------------------------
# OWNERS ENDPOINTS (DIRECT DATABASE + LIVE USER MERGING)
# ---------------------------------------------------------------------
@router.get("/")
def read_owners(
    organization_id: Optional[uuid.UUID] = Query(default=DEFAULT_ORG_ID),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    """
    Returns explicit Owner records merged with registered Users.
    Uses safe dictionary response to prevent Pydantic 500 validation crashes.
    """
    org_id = organization_id or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    results: List[Dict[str, Any]] = []
    seen_identifiers = set()

    # 1. Fetch explicit owner table records
    try:
        db_owners = list(db.scalars(
            select(models.Owner).where(
                or_(
                    models.Owner.organization_id == org_id,
                    models.Owner.organization_id.is_(None)
                )
            )
        ).all())

        for o in db_owners:
            o_id = str(getattr(o, "id", "") or "")
            o_user_id = str(getattr(o, "user_id", "") or "")
            o_email = (getattr(o, "email", "") or "").lower().strip()
            o_name = getattr(o, "name", "") or getattr(o, "full_name", "") or "Property Owner"

            if o_id:
                seen_identifiers.add(o_id)
            if o_user_id:
                seen_identifiers.add(o_user_id)
            if o_email:
                seen_identifiers.add(o_email)

            results.append({
                "id": o_id,
                "user_id": o_user_id or o_id,
                "own_id": getattr(o, "own_id", "") or f"OWN-{o_id[:6].upper()}",
                "name": o_name,
                "full_name": o_name,
                "email": getattr(o, "email", "") or "",
                "phone": getattr(o, "phone", "") or "",
                "type": getattr(o, "type", "Individual") or "Individual",
                "status": getattr(o, "status", "Active") or "Active"
            })
    except Exception as e:
        logger.warning(f"Notice querying owners table: {e}")

    # 2. Fetch all registered users with owner/investor/landlord roles
    try:
        owner_users = list(db.scalars(
            select(models.User).where(
                or_(
                    models.User.role.ilike("%owner%"),
                    models.User.role.ilike("%investor%"),
                    models.User.role.ilike("%property_owner%"),
                    models.User.role.ilike("%landlord%")
                )
            )
        ).all())

        for u in owner_users:
            u_id = str(getattr(u, "id", "") or "")
            u_email = (getattr(u, "email", "") or "").lower().strip()
            u_name = getattr(u, "name", "") or getattr(u, "full_name", "") or "Registered Owner"

            if u_id not in seen_identifiers and u_email not in seen_identifiers:
                if u_id:
                    seen_identifiers.add(u_id)
                if u_email:
                    seen_identifiers.add(u_email)

                results.append({
                    "id": u_id,
                    "user_id": u_id,
                    "own_id": f"OWN-{u_id[:6].upper()}",
                    "name": u_name,
                    "full_name": u_name,
                    "email": getattr(u, "email", "") or "",
                    "phone": getattr(u, "phone", "") or "",
                    "type": "Individual",
                    "status": "Active"
                })
    except Exception as e:
        logger.warning(f"Notice querying users table: {e}")

    # 3. Apply optional filters
    if status_filter:
        s_filt = status_filter.strip().lower()
        results = [r for r in results if s_filt in (r.get("status") or "").lower()]

    if search:
        s_term = search.strip().lower()
        results = [
            r for r in results
            if s_term in (r.get("name") or "").lower()
            or s_term in (r.get("full_name") or "").lower()
            or s_term in (r.get("email") or "").lower()
            or s_term in (r.get("phone") or "").lower()
            or s_term in (r.get("own_id") or "").lower()
        ]

    return results


@router.post("/", response_model=schemas.OwnerSchema, status_code=status.HTTP_201_CREATED)
def create_owner(owner_in: schemas.OwnerCreate, db: Session = Depends(get_db)):
    org_id = getattr(owner_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    clean_email = owner_in.email.lower().strip() if owner_in.email else None
    own_id = getattr(owner_in, "own_id", None) or f"OWN-{datetime.now().year}-{str(uuid.uuid4())[:4].upper()}"

    duplicate_filters = []
    if own_id and hasattr(models.Owner, "own_id"):
        duplicate_filters.append(models.Owner.own_id.ilike(own_id))
    if clean_email and hasattr(models.Owner, "email"):
        duplicate_filters.append(models.Owner.email.ilike(clean_email))

    if duplicate_filters:
        existing = db.scalar(
            select(models.Owner).where(
                models.Owner.organization_id == org_id,
                or_(*duplicate_filters)
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An owner with this ID or email already exists in this organization."
            )

    owner_data = owner_in.model_dump(exclude_unset=True) if hasattr(owner_in, "model_dump") else owner_in.dict(exclude_unset=True)
    if "id" not in owner_data or not owner_data["id"]:
        owner_data["id"] = uuid.uuid4()
    owner_data["organization_id"] = org_id
    if clean_email:
        owner_data["email"] = clean_email
    if "own_id" not in owner_data and hasattr(models.Owner, "own_id"):
        owner_data["own_id"] = own_id
    if "status" not in owner_data or not owner_data["status"]:
        owner_data["status"] = "Active"

    db_owner = models.Owner(**owner_data)
    db.add(db_owner)
    db.commit()
    db.refresh(db_owner)
    return db_owner


@router.get("/{owner_id}", response_model=schemas.OwnerSchema)
def get_owner(
    owner_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    owner = find_owner_by_identifier(db, owner_id, organization_id)
    if not owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner not found."
        )
    return owner


@router.put("/{owner_id}", response_model=schemas.OwnerSchema)
@router.patch("/{owner_id}", response_model=schemas.OwnerSchema)
def update_owner(
    owner_id: str,
    owner_update: schemas.OwnerUpdate,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_owner = find_owner_by_identifier(db, owner_id, organization_id)
    if not db_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner not found."
        )

    update_data = owner_update.model_dump(exclude_unset=True) if hasattr(owner_update, "model_dump") else owner_update.dict(exclude_unset=True)

    if "email" in update_data and update_data["email"]:
        clean_email = update_data["email"].lower().strip()
        update_data["email"] = clean_email
        if clean_email != (getattr(db_owner, "email", "") or "").lower().strip():
            email_check = db.scalar(
                select(models.Owner).where(
                    models.Owner.organization_id == organization_id,
                    models.Owner.email.ilike(clean_email),
                    models.Owner.id != db_owner.id
                )
            )
            if email_check:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Email '{clean_email}' is already assigned to another owner."
                )

    for field, value in update_data.items():
        if hasattr(db_owner, field):
            setattr(db_owner, field, value)

    db.commit()
    db.refresh(db_owner)
    return db_owner


@router.delete("/{owner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_owner(
    owner_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    db_owner = find_owner_by_identifier(db, owner_id, organization_id)
    if not db_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner not found."
        )

    try:
        db.delete(db_owner)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete owner because they hold active property ownership shares."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting owner: {str(e)}"
        )

    return None