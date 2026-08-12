import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from .database import engine, Base
from . import models
from .routers import units, properties, tenants, leases, invoices, maintenance

# Disabled: Alembic manages PostgreSQL schema migrations directly
# models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ARGO Property Management API",
    description="Multi-Tenant Property Operations Backend Gateway",
    version="0.5.0"
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. MOUNT API ROUTERS
# ==========================================
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(units.router, prefix="/api/units", tags=["Units"])
app.include_router(tenants.router, prefix="/api/tenants", tags=["Tenants"])
app.include_router(leases.router, prefix="/api/leases", tags=["Leases"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["Invoices & Rent Collection"])
app.include_router(maintenance.router, prefix="/api/maintenance", tags=["Maintenance Work Orders"])


# ==========================================
# 2. MOUNT FRONTEND STATIC DIRECTORY
# ==========================================
# Automatically search candidate locations for the 'frontend' directory
current_dir = os.path.dirname(os.path.abspath(__file__))
candidate_paths = [
    os.path.abspath(os.path.join(current_dir, "../../frontend")),  # Root /frontend
    os.path.abspath(os.path.join(current_dir, "../frontend")),     # /backend/frontend
    os.path.abspath(os.path.join(current_dir, "../../../frontend"))
]

frontend_path = None
for path in candidate_paths:
    if os.path.exists(path):
        frontend_path = path
        break

if frontend_path:
    print(f"✅ [StaticFiles] Successfully mounted frontend directory: {frontend_path}")
    app.mount("/app", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    print("⚠️ [StaticFiles] WARNING: Could not find 'frontend' directory in candidate paths.")


# ==========================================
# 3. ROOT REDIRECT
# ==========================================
@app.get("/")
def read_root():
    """Auto-redirect root traffic straight to Auth Gateway & Role Router."""
    return RedirectResponse(url="/app/index.html")