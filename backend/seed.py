import uuid
from datetime import date, datetime
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

        # 2. Add Default User Accounts (Admin, Owner, Client) if User model exists
        if hasattr(models, "User"):
            admin_user = db.query(models.User).filter_by(email="admin@argo.ph").first()
            if not admin_user:
                admin_user = models.User(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    name="Juan Dela Cruz",
                    email="admin@argo.ph",
                    role="admin",
                    avatar="JD",
                    is_active=True
                )
                db.add(admin_user)

            owner_user = db.query(models.User).filter_by(email="ramon.santos@owner.ph").first()
            if not owner_user:
                owner_user = models.User(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    name="Don Ramon Santos",
                    email="ramon.santos@owner.ph",
                    role="owner",
                    avatar="RS",
                    is_active=True
                )
                db.add(owner_user)

            tenant_user = db.query(models.User).filter_by(email="maria.santos@tenant.ph").first()
            if not tenant_user:
                tenant_user = models.User(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    name="Maria Santos",
                    email="maria.santos@tenant.ph",
                    role="client",
                    avatar="MS",
                    is_active=True
                )
                db.add(tenant_user)
            db.commit()

        # 3. Add Property
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

        # 4. Add Building
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

        # 5. Add Units
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

        # 6. Add Tenant
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

        # 7. Add Owner (Don Ramon Santos)
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
            if hasattr(models, "PropertyOwnership"):
                ownership = db.query(models.PropertyOwnership).filter_by(
                    organization_id=org_id, property_id=prop.id, owner_id=owner.id
                ).first()
                if not ownership:
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

        # 8. Add Lease (Maria Santos in Unit 101)
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

            # 9. Add Base Rent Invoice for Client Billing
            invoice_rent = db.query(models.Invoice).filter_by(organization_id=org_id, invoice_id="INV-2026-08").first()
            if not invoice_rent:
                invoice_rent = models.Invoice(
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
                db.add(invoice_rent)

            # 10. Add Sub-Meter Utility Invoices (Meralco & Maynilad)
            invoice_elec = db.query(models.Invoice).filter_by(organization_id=org_id, invoice_id="UTL-ELE-2026-08").first()
            if not invoice_elec:
                invoice_elec = models.Invoice(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    invoice_id="UTL-ELE-2026-08",
                    lease_id=lease.id,
                    type="Electricity Bill (Meralco) — August 2026",
                    sub="Meralco 189.50 kWh @ ₱12.50/kWh",
                    category_type="Electricity",
                    due_date=date(2026, 8, 15),
                    amount=2368.75,
                    status="Unpaid",
                    channel="GCash"
                )
                db.add(invoice_elec)

            invoice_water = db.query(models.Invoice).filter_by(organization_id=org_id, invoice_id="UTL-WTR-2026-08").first()
            if not invoice_water:
                invoice_water = models.Invoice(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    invoice_id="UTL-WTR-2026-08",
                    lease_id=lease.id,
                    type="Water Bill (Maynilad) — August 2026",
                    sub="Maynilad 16.50 cu.m @ ₱48.00/cu.m",
                    category_type="Water",
                    due_date=date(2026, 8, 15),
                    amount=792.00,
                    status="Unpaid",
                    channel="Pending Payment"
                )
                db.add(invoice_water)
            db.commit()

        # 11. Add Maintenance Ticket
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
                status="In Progress",
                technician="Roldan HVAC Services"
            )
            db.add(ticket)
            db.commit()

        # 12. Add Sub-Meter Baseline Readings (if MeterReading model exists)
        if hasattr(models, "MeterReading"):
            reading_elec = db.query(models.MeterReading).filter_by(organization_id=org_id, serial="MER-992810").first()
            if not reading_elec:
                reading_elec = models.MeterReading(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    unit_id=unit1.id,
                    tenant_name="Maria Santos",
                    unit_location="Sunrise Residences • Tower A • Unit 101",
                    utility="Meralco",
                    serial="MER-992810",
                    prev_dial=1420.50,
                    curr_dial=1610.00,
                    consumption=189.50,
                    unit_symbol="kWh",
                    period="August 2026",
                    status="Billed to Ledger"
                )
                db.add(reading_elec)

            reading_water = db.query(models.MeterReading).filter_by(organization_id=org_id, serial="MAY-441209").first()
            if not reading_water:
                reading_water = models.MeterReading(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    unit_id=unit1.id,
                    tenant_name="Maria Santos",
                    unit_location="Sunrise Residences • Tower A • Unit 101",
                    utility="Maynilad",
                    serial="MAY-441209",
                    prev_dial=312.00,
                    curr_dial=328.50,
                    consumption=16.50,
                    unit_symbol="cu.m",
                    period="August 2026",
                    status="Billed to Ledger"
                )
                db.add(reading_water)
            db.commit()

        # 13. Add Move-In Inspection / Handover Log (if Inspection model exists)
        if hasattr(models, "Inspection"):
            insp = db.query(models.Inspection).filter_by(organization_id=org_id, unit_id=unit1.id, type="Move-in").first()
            if not insp:
                insp = models.Inspection(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    inspection_id="INS-2026-001",
                    unit_id=unit1.id,
                    unit_name="Unit 101",
                    property_info="Sunrise Residences • Tower A",
                    tenant="Maria Santos",
                    type="Move-in",
                    date=date(2026, 1, 1),
                    inspector="Property Admin",
                    status="Completed",
                    notes="Full move-in inspection and key handover cleared."
                )
                db.add(insp)
                db.commit()

        # 14. Add Master Ledger Transactions (if Transaction model exists)
        if hasattr(models, "Transaction"):
            txn = db.query(models.Transaction).filter_by(organization_id=org_id, txn_id="TXN-2026-08-001").first()
            if not txn:
                txn = models.Transaction(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    txn_id="TXN-2026-08-001",
                    ref_code="#BDO-TRF8812",
                    payer="Sunrise Property Management",
                    property_location="Sunrise Residences",
                    category="Owner Yield Disbursement",
                    direction="OUTFLOW",
                    gross_amount=-112500.00,
                    channel="Bank Transfer (BDO)",
                    status="Disbursed"
                )
                db.add(txn)
                db.commit()

        # 15. Add Legal & Title Vault Documents (if Document model exists)
        if hasattr(models, "Document"):
            doc1 = db.query(models.Document).filter_by(organization_id=org_id, title="Sunrise Residences Title Deed (TCT #49281)").first()
            if not doc1:
                doc1 = models.Document(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    doc_id="DOC-1001",
                    title="Sunrise Residences Title Deed (TCT #49281)",
                    file_type="PDF • 4.2 MB",
                    entity_name="Sunrise Residences",
                    entity_sub="PROP-001 • Primary Deed",
                    type="Title",
                    uploader="Property Admin",
                    date=date(2024, 1, 15),
                    status="Active"
                )
                db.add(doc1)

            doc2 = db.query(models.Document).filter_by(organization_id=org_id, title="Signed Residential Lease Agreement").first()
            if not doc2:
                doc2 = models.Document(
                    id=uuid.uuid4(),
                    organization_id=org_id,
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
                db.add(doc2)
            db.commit()

        # 16. Add Real-time Notifications (if Notification model exists)
        if hasattr(models, "Notification"):
            notif = db.query(models.Notification).filter_by(organization_id=org_id, title="Tenant Reported Unit Maintenance Issue").first()
            if not notif:
                notif = models.Notification(
                    id=uuid.uuid4(),
                    organization_id=org_id,
                    pov="admin",
                    category="maintenance",
                    status="unread",
                    is_read=False,
                    title="Tenant Reported Unit Maintenance Issue",
                    description="Tenant Maria Santos (Sunrise Residences • Unit 101) submitted a service request: 'AC Unit Leaking Water'.",
                    property="Sunrise Residences • Unit 101",
                    tag="Ticket TCK-2026-001",
                    urgent=True
                )
                db.add(notif)
                db.commit()

        print("✅ Database successfully seeded with contract-compliant test data!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()