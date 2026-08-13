import uuid
from datetime import date
from app.database import SessionLocal
from app import models

def seed_database():
    db = SessionLocal()
    try:
        # Sandbox Org UUID matching schema.sql
        org_id = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
        
        # 1. Ensure Sandbox Organization
        org = db.query(models.Organization).filter_by(id=org_id).first()
        if not org:
            org = models.Organization(id=org_id, name="Sunrise Property Group")
            db.add(org)
            db.commit()

        # 2. Add Property
        prop = db.query(models.Property).filter_by(organization_id=org_id, code="PROP-001").first()
        if not prop:
            prop = models.Property(
                id=uuid.uuid4(),
                organization_id=org_id,
                code="PROP-001",
                name="Sunrise Residences",
                type="Residential",
                location="Parañaque, Metro Manila",
                units_count=2,
                status="Active"
            )
            db.add(prop)
            db.commit()

        # 3. Add Building
        bldg = db.query(models.Building).filter_by(organization_id=org_id, code="BLDG-A").first()
        if not bldg:
            bldg = models.Building(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                code="BLDG-A",
                name="Tower A",
                floors=10,
                total_units=50,
                status="ACTIVE"
            )
            db.add(bldg)
            db.commit()

        # 4. Add Units (Added required 'floor' column)
        unit1 = db.query(models.Unit).filter_by(organization_id=org_id, unit_no="Unit 101").first()
        if not unit1:
            unit1 = models.Unit(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                building_id=bldg.id,
                unit_no="Unit 101",
                type="1BR",
                floor="1st Floor",
                rent=15000.0,
                status="OCCUPIED",
                subtitle="Sunrise Residences • Tower A • Unit 101"
            )
            db.add(unit1)

        unit2 = db.query(models.Unit).filter_by(organization_id=org_id, unit_no="Unit 204").first()
        if not unit2:
            unit2 = models.Unit(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                building_id=bldg.id,
                unit_no="Unit 204",
                type="2BR",
                floor="2nd Floor",
                rent=22000.0,
                status="VACANT",
                subtitle="Sunrise Residences • Tower A • Unit 204"
            )
            db.add(unit2)
        db.commit()

        # 5. Add Tenant (Added required 'tnt_id' column)
        tenant = db.query(models.Tenant).filter_by(organization_id=org_id, tnt_id="TNT-1001").first()
        if not tenant:
            tenant = models.Tenant(
                id=uuid.uuid4(),
                organization_id=org_id,
                tnt_id="TNT-1001",
                name="Maria Santos",
                email="maria.santos@tenant.ph",
                phone="09171234567",
                type="Individual",
                status="Active"
            )
            db.add(tenant)
            db.commit()

        # 6. Add Owner (Don Ramon Santos)
        owner = db.query(models.Owner).filter_by(organization_id=org_id, own_id="OWN-2001").first()
        if not owner:
            owner = models.Owner(
                id=uuid.uuid4(),
                organization_id=org_id,
                own_id="OWN-2001",
                name="Don Ramon Santos",
                email="ramon.santos@owner.ph",
                phone="09183334444",
                type="INDIVIDUAL",
                status="ACTIVE"
            )
            db.add(owner)
            db.commit()

            # Assign 100% Ownership
            ownership = models.PropertyOwnership(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                owner_id=owner.id,
                share_percent=100.00,
                role="Primary"
            )
            db.add(ownership)
            db.commit()

        # 7. Add Lease (Maria Santos in Unit 101)
        lease = db.query(models.Lease).filter_by(organization_id=org_id, lease_id="LSE-2026-001").first()
        if not lease:
            lease = models.Lease(
                id=uuid.uuid4(),
                organization_id=org_id,
                lease_id="LSE-2026-001",
                tenant_id=tenant.id,
                unit_id=unit1.id,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
                rent=15000.0,
                deposit=30000.0,
                status="ACTIVE"
            )
            db.add(lease)
            db.commit()

            # 8. Add Base Rent Invoice for Client Billing
            invoice = models.Invoice(
                id=uuid.uuid4(),
                organization_id=org_id,
                invoice_id="INV-2026-08",
                lease_id=lease.id,
                type="Monthly Base Rent — August 2026",
                sub="Sunrise Residences • Tower A • Unit 101",
                category_type="Rent",
                due_date=date(2026, 8, 15),
                amount=15000.0,
                status="Unpaid",
                channel="Pending Payment"
            )
            db.add(invoice)
            db.commit()

        # 9. Add Maintenance Ticket
        ticket = db.query(models.MaintenanceTicket).filter_by(organization_id=org_id, ticket_id="TCK-2026-001").first()
        if not ticket:
            ticket = models.MaintenanceTicket(
                id=uuid.uuid4(),
                organization_id=org_id,
                ticket_id="TCK-2026-001",
                unit_id=unit1.id,
                tenant_name="Maria Santos",
                category="HVAC / Aircon",
                title="AC Unit Leaking Water",
                description="Master bedroom AC unit is dripping water onto floor.",
                priority="High",
                status="Open",
                technician="Unassigned"
            )
            db.add(ticket)
            db.commit()

        print("✅ Database successfully seeded with contract-compliant test data!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()