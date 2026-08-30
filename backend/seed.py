import uuid
from datetime import date, datetime
from app.database import SessionLocal
from app import models

# Standard bcrypt hash for "password123" (zero external imports needed)
DEFAULT_PASSWORD_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQmG6W5650nxcebGW2y26"


def create_instance_safely(model_cls, **kwargs):
    """Instantiates a SQLAlchemy model with only the fields present on the table."""
    valid_fields = {}
    for key, value in kwargs.items():
        if hasattr(model_cls, key):
            valid_fields[key] = value
    return model_cls(**valid_fields)


def seed_database():
    db = SessionLocal()
    print("🔄 Synchronizing and seeding canonical database records...")
    try:
        # Standard Sandbox Organization UUID matching schema
        org_id = uuid.UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")

        # 0. Clean old/conflicting records for this sandbox org
        print("🧹 Cleaning stale test records in child-to-parent order...")
        cleanup_models = [
            "Notification", "Document", "Inspection", "MeterReading",
            "UtilityCharge", "MaintenanceTicket", "Maintenance",
            "Transaction", "Invoice", "Lease", "PropertyOwnership",
            "Tenant", "Owner", "PropertyOwner", "Unit", "Building",
            "Property", "User", "Organization"
        ]

        for model_name in cleanup_models:
            if hasattr(models, model_name):
                cls = getattr(models, model_name)
                try:
                    if hasattr(cls, "organization_id"):
                        db.query(cls).filter_by(organization_id=org_id).delete()
                    elif hasattr(cls, "id") and model_name == "Organization":
                        db.query(cls).filter_by(id=org_id).delete()
                except Exception:
                    db.rollback()
        db.commit()

        # 1. Organization
        org = create_instance_safely(
            models.Organization,
            id=org_id,
            name="ARGO Property Management Corp.",
            slug="argo-main",
            currency="PHP (₱)",
            pm_fee_percentage=10.00,
            email="operations@argo.ph",
            address="123 Solar St., Metro Manila, Philippines"
        )
        db.add(org)
        db.commit()

        # 2. Add Default User Accounts (Password: password123)
        admin_user_id = uuid.uuid4()
        owner_user_id = uuid.uuid4()
        tenant_user_id = uuid.uuid4()

        admin_user = create_instance_safely(
            models.User,
            id=admin_user_id,
            organization_id=org_id,
            name="Juan Dela Cruz",
            full_name="Juan Dela Cruz",
            email="admin@argo.ph",
            phone="+63 917 882 9102",
            password_hash=DEFAULT_PASSWORD_HASH,
            hashed_password=DEFAULT_PASSWORD_HASH,
            role="admin",
            avatar="JD",
            is_active=True
        )

        owner_user = create_instance_safely(
            models.User,
            id=owner_user_id,
            organization_id=org_id,
            name="Don Ramon Santos",
            full_name="Don Ramon Santos",
            email="ramon.santos@owner.ph",
            phone="+63 918 554 9011",
            password_hash=DEFAULT_PASSWORD_HASH,
            hashed_password=DEFAULT_PASSWORD_HASH,
            role="owner",
            avatar="RS",
            is_active=True
        )

        tenant_user = create_instance_safely(
            models.User,
            id=tenant_user_id,
            organization_id=org_id,
            name="Maria Santos",
            full_name="Maria Santos",
            email="maria.santos@tenant.ph",
            phone="+63 917 123 4567",
            password_hash=DEFAULT_PASSWORD_HASH,
            hashed_password=DEFAULT_PASSWORD_HASH,
            role="client",
            avatar="MS",
            is_active=True
        )
        db.add_all([admin_user, owner_user, tenant_user])
        db.commit()

        # 3. Add Master Property: Sunrise Residences
        prop_id = uuid.uuid4()
        prop = create_instance_safely(
            models.Property,
            id=prop_id,
            organization_id=org_id,
            code="PROP-001",
            name="Sunrise Residences",
            property_name="Sunrise Residences",
            tct_number="TCT #49281-MNL",
            type="Residential Multi-Family",
            location="123 Solar St., Parañaque, Metro Manila",
            units_count=20,
            status="Active"
        )
        db.add(prop)
        db.commit()

        # 4. Add Master Building: Tower A
        bldg_id = uuid.uuid4()
        if hasattr(models, "Building"):
            bldg = create_instance_safely(
                models.Building,
                id=bldg_id,
                organization_id=org_id,
                property_id=prop.id,
                code="BLDG-001",
                name="Tower A",
                floors=5,
                total_units=20,
                occupied_units=1,
                status="Active"
            )
            db.add(bldg)
            db.commit()

        # 5. Add All 20 Inventory Units
        unit_configs = [
            ("Unit 101", "1-Bedroom Apartment", "First Floor", 1, 45.5, 15000.00, "Occupied", "Maria Santos"),
            ("Unit 102", "Studio Deluxe", "First Floor", 1, 32.0, 12500.00, "Available", None),
            ("Unit 103", "1-Bedroom Apartment", "First Floor", 1, 45.5, 15000.00, "Available", None),
            ("Unit 104", "2-Bedroom Suite", "First Floor", 1, 60.0, 20000.00, "Available", None),
            ("Unit 201", "1-Bedroom Apartment", "Second Floor", 2, 45.5, 15500.00, "Available", None),
            ("Unit 202", "Studio Deluxe", "Second Floor", 2, 32.0, 13000.00, "Available", None),
            ("Unit 203", "1-Bedroom Apartment", "Second Floor", 2, 45.5, 15500.00, "Available", None),
            ("Unit 204", "2-Bedroom Suite", "Second Floor", 2, 60.0, 20500.00, "Available", None),
            ("Unit 301", "1-Bedroom Apartment", "Third Floor", 3, 45.5, 16000.00, "Available", None),
            ("Unit 302", "Studio Deluxe", "Third Floor", 3, 32.0, 13500.00, "Available", None),
            ("Unit 303", "1-Bedroom Apartment", "Third Floor", 3, 45.5, 16000.00, "Available", None),
            ("Unit 304", "2-Bedroom Suite", "Third Floor", 3, 60.0, 21000.00, "Available", None),
            ("Unit 401", "1-Bedroom Apartment", "Fourth Floor", 4, 45.5, 16500.00, "Available", None),
            ("Unit 402", "Studio Deluxe", "Fourth Floor", 4, 32.0, 14000.00, "Available", None),
            ("Unit 403", "1-Bedroom Apartment", "Fourth Floor", 4, 45.5, 16500.00, "Available", None),
            ("Unit 404", "2-Bedroom Suite", "Fourth Floor", 4, 60.0, 21500.00, "Available", None),
            ("Unit 501", "1-Bedroom Apartment", "Fifth Floor", 5, 45.5, 17000.00, "Available", None),
            ("Unit 502", "Studio Deluxe", "Fifth Floor", 5, 32.0, 14500.00, "Available", None),
            ("Unit 503", "1-Bedroom Apartment", "Fifth Floor", 5, 45.5, 17000.00, "Available", None),
            ("Unit 504", "Penthouse Suite", "Fifth Floor", 5, 75.0, 25000.00, "Available", None)
        ]

        unit_objects = {}
        for uno, utype, flr_str, flr_num, usqm, urent, ustatus, utenant in unit_configs:
            u_obj = create_instance_safely(
                models.Unit,
                id=uuid.uuid4(),
                organization_id=org_id,
                property_id=prop.id,
                building_id=bldg_id,
                unit_no=uno,
                unit_number=uno,
                type=utype,
                floor=flr_str,
                floor_number=flr_num,
                sqm=usqm,
                rent=urent,
                rent_amount=urent,
                status=ustatus,
                tenant_name=utenant,
                subtitle=f"{usqm} sqm · {utype}"
            )
            db.add(u_obj)
            unit_objects[uno] = u_obj
        db.commit()

        unit_101 = unit_objects["Unit 101"]

        # 6. Add Tenant (Maria Santos)
        tenant_id = uuid.uuid4()
        tenant = create_instance_safely(
            models.Tenant,
            id=tenant_id,
            organization_id=org_id,
            user_id=tenant_user.id,
            tenant_id="TNT-2026-0101",
            tnt_id="TNT-2026-0101",
            name="Maria Santos",
            email="maria.santos@tenant.ph",
            phone="+63 917 123 4567",
            type="Individual",
            unit="Sunrise Residences • Tower A • Unit 101",
            lease_id="LSE-2026-0101",
            emergency_contact="Juan Dela Cruz (+63 917 882 9102)",
            status="Active"
        )
        db.add(tenant)
        db.commit()

        # 7. Add Owner (Don Ramon Santos) & 100% Managing Equity
        owner_cls = getattr(models, "Owner", getattr(models, "PropertyOwner", None))
        owner_id = uuid.uuid4()
        if owner_cls:
            owner = create_instance_safely(
                owner_cls,
                id=owner_id,
                organization_id=org_id,
                user_id=owner_user.id,
                own_id="OWN-2026-088",
                name="Don Ramon Santos",
                email="ramon.santos@owner.ph",
                phone="+63 918 554 9011",
                type="INDIVIDUAL",
                tin="231-998-102-000",
                status="Active"
            )
            db.add(owner)
            db.commit()

            if hasattr(models, "PropertyOwnership"):
                ownership = create_instance_safely(
                    models.PropertyOwnership,
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    property_id=prop.id,
                    owner_id=owner.id,
                    share_percent=100.00,
                    role="Primary Managing Owner",
                    start_date=date(2026, 1, 1),
                    contract_ref="DEED-2026-001"
                )
                db.add(ownership)
                db.commit()

        # 8. Add Active Tenancy Lease (Maria Santos in Unit 101)
        lease_id = uuid.uuid4()
        lease = create_instance_safely(
            models.Lease,
            id=lease_id,
            organization_id=org_id,
            property_id=prop.id,
            unit_id=unit_101.id,
            tenant_id=tenant.id,
            lease_id="LSE-2026-0101",
            tenant_name="Maria Santos",
            tenant_email="maria.santos@tenant.ph",
            property_name="Sunrise Residences",
            unit_number="Unit 101",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            rent=15000.00,
            deposit=30000.00,
            status="Active"
        )
        db.add(lease)
        db.commit()

        # 9. Add Invoices (Rent & Utilities)
        invoice_rent = create_instance_safely(
            models.Invoice,
            id=uuid.uuid4(),
            organization_id=org_id,
            lease_id=lease.id,
            invoice_id="INV-2026-0801",
            tenant_name="Maria Santos",
            tenant_email="maria.santos@tenant.ph",
            type="Monthly Base Rent — August 2026",
            sub="Sunrise Residences • Tower A • Unit 101",
            property_location="Sunrise Residences • Tower A • Unit 101",
            category_type="Rent",
            due_date=date(2026, 8, 31),
            amount=15000.00,
            status="Paid",
            channel="GCash Express",
            ref_no="#GC-2026-0819"
        )

        invoice_elec = create_instance_safely(
            models.Invoice,
            id=uuid.uuid4(),
            organization_id=org_id,
            lease_id=lease.id,
            invoice_id="UTL-ELE-2026-0801",
            tenant_name="Maria Santos",
            tenant_email="maria.santos@tenant.ph",
            type="Electricity Sub-Meter (144.70 kWh) — August 2026",
            sub="Meralco 144.70 kWh @ ₱12.50/kWh",
            property_location="Sunrise Residences • Tower A • Unit 101",
            category_type="Electricity",
            due_date=date(2026, 8, 31),
            amount=1808.75,
            status="UNPAID",
            channel="GCash",
            ref_no="#UTL-ELE-2026-0801"
        )

        invoice_water = create_instance_safely(
            models.Invoice,
            id=uuid.uuid4(),
            organization_id=org_id,
            lease_id=lease.id,
            invoice_id="UTL-WTR-2026-0802",
            tenant_name="Maria Santos",
            tenant_email="maria.santos@tenant.ph",
            type="Water Sub-Meter (12.50 cu.m) — August 2026",
            sub="Maynilad 12.50 cu.m @ ₱48.00/cu.m",
            property_location="Sunrise Residences • Tower A • Unit 101",
            category_type="Water",
            due_date=date(2026, 8, 31),
            amount=600.00,
            status="UNPAID",
            channel="GCash",
            ref_no="#UTL-WTR-2026-0802"
        )
        db.add_all([invoice_rent, invoice_elec, invoice_water])
        db.commit()

        # 10. Add Utility Charges Table Records
        if hasattr(models, "UtilityCharge"):
            util_elec = create_instance_safely(
                models.UtilityCharge,
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
                status="UNPAID"
            )
            util_wtr = create_instance_safely(
                models.UtilityCharge,
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
                status="UNPAID"
            )
            db.add_all([util_elec, util_wtr])
            db.commit()

        # 11. Add Sub-Meter Dial Logs
        if hasattr(models, "MeterReading"):
            reading_elec = create_instance_safely(
                models.MeterReading,
                id=uuid.uuid4(),
                organization_id=org_id,
                unit_id=unit_101.id,
                reading_id="MET-2026-001",
                tenant_name="Maria Santos",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                utility="Meralco",
                serial="MER-UNIT101-01",
                prev_dial=1240.50,
                curr_dial=1385.20,
                consumption=144.70,
                unit_symbol="kWh",
                period="August 2026",
                status="Billed"
            )
            reading_water = create_instance_safely(
                models.MeterReading,
                id=uuid.uuid4(),
                organization_id=org_id,
                unit_id=unit_101.id,
                reading_id="MET-2026-002",
                tenant_name="Maria Santos",
                unit_location="Sunrise Residences • Tower A • Unit 101",
                utility="Maynilad",
                serial="MAY-UNIT101-01",
                prev_dial=210.00,
                curr_dial=222.50,
                consumption=12.50,
                unit_symbol="cu.m",
                period="August 2026",
                status="Billed"
            )
            db.add_all([reading_elec, reading_water])
            db.commit()

        # 12. Add Maintenance Work Order
        maint_cls = getattr(models, "MaintenanceTicket", getattr(models, "Maintenance", None))
        if maint_cls:
            ticket = create_instance_safely(
                maint_cls,
                id=uuid.uuid4(),
                organization_id=org_id,
                unit_id=unit_101.id,
                ticket_id="TCK-2026-001",
                tenant_name="Maria Santos",
                tenant_email="maria.santos@tenant.ph",
                property_location="Sunrise Residences • Tower A • Unit 101",
                category="HVAC / Aircon",
                title="Aircon Water Leakage under cabinet",
                description="Master bedroom AC unit is dripping water under cabinet.",
                priority="High",
                status="In Progress",
                technician="Roldan HVAC Services",
                cost=1200.00
            )
            db.add(ticket)
            db.commit()

        # 13. Add Move-In Handover Inspection
        if hasattr(models, "Inspection"):
            insp = create_instance_safely(
                models.Inspection,
                id=uuid.uuid4(),
                organization_id=org_id,
                unit_id=unit_101.id,
                inspection_id="INS-2026-001",
                unit_name="Unit 101",
                property_info="Sunrise Residences • Tower A",
                tenant="Maria Santos",
                type="Move-In",
                date=date(2026, 1, 1),
                inspector="Property Manager",
                status="Passed",
                notes="Move-In Handover Checklist (Score: 100%). Keys: 3 Keys, 2 RFIDs, 1 Remote issued. Baselines: 1240.50 kWh / 210.00 cu.m."
            )
            db.add(insp)
            db.commit()

        # 14. Add Master Ledger Yield Transaction
        if hasattr(models, "Transaction"):
            txn = create_instance_safely(
                models.Transaction,
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
                status="Completed",
                timestamp="Aug 19, 2026"
            )
            db.add(txn)
            db.commit()

        # 15. Add Legal & Title Documents
        if hasattr(models, "Document"):
            doc1 = create_instance_safely(
                models.Document,
                id=uuid.uuid4(),
                organization_id=org_id,
                doc_id="DOC-1001",
                title="Sunrise Residences Title Deed (TCT #49281)",
                file_type="PDF • 4.2 MB",
                entity_name="Sunrise Residences",
                entity_sub="Sunrise Residences (PROP-001)",
                type="Title",
                uploader="Property Admin",
                date=date(2026, 1, 1),
                status="Verified",
                notes="Certified legal land title registered under Sunrise Residences. TCT Ref: TCT #49281-MNL."
            )
            doc2 = create_instance_safely(
                models.Document,
                id=uuid.uuid4(),
                organization_id=org_id,
                doc_id="DOC-1002",
                title="Signed Residential Tenancy Agreement (LSE-2026-0101)",
                file_type="PDF • 2.4 MB",
                entity_name="Maria Santos",
                entity_sub="Sunrise Residences • Unit 101",
                type="Lease Contract",
                uploader="Leasing Desk",
                date=date(2026, 1, 1),
                status="Verified",
                notes="Legally executed lease agreement for Sunrise Residences • Unit 101. Monthly Rent: ₱15,000.00."
            )
            db.add_all([doc1, doc2])
            db.commit()

        # 16. Add Multi-Role Broadcast Notifications
        if hasattr(models, "Notification"):
            notif_admin = create_instance_safely(
                models.Notification,
                id=uuid.uuid4(),
                organization_id=org_id,
                user_id=admin_user_id,
                pov="admin",
                category="payment",
                status="Active",
                is_read=False,
                title="GCash Rent Payment Submitted for Audit",
                description="Tenant Maria Santos submitted rent payment for Sunrise Residences • Unit 101 (₱15,000.00). Ref: #GC-2026-0819.",
                property="Sunrise Residences • Unit 101",
                amount="₱15,000.00",
                tag="Ref #GC-2026-0819",
                action_url="rent-collection.html",
                action_text="Verify Payment",
                urgent=False
            )
            notif_client = create_instance_safely(
                models.Notification,
                id=uuid.uuid4(),
                organization_id=org_id,
                user_id=tenant_user_id,
                pov="client",
                category="payment",
                status="Active",
                is_read=False,
                title="Official Rent Receipt Issued & Published",
                description="Your monthly base rent payment of ₱15,000.00 (#GC-2026-0819) for Unit 101 has been verified and cleared.",
                property="Sunrise Residences • Unit 101",
                amount="₱15,000.00",
                tag="Status: CLEARED",
                action_url="client-billing.html",
                action_text="View Receipt",
                urgent=False
            )
            db.add_all([notif_admin, notif_client])
            db.commit()

        print("✅ Database successfully seeded with contract-compliant test data!")
        print("🔑 Test Credentials (Password: password123 for all):")
        print("   - Admin: admin@argo.ph")
        print("   - Owner: ramon.santos@owner.ph")
        print("   - Tenant: maria.santos@tenant.ph")

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()