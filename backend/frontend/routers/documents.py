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


@router.get("/", response_model=List[schemas.DocumentSchema])
def read_documents(
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    pov: Optional[str] = Query(default=None),
    type_filter: Optional[str] = Query(default=None, alias="type"),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    ensure_sandbox_organization(db, organization_id)
    stmt = select(models.Document).where(models.Document.organization_id == organization_id)

    # Role-scoped filtering (pov: admin, owner, client) at the database query level
    normalized_pov = "all"
    if pov and pov.lower() != "all":
        raw_pov = pov.lower().strip()
        normalized_pov = raw_pov
        if raw_pov in ("tenant", "client_pov"):
            normalized_pov = "client"
        elif raw_pov in ("property_owner", "investor"):
            normalized_pov = "owner"
        elif raw_pov in ("pm", "property_manager"):
            normalized_pov = "admin"

        if normalized_pov == "client":
            # Clients / tenants see lease contracts and tenant-specific records
            stmt = stmt.where(or_(
                models.Document.type.ilike("%lease%"),
                models.Document.type.ilike("%contract%"),
                models.Document.entity_name.ilike("%santos%")
            ))
        elif normalized_pov == "owner":
            # Owners see title deeds, tax declarations, and equity statements
            stmt = stmt.where(or_(
                models.Document.type.ilike("%title%"),
                models.Document.type.ilike("%tax%"),
                models.Document.type.ilike("%statement%"),
                models.Document.entity_name.ilike("%residences%")
            ))
        # Admin sees all documents without restriction

    if type_filter:
        stmt = stmt.where(models.Document.type.ilike(f"%{type_filter}%"))
    if search:
        search_terms = [
            models.Document.title.ilike(f"%{search}%"),
            models.Document.doc_id.ilike(f"%{search}%"),
            models.Document.entity_name.ilike(f"%{search}%"),
            models.Document.type.ilike(f"%{search}%")
        ]
        stmt = stmt.where(or_(*search_terms))

    documents = list(db.scalars(stmt).all())

    # Fallback seed if DB is empty
    if not documents and not search and not type_filter:
        default_docs = [
            models.Document(
                id=uuid.uuid4(),
                organization_id=organization_id,
                doc_id="DOC-1001",
                title="Sunrise Residences Title Deed (TCT #49281)",
                file_type="PDF • 4.2 MB",
                entity_name="Sunrise Residences",
                entity_sub="PROP-001 • Primary Deed",
                type="Title",
                uploader="Property Admin",
                date=date(2024, 1, 15),
                status="Active"
            ),
            models.Document(
                id=uuid.uuid4(),
                organization_id=organization_id,
                doc_id="DOC-1002",
                title="Signed Residential Lease Agreement",
                file_type="PDF • 2.4 MB",
                entity_name="Maria Santos",
                entity_sub="Sunrise Residences • Unit 101",
                type="Lease Contract",
                uploader="Juan Dela Cruz",
                date=date(2026, 1, 1),
                status="Active"
            )
        ]
        db.add_all(default_docs)
        db.commit()
        
        # Re-run query with role filter applied
        stmt = select(models.Document).where(models.Document.organization_id == organization_id)
        if pov and pov.lower() != "all":
            if normalized_pov == "client":
                stmt = stmt.where(or_(
                    models.Document.type.ilike("%lease%"),
                    models.Document.type.ilike("%contract%"),
                    models.Document.entity_name.ilike("%santos%")
                ))
            elif normalized_pov == "owner":
                stmt = stmt.where(or_(
                    models.Document.type.ilike("%title%"),
                    models.Document.type.ilike("%tax%"),
                    models.Document.type.ilike("%statement%"),
                    models.Document.entity_name.ilike("%residences%")
                ))
        if type_filter:
            stmt = stmt.where(models.Document.type.ilike(f"%{type_filter}%"))
        if search:
            stmt = stmt.where(or_(*search_terms))
        documents = list(db.scalars(stmt).all())

    return documents


@router.post("/", response_model=schemas.DocumentSchema, status_code=status.HTTP_201_CREATED)
def create_document(
    doc_in: schemas.DocumentCreate,
    db: Session = Depends(get_db)
):
    org_id = getattr(doc_in, "organization_id", DEFAULT_ORG_ID) or DEFAULT_ORG_ID
    ensure_sandbox_organization(db, org_id)

    doc_data = doc_in.model_dump(exclude_unset=True) if hasattr(doc_in, "model_dump") else doc_in.dict(exclude_unset=True)
    
    if "id" not in doc_data or not doc_data["id"]:
        doc_data["id"] = uuid.uuid4()
    doc_data["organization_id"] = org_id
    if "doc_id" not in doc_data or not doc_data["doc_id"]:
        doc_data["doc_id"] = f"DOC-{str(uuid.uuid4())[:4].upper()}"

    db_doc = models.Document(**doc_data)
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc


@router.get("/{doc_id}", response_model=schemas.DocumentSchema)
def get_document(
    doc_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(doc_id)
        stmt = select(models.Document).where(
            models.Document.id == parsed_uuid,
            models.Document.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Document).where(
            models.Document.doc_id == doc_id,
            models.Document.organization_id == organization_id
        )

    doc = db.scalar(stmt)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: str,
    organization_id: uuid.UUID = Query(default=DEFAULT_ORG_ID),
    db: Session = Depends(get_db)
):
    try:
        parsed_uuid = uuid.UUID(doc_id)
        stmt = select(models.Document).where(
            models.Document.id == parsed_uuid,
            models.Document.organization_id == organization_id
        )
    except ValueError:
        stmt = select(models.Document).where(
            models.Document.doc_id == doc_id,
            models.Document.organization_id == organization_id
        )

    db_doc = db.scalar(stmt)
    if not db_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    db.delete(db_doc)
    db.commit()
    return None