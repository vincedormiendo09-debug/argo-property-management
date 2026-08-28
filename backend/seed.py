import uuid
from datetime import date, datetime
from app.database import SessionLocal
from app import models


def seed_database():
    db = SessionLocal()
    print("🔄 Synchronizing and seeding canonical database records...")
    try:
        # Standard Sandbox Organization UUID matching schema.sql
        org_id = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

        # 0. Clean old/conflicting records for this sandbox org to eliminate duplicate disparate data
        print("🧹 Cleaning stale test records...")
        if hasattr(models, "Notification"):
            db.query(models.Notification).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Document"):
            db.query(models.Document).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Inspection"):
            db.query(models.Inspection).filter_by(organization_id=org_id).delete()
        if hasattr(models, "MeterReading"):
            db.query(models.MeterReading).filter_by(organization_id=org_id).delete()
        if hasattr(models, "UtilityCharge"):
            db.query(models.UtilityCharge).filter_by(organization_id=org_id).delete()
        if hasattr(models, "MaintenanceTicket"):
            db.query(models.MaintenanceTicket).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Transaction"):
            db.query(models.Transaction).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Invoice"):
            db.query(models.Invoice).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Lease"):
            db.query(models.Lease).filter_by(organization_id=org_id).delete()
        if hasattr(models, "PropertyOwnership"):
            db.query(models.PropertyOwnership).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Tenant"):
            db.query(models.Tenant).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Owner"):
            db.query(models.Owner).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Unit"):
            db.query(models.Unit).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Building"):
            db.query(models.Building).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Property"):
            db.query(models.Property).filter_by(organization_id=org_id).delete()
        if hasattr(models, "User"):
            db.query(models.User).filter_by(organization_id=org_id).delete()
        if hasattr(models, "Organization"):
            db.query(models.Organization).filter_by(id=org_id).delete()
        db.commit()

        # 1. Organization
        org = models.Organization(
            id=org_id, 
            name="Sunrise Property Group"
        )
        db.add(org)
        db.commit()

        # 2. Add Default User Accounts (Admin, Owner, Client)
        admin_user = models.User(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Juan Dela Cruz",
            full_name="Juan Dela Cruz",
            email="admin@argo.ph",
            phone="09170000000",
            role="admin",
            avatar="JD",
            is_active=True
        )
        owner_user = models.User(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Don Ramon Santos",
            full_name="Don Ramon Santos",
            email="ramon.santos@owner.ph",
            phone="09185549011",
            role="owner",
            avatar="RS",
            is_active=True
        )
        tenant_user = models.User(
            id=uuid.uuid4(),
            organization_id=org_id,
            name="Maria Santos",
            full_name="Maria Santos",
            email="maria.santos@tenant.ph",
            phone="09171234567",
            role="client",
            avatar="MS",
            is_active=True
        )
        db.add_all([admin_user, owner_user, tenant_user])
        db.commit()

        # 3. Add Master Property: Sunrise Residences (20 Units Capacity, TCT Land Title)
        prop = models.Property(
            id=uuid.uuid4(),
            organization_id=org_id,
            code="PROP-001",
            name="Sunrise Residences",
            tct_number="TCT #49281-MNL",
            type="Residential Multi-Family",
            location="123 Solar St., Parañaque, Metro Manila",
            units_count=20,
            status="Active"
        )
        db.add(prop)
        db.commit()

        # 4. Add Master Building: Tower A (5 Floors, 20 Units Capacity, Floor Distribution)
        bldg = models.Building(
            id=uuid.uuid4(),
            organization_id=org_id,
            property_id=prop.id,
            code="BLDG-001",
            name="Tower A",
            floors=5,
            total_units=20,
            floor_distribution={
                "First Floor": 4,
                "Second Floor": 4,
                "Third Floor": 4,
                "Fourth Floor": 4,
                "Fifth Floor": 4
            },
            status="ACTIVE"
        )
        db.add(bldg)
        db.commit()

        # 5. Add All 20 Inventory Units (5 Floors x 4 Units with sqm specifications)
        unit_configs = [
            # 1st Floor
            ("Unit 101", "1-Bedroom Apartment", "First Floor", 1, 45.5, 15000.00, "OCCUPIED", "45.5 sqm · 1 bedroom · Living Area"),
            ("Unit 102", "Studio Deluxe", "First Floor", 1, 32.0, 12500.00, "VACANT", "32.0 sqm · Studio type"),
            ("Unit 103", "1-Bedroom Apartment", "First Floor", 1, 45.5, 15000.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 104", "2-Bedroom Suite", "First Floor", 1, 60.0, 20000.00, "VACANT", "60.0 sqm · 2 bedrooms · Balcony"),
            # 2nd Floor
            ("Unit 201", "1-Bedroom Apartment", "Second Floor", 2, 45.5, 15500.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 202", "Studio Deluxe", "Second Floor", 2, 32.0, 13000.00, "VACANT", "32.0 sqm · Studio type"),
            ("Unit 203", "1-Bedroom Apartment", "Second Floor", 2, 45.5, 15500.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 204", "2-Bedroom Suite", "Second Floor", 2, 60.0, 20500.00, "VACANT", "60.0 sqm · 2 bedrooms · Balcony"),
            # 3rd Floor
            ("Unit 301", "1-Bedroom Apartment", "Third Floor", 3, 45.5, 16000.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 302", "Studio Deluxe", "Third Floor", 3, 32.0, 13500.00, "VACANT", "32.0 sqm · Studio type"),
            ("Unit 303", "1-Bedroom Apartment", "Third Floor", 3, 45.5, 16000.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 304", "2-Bedroom Suite", "Third Floor", 3, 60.0, 21000.00, "VACANT", "60.0 sqm · 2 bedrooms · Corner Unit"),
            # 4th Floor
            ("Unit 401", "1-Bedroom Apartment", "Fourth Floor", 4, 45.5, 16500.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 402", "Studio Deluxe", "Fourth Floor", 4, 32.0, 14000.00, "VACANT", "32.0 sqm · Studio type"),
            ("Unit 403", "1-Bedroom Apartment", "Fourth Floor", 4, 45.5, 16500.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 404", "2-Bedroom Suite", "Fourth Floor", 4, 60.0, 21500.00, "VACANT", "60.0 sqm · 2 bedrooms · High Floor"),
            # 5th Floor (Penthouse Level)
            ("Unit 501", "1-Bedroom Apartment", "Fifth Floor", 5, 45.5, 17000.00, "VACANT", "45.5 sqm · 1 bedroom · Skyline View"),
            ("Unit 502", "Studio Deluxe", "Fifth Floor", 5, 32.0, 14500.00, "VACANT", "32.0 sqm · Studio type"),
            ("Unit 503", "1-Bedroom Apartment", "Fifth Floor", 5, 45.5, 17000.00, "VACANT", "45.5 sqm · 1 bedroom"),
            ("Unit 504", "Penthouse Suite", "Fifth Floor", 5, 75.0, 25000.00, "VACANT", "75.0 sqm · Penthouse · Panoramic Deck")
        ]

        unit_objects = {}
        for uno, utype, flr_str, flr_num, usqm, urent, ustatus, udesc in unit_configs:
            u_obj = models.Unit(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                building_id=bldg.id,
                unit_no=uno,
                type=utype,
                floor=flr_str,
                sqm=usqm,
                rent=urent,
                status=ustatus,
                subtitle=udesc
            )
            db.add(u_obj)
            unit_objects[uno] = u_obj
        db.commit()

        unit_101 = unit_objects["Unit 101"]

        # 6. Add Tenant (Maria Santos)
        tenant = models.Tenant(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=tenant_user.id,
            tnt_id="TNT-2026-0101",
            name="Maria Santos",
            email="maria.santos@tenant.ph",
            phone="+63 917 123 4567",
            type="Individual",
            status="Active"
        )
        db.add(tenant)
        db.commit()

        # 7. Add Owner (Don Ramon Santos) & 100% Managing Equity
        owner = models.Owner(
            id=uuid.uuid4(),
            organization_id=org_id,
            user_id=owner_user.id,
            own_id="OWN-2026-088",
            name="Don Ramon Santos",
            email="ramon.santos@owner.ph",
            phone="+63 918 554 9011",
            type="INDIVIDUAL",
            status="ACTIVE"
        )
        db.add(owner)
        db.commit()

        if hasattr(models, "PropertyOwnership"):
            ownership = models.PropertyOwnership(
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                owner_id=owner.id,
                share_percent=100.00,
                role="Primary Managing Owner"
            )
            db.add(ownership)
            db.commit()

        # 8. Add Active Tenancy Lease (Maria Santos in Unit 101)
        lease = models.Lease(
            id=uuid.uuid4(),
            organization_id=org_id,
            lease_id="LSE-2026-0101",
            tenant_id=tenant.id,
            unit_id=unit_101.id,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            rent=15000.00,
            deposit=30000.00,
            status="ACTIVE"
        )
        db.add(lease)
        db.commit()

        # 9. Add Base Rent & Utility Invoices
        invoice_rent = models.Invoice(
            id=uuid.uuid4(),
            organization_id=org_id,
            invoice_id="INV-2026-0801",
            lease_id=lease.id,
            type="Monthly Base Rent — August 2026",
            sub="Sunrise Residences • Tower A • Unit 101",
            category_type="Rent",
            due_date=date(2026, 8, 31),
            amount=15000.00,
            status="Paid",
            channel="GCash Express",
            ref_no="#GC-2026-0819"
        )
        invoice_elec = models.Invoice(
            id=uuid.uuid4(),
            organization_id=org_id,
            invoice_id="UTL-ELE-2026-0801",
            lease_id=lease.id,
            type="Electricity Sub-Meter (144.70 kWh) — August 2026",
            sub="Meralco 144.70 kWh @ ₱12.50/kWh",
            category_type="Electricity",
            due_date=date(2026, 8, 31),
            amount=1808.75,
            status="Unpaid",
            channel="Pending Payment",
            ref_no="#UTL-ELE-2026-0801"
        )
        invoice_water = models.Invoice(
            id=uuid.uuid4(),
            organization_id=org_id,
            invoice_id="UTL-WTR-2026-0802",
            lease_id=lease.id,
            type="Water Sub-Meter (12.50 cu.m) — August 2026",
            sub="Maynilad 12.50 cu.m @ ₱48.00/cu.m",
            category_type="Water",
            due_date=date(2026, 8, 31),
            amount=600.00,
            status="Unpaid",
            channel="Pending Payment",
            ref_no="#UTL-WTR-2026-0802"
        )
        db.add_all([invoice_rent, invoice_elec, invoice_water])
        db.commit()

        # 10. Add Utility Charges Table Records
        if hasattr(models, "UtilityCharge"):
            util_elec = models.UtilityCharge(
                id=uuid.uuid4(),
                organization_id=org_id,
                charge_id="UTL-ELE-2026-0801",
                tenant_name="Maria Santos",
                tenant_email="maria.santos@tenant.ph",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                type="Electricity",
                breakdown="Meralco Sub-Meter 144.70 kWh @ ₱12.50/kWh",
                period="August 2026",
                due_date=date(2026, 8, 31),
                amount=1808.75,
                status="Pending"
            )
            util_wtr = models.UtilityCharge(
                id=uuid.uuid4(),
                organization_id=org_id,
                charge_id="UTL-WTR-2026-0802",
                tenant_name="Maria Santos",
                tenant_email="maria.santos@tenant.ph",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                type="Water",
                breakdown="Maynilad Sub-Meter 12.50 cu.m @ ₱48.00/cu.m",
                period="August 2026",
                due_date=date(2026, 8, 31),
                amount=600.00,
                status="Pending"
            )
            db.add_all([util_elec, util_wtr])
            db.commit()

        # 11. Add Sub-Meter Dial Logs
        if hasattr(models, "MeterReading"):
            reading_elec = models.MeterReading(
                id=uuid.uuid4(),
                organization_id=org_id,
                unit_id=unit_101.id,
                tenant_name="Maria Santos",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                utility="Meralco",
                serial="MER-UNIT101-01",
                prev_dial=1240.50,
                curr_dial=1385.20,
                consumption=144.70,
                unit_symbol="kWh",
                period="August 2026",
                status="Billed to Ledger"
            )
            reading_water = models.MeterReading(
                id=uuid.uuid4(),
                organization_id=org_id,
                unit_id=unit_101.id,
                tenant_name="Maria Santos",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                utility="Maynilad",
                serial="MAY-UNIT101-01",
                prev_dial=210.00,
                curr_dial=222.50,
                consumption=12.50,
                unit_symbol="cu.m",
                period="August 2026",
                status="Billed to Ledger"
            )
            db.add_all([reading_elec, reading_water])
            db.commit()

        # 12. Add Maintenance Work Order
        if hasattr(models, "MaintenanceTicket"):
            ticket = models.MaintenanceTicket(
                id=uuid.uuid4(),
                organization_id=org_id,
                ticket_id="TCK-2026-001",
                unit_id=unit_101.id,
                tenant_name="Maria Santos",
                category="HVAC / Aircon",
                title="Aircon Water Leakage under cabinet",
                description="Master bedroom AC unit is dripping water under cabinet.",
                priority="High",
                status="In Progress",
                technician="Roldan HVAC Services"
            )
            db.add(ticket)
            db.commit()

        # 13. Add Move-In Handover Inspection
        if hasattr(models, "Inspection"):
            insp = models.Inspection(
                id=uuid.uuid4(),
                organization_id=org_id,
                inspection_id="INS-2026-001",
                unit_id=unit_101.id,
                unit_name="Unit 101",
                property_info="Sunrise Residences • Tower A",
                tenant="Maria Santos",
                type="Move-in",
                date=date(2026, 1, 1),
                inspector="Property Admin",
                status="Completed",
                notes="Full move-in condition audit, key inventory, and sub-meter baselines signed off."
            )
            db.add(insp)
            db.commit()

        # 14. Add Master Ledger Yield Transaction
        if hasattr(models, "Transaction"):
            txn = models.Transaction(
                id=uuid.uuid4(),
                organization_id=org_id,
                txn_id="TXN-2026-08-001",
                ref_code="#GC-2026-0819",
                payer="Maria Santos",
                property_location="Sunrise Residences • Tower A • Unit 101",
                category="Rent Collection",
                direction="INFLOW",
                gross_amount=15000.00,
                channel="GCash Express",
                status="Verified / Cleared"
            )
            db.add(txn)
            db.commit()

        # 15. Add Master Legal & Title Documents
        if hasattr(models, "Document"):
            doc1 = models.Document(
                id=uuid.uuid4(),
                organization_id=org_id,
                doc_id="DOC-1001",
                title="Sunrise Residences Title Deed (TCT #49281)",
                file_type="PDF • 4.2 MB",
                entity_name="Sunrise Residences",
                entity_sub="PROP-001 • Primary Deed (Don Ramon Santos)",
                type="Title",
                uploader="Property Admin",
                date=date(2026, 1, 1),
                status="Active"
            )
            doc2 = models.Document(
                id=uuid.uuid4(),
                organization_id=org_id,
                doc_id="DOC-1002",
                title="Signed Residential Tenancy Agreement (LSE-2026-0101)",
                file_type="PDF • 2.4 MB",
                entity_name="Maria Santos",
                entity_sub="Sunrise Residences • Unit 101",
                type="Lease Contract",
                uploader="Juan Dela Cruz (PM)",
                date=date(2026, 1, 1),
                status="Active"
            )
            db.add_all([doc1, doc2])
            db.commit()

        # 16. Add Multi-Role Broadcast Notifications
        if hasattr(models, "Notification"):
            notif_admin = models.Notification(
                id=uuid.uuid4(),
                organization_id=org_id,
                pov="admin",
                category="payment",
                status="unread",
                is_read=False,
                title="GCash Rent Payment Submitted for Audit",
                description="Tenant Maria Santos submitted rent payment for Sunrise Residences • Unit 101 (₱15,000.00). Ref: #GCASH-883192.",
                property="Sunrise Residences • Unit 101",
                tag="Ref #GCASH-883192",
                urgent=False
            )
            notif_client = models.Notification(
                id=uuid.uuid4(),
                organization_id=org_id,
                pov="client",
                category="payment",
                status="unread",
                is_read=False,
                title="Official Rent Receipt Issued & Published",
                description="Your monthly base rent payment of ₱15,000.00 (#GCASH-883192) for Unit 101 has been verified and cleared.",
                property="Sunrise Residences • Unit 101",
                tag="Status: CLEARED",
                urgent=False
            )
            db.add_all([notif_admin, notif_client])
            db.commit()

        print("✅ Database successfully seeded with contract-compliant test data!")
        print("📊 Stats: 1 Property (Sunrise Residences), 1 Building (Tower A), 20 Units (5.0% Occupancy), 1 Tenant (Maria Santos), 1 Owner (Don Ramon Santos - 100%).")

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()