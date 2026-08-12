import uuid
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app import models

def seed_database():
    db = SessionLocal()
    try:
        org_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        
        # 1. Ensure Sandbox Organization
        org = db.query(models.Organization).filter_by(id=org_id).first()
        if not org:
            org = models.Organization(id=org_id, name="Sunrise Property Group")
            db.add(org)
            db.commit()

        # 2. Add Property
        prop = db.query(models.Property).filter_by(organization_id=org_id).first()
        if not prop:
            prop = models.Property(
                id=uuid.uuid4(),
                organization_id=org_id,
                code="PROP-001",
                name="Sunrise Residences",
                type="Residential",
                location="Parañaque, Metro Manila",
                status="Active"
            )
            db.add(prop)
            db.commit()

        # 3. Add Units
        unit1 = db.query(models.Unit).filter_by(organization_id=org_id, unit_no="Unit 101").first()
        if not unit1:
            unit1 = models.Unit(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                unit_no="Unit 101",
                type="1BR",
                rent=15000.0,
                status="OCCUPIED"
            )
            db.add(unit1)
            db.commit()

        # 4. Add Tenant
        tenant = db.query(models.Tenant).filter_by(organization_id=org_id).first()
        if not tenant:
            tenant = models.Tenant(
                id=uuid.uuid4(),
                organization_id=org_id,
                name="Maria Santos",
                email="maria.santos@tenant.ph",
                phone="09171234567",
                status="Active"
            )
            db.add(tenant)
            db.commit()

        print("✅ Database successfully seeded with mock data!")

    finally:
        db.close()

if __name__ == "__main__":
    seed_database()