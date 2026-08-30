import os
import uuid
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status, Query, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import text, select, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .database import engine, Base, get_db
from . import models, schemas

# Core Routers
from .routers import (
    units, 
    properties, 
    tenants, 
    leases, 
    invoices, 
    maintenance, 
    auth, 
    users
)

# Optional / Supplementary Routers
try:
    from .routers import utilities
except ImportError:
    utilities = None

try:
    from .routers import buildings
except ImportError:
    buildings = None

try:
    from .routers import owners
except ImportError:
    owners = None

try:
    from .routers import transactions
except ImportError:
    transactions = None

try:
    from .routers import notifications
except ImportError:
    notifications = None

try:
    from .routers import meter_readings
except ImportError:
    meter_readings = None

try:
    from .routers import inspections
except ImportError:
    inspections = None

try:
    from .routers import documents
except ImportError:
    documents = None


DEFAULT_ORG_ID = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


def parse_uuid_safely(val: Optional[str]) -> Optional[uuid.UUID]:
    if not val or str(val).strip().lower() in ("undefined", "null", ""):
        return None
    try:
        return uuid.UUID(str(val).strip())
    except Exception:
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verifies live database connectivity on startup and cleanly disposes the pool on shutdown."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ [Database] Live PostgreSQL connection established successfully.")
    except Exception as db_err:
        print(f"⚠️ [Database] Connection warning on startup: {db_err}")

    if os.getenv("AUTO_CREATE_TABLES", "false").lower() in ("true", "1", "t"):
        try:
            Base.metadata.create_all(bind=engine)
            print("✅ [Database] Schema tables validated / created.")
        except Exception as schema_err:
            print(f"⚠️ [Database] Schema creation warning: {schema_err}")

    yield

    engine.dispose()
    print("🔌 [Database] PostgreSQL connection pool disposed cleanly.")


app = FastAPI(
    title="ARGO Property Management API",
    description="Multi-Tenant Property Operations Backend Gateway",
    version="0.5.0",
    lifespan=lifespan
)

# ==========================================
# CORS MIDDLEWARE CONFIGURATION
# ==========================================
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "https://argo-management-2026.onrender.com"
]

env_origins = os.getenv("ALLOWED_ORIGINS")
if env_origins:
    origins.extend([o.strip() for o in env_origins.split(",")])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.github\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. MOUNT CORE & AUTH API ROUTERS
