import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import engine, Base, get_db
from . import models
from .routers import units, properties, tenants, leases, invoices, maintenance

# Dynamic imports for optional/supplementary modules
try:
    from .routers import buildings
except ImportError:
    buildings = None

try:
    from .routers import auth
except ImportError:
    auth = None

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

try:
    from .routers import users
except ImportError:
    users = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application Lifespan Context Manager:
    Verifies live database connectivity on startup and cleanly disposes the pool on shutdown.
    """
    # 1. Test live PostgreSQL connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ [Database] Live PostgreSQL connection established successfully.")
    except Exception as db_err:
        print(f"⚠️ [Database] Connection warning on startup: {db_err}")

    # 2. Auto-create tables if AUTO_CREATE_TABLES=true
    if os.getenv("AUTO_CREATE_TABLES", "false").lower() in ("true", "1", "t"):
        try:
            Base.metadata.create_all(bind=engine)
            print("✅ [Database] Schema tables validated / created.")
        except Exception as schema_err:
            print(f"⚠️ [Database] Schema creation warning: {schema_err}")

    yield

    # Teardown logic
    engine.dispose()
    print("🔌 [Database] PostgreSQL connection pool disposed cleanly.")


app = FastAPI(
    title="ARGO Property Management API",
    description="Multi-Tenant Property Operations Backend Gateway",
    version="0.5.0",
    lifespan=lifespan,
    redirect_slashes=False  # Prevents 307 redirect errors on missing trailing slashes
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
# 1. MOUNT CORE API ROUTERS
# ==========================================
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(units.router, prefix="/api/units", tags=["Units"])
app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])
app.include_router(leases.router, prefix="/api/leases", tags=["Leases"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices & Rent Collection"])
app.include_router(maintenance.router, prefix="/api/maintenance", tags=["Maintenance Work Orders"])

# Mount supplementary routers if present
if buildings and hasattr(buildings, "router"):
    app.include_router(buildings.router, prefix="/api/buildings", tags=["Buildings"])

if auth and hasattr(auth, "router"):
    app.include_router(auth.router, prefix="/api/auth", tags=["Authentication & Access"])

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

if users and hasattr(users, "router"):
    app.include_router(users.router, prefix="/api/users", tags=["Users & Profiles"])


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


current_dir = os.path.dirname(os.path.abspath(__file__))
candidate_paths = [
    os.path.abspath(os.path.join(current_dir, "../../frontend")),  # Root /frontend
    os.path.abspath(os.path.join(current_dir, "../frontend")),    # /backend/frontend
    os.path.abspath(os.path.join(current_dir, "frontend")),        # ./frontend
    os.path.abspath(os.path.join(current_dir, "..")),              # Repo root (where HTML files live)
    os.path.abspath(os.path.join(current_dir, "static")),
    os.path.abspath(os.path.join(current_dir, "../static")),
    current_dir                                                   # ./
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


# ==========================================
# 4. ROOT REDIRECT
# ==========================================
@app.get("/")
def read_root():
    """Auto-redirect root traffic straight to login/dashboard."""
    return RedirectResponse(url="/index.html")