# ==========================================
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication & Access"])
app.include_router(users.router, prefix="/api/users", tags=["Users & Profiles"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(units.router, prefix="/api/units", tags=["Units"])
app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])
app.include_router(leases.router, prefix="/api/leases", tags=["Leases"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices & Rent Collection"])
app.include_router(maintenance.router, prefix="/api/maintenance", tags=["Maintenance Work Orders"])

# Utilities (Mounted to both /api/utilities and /api/utility-charges for full backward compatibility)
if utilities and hasattr(utilities, "router"):
    app.include_router(utilities.router, prefix="/api/utilities", tags=["Utilities & Sub-Meters"])
    app.include_router(utilities.router, prefix="/api/utility-charges", tags=["Utility Charges"])

if buildings and hasattr(buildings, "router"):
    app.include_router(buildings.router, prefix="/api/buildings", tags=["Buildings"])

if owners and hasattr(owners, "router"):
    app.include_router(owners.router, prefix="/api/owners", tags=["Property Owners"])

if transactions and hasattr(transactions, "router"):
    app.include_router(transactions.router, prefix="/api/transactions", tags=["Transactions & Ledger"])

if notifications and hasattr(notifications, "router"):
    app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications Center"])

if meter_readings and hasattr(meter_readings, "router"):
    app.include_router(meter_readings.router, prefix="/api/meter-readings", tags=["Meter Readings & Sub-Meters"])

if inspections and hasattr(inspections, "router"):
    app.include_router(inspections.router, prefix="/api/inspections", tags=["Inspections & Checklists"])

if documents and hasattr(documents, "router"):
    app.include_router(documents.router, prefix="/api/documents", tags=["Document Vault"])


# ==========================================
# 2. DEDICATED PROPERTY OWNERSHIP ROUTER
# ==========================================
ownership_router = APIRouter()


@ownership_router.get("")
@ownership_router.get("/")
def get_property_ownerships(
    organization_id: Optional[str] = Query(default=None),
    property_id: Optional[str] = Query(default=None),
    owner_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_uuid = parse_uuid_safely(organization_id) or DEFAULT_ORG_ID
    prop_uuid = parse_uuid_safely(property_id)
    own_uuid = parse_uuid_safely(owner_id)

    stmt = select(models.PropertyOwnership).where(
        or_(
            models.PropertyOwnership.organization_id == org_uuid,
            models.PropertyOwnership.organization_id.is_(None)
        )
    )
    if prop_uuid:
        stmt = stmt.where(models.PropertyOwnership.property_id == prop_uuid)
    if own_uuid:
        stmt = stmt.where(models.PropertyOwnership.owner_id == own_uuid)

    shares = list(db.scalars(stmt).all())
    results = []

    # Cache properties and owners for lookup
    props_map = {
        p.id: (getattr(p, "name", None) or getattr(p, "property_name", None) or "Property") 
        for p in db.scalars(select(models.Property)).all()
    }
    owners_map = {
        o.id: (getattr(o, "name", None) or getattr(o, "full_name", None) or "Owner") 
        for o in db.scalars(select(models.Owner)).all()
    }
    for u in db.scalars(select(models.User)).all():
        if u.id not in owners_map:
            owners_map[u.id] = getattr(u, "name", None) or getattr(u, "full_name", None) or "Registered Owner"

    for s in shares:
        s_id = str(s.id)
        p_id = s.property_id
        o_id = s.owner_id
        results.append({
            "id": s_id,
            "organization_id": str(s.organization_id or org_uuid),
            "property_id": str(p_id),
            "property_name": props_map.get(p_id, "Property Asset"),
            "owner_id": str(o_id),
            "owner_name": owners_map.get(o_id, "Property Owner"),
            "owner_type": "Individual",
            "share_percent": float(s.share_percent or 100.0),
            "role": s.role or "Primary Managing Owner",
            "is_primary": "primary" in (s.role or "").lower()
        })

    return results


@ownership_router.post("", status_code=status.HTTP_201_CREATED)
@ownership_router.post("/", status_code=status.HTTP_201_CREATED)
def assign_property_ownership_endpoint(
    share_payload: Dict[str, Any],
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    org_id = parse_uuid_safely(share_payload.get("organization_id") or organization_id) or DEFAULT_ORG_ID
    prop_id = parse_uuid_safely(share_payload.get("property_id"))
    own_id = parse_uuid_safely(share_payload.get("owner_id"))

    if not prop_id or not own_id:
        raise HTTPException(status_code=400, detail="Valid property_id and owner_id are required.")

    share_record = models.PropertyOwnership(
        id=uuid.uuid4(),
        organization_id=org_id,
        property_id=prop_id,
        owner_id=own_id,
        share_percent=float(share_payload.get("share_percent", 100.0)),
        role=share_payload.get("role", "Primary Managing Owner")
    )
    db.add(share_record)
    db.commit()
    db.refresh(share_record)
    return {
        "id": str(share_record.id),
        "property_id": str(share_record.property_id),
        "owner_id": str(share_record.owner_id),
        "share_percent": float(share_record.share_percent),
        "role": share_record.role
    }


@ownership_router.delete("/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
@ownership_router.delete("/{share_id}/", status_code=status.HTTP_204_NO_CONTENT)
def delete_property_ownership_endpoint(
    share_id: str,
    organization_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    share_uuid = parse_uuid_safely(share_id)
    if not share_uuid:
        raise HTTPException(status_code=400, detail="Invalid share ID.")

    share = db.scalar(select(models.PropertyOwnership).where(models.PropertyOwnership.id == share_uuid))
    if not share:
        raise HTTPException(status_code=404, detail="Ownership share not found.")

    db.delete(share)
    db.commit()
    return None

app.include_router(ownership_router, prefix="/api/property-ownership", tags=["Property Ownership"])


# ==========================================
# 3. SYSTEM HEALTH & DIAGNOSTIC ENDPOINTS
# ==========================================
@app.get("/api/health", tags=["System Health"])
@app.get("/health", tags=["System Health"])
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "online",
            "database": "connected",
            "service": "ARGO Property Management API",
            "version": "0.5.0"
        }
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "database": "disconnected",
                "error": str(e)
            }
        )


# ==========================================
# 4. STATIC FILES MOUNT
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
candidate_paths = [
    os.path.abspath(os.path.join(current_dir, "../../frontend")),
    os.path.abspath(os.path.join(current_dir, "../frontend")),
    os.path.abspath(os.path.join(current_dir, "frontend")),
    os.path.abspath(os.path.join(current_dir, "..")),
    os.path.abspath(os.path.join(current_dir, "static")),
    os.path.abspath(os.path.join(current_dir, "../static")),
    current_dir
]

frontend_path = None
for path in candidate_paths:
    if os.path.exists(os.path.join(path, "dashboard.html")) or os.path.exists(os.path.join(path, "index.html")):
        frontend_path = path
        break

if frontend_path:
    print(f"✅ [StaticFiles] Successfully mounted frontend directory: {frontend_path}")
    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend_app")
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend_root")
else:
    print("⚠️ [StaticFiles] WARNING: Could not find HTML files in candidate paths.")