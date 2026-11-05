import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.accounts.models import Role, UserRole, UserVerification
from apps.departments.models import Department


class Command(BaseCommand):
    help = "Create base roles, sample departments, and local development accounts."

    def handle(self, *args, **options):
        roles = {
            name: Role.objects.get_or_create(name=name, defaults={"description": description})[0]
            for name, description in [
                ("SUPER_ADMIN", "System-wide administration"),
                ("ADMIN", "Operational administration"),
                ("USER", "Regular user"),
            ]
        }
        departments = {
            code: Department.objects.get_or_create(
                department_code=code,
                defaults={"department_name": name},
            )[0]
            for name, code in [
                ("Information Technology", "IT"),
                ("Procurement", "PROC"),
                ("Finance", "FIN"),
            ]
        }

        User = get_user_model()
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
        name = os.getenv("BOOTSTRAP_ADMIN_NAME", "System Administrator")
        if email and password:
            admin, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "name": name,
                    "is_active": True,
                    "is_staff": True,
                    "is_superuser": True,
                    "verification_status": "VERIFIED",
                },
            )
            if created:
                admin.set_password(password)
                admin.save()
            UserRole.objects.get_or_create(user=admin, role=roles["SUPER_ADMIN"])
            self.stdout.write(self.style.SUCCESS(f"Bootstrap administrator ready: {email}"))
        else:
            self.stdout.write("Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD to create the first admin.")

        # Convenient shared accounts are only created with DEBUG enabled. They
        # make the registration and administrator verification flows testable
        # immediately after starting the local Compose stack.
        if not settings.DEBUG:
            return

        # Earlier demo seeds included a vendor login. Vendors are records only;
        # keep any account created by that seed disabled on upgraded databases.
        User.objects.filter(email="vendor.rep@procurement.local").update(is_active=False, verification_status="REJECTED")

        demo_password = "procurement-demo-2026"
        demo_users = [
            {
                "email": "demo.user@procurement.local",
                "name": "Demo User",
                "status": "VERIFIED",
                "is_active": True,
            },
            {
                "email": "pending.user@procurement.local",
                "name": "Pending Demo User",
                "status": "PENDING",
                "is_active": False,
            },
            {
                "email": "reviewer@procurement.local",
                "name": "Clinical Engineering Reviewer",
                "designation": "TSC Member",
                "status": "VERIFIED",
                "is_active": True,
            },
        ]
        for details in demo_users:
            user, created = User.objects.get_or_create(
                email=details["email"],
                defaults={
                    "name": details["name"],
                    "designation": details.get("designation", ""),
                    "department": departments["IT"],
                    "is_active": details["is_active"],
                    "verification_status": details["status"],
                },
            )
            if created:
                user.set_password(demo_password)
                user.save()
            UserRole.objects.get_or_create(user=user, role=roles["USER"])
            if details["status"] == "PENDING":
                UserVerification.objects.get_or_create(
                    user=user,
                    status="PENDING",
                    defaults={"remarks": "Seeded local development account"},
                )
            self.stdout.write(self.style.SUCCESS(f"Development account ready: {details['email']}"))

        self.seed_demo_project(User, departments["PROC"])
        self.seed_workflow_project(User, departments["PROC"])

    def seed_demo_project(self, User, department):
        """Create one realistic in-progress record for the manual review flow."""
        from django.core.files.base import ContentFile
        from apps.audit.models import AuditLog
        from apps.committees.models import Committee, CommitteeMember
        from apps.documents.models import Document, DocumentVersion
        from apps.procurement.models import ProcurementProject, ProjectActivity, ProjectMember
        from apps.vendors.models import ProjectVendor, Vendor, VendorCategory, VendorCategoryMapping

        creator = User.objects.get(email="demo.user@procurement.local")
        reviewer = User.objects.get(email="reviewer@procurement.local")
        admin = User.objects.filter(is_superuser=True).first()
        project, _ = ProcurementProject.objects.get_or_create(
            title="District Hospital Diagnostic Equipment Procurement",
            defaults={
                "description": "Open tender for diagnostic imaging equipment, installation, training, and a three-year maintenance plan.",
                "department": department,
                "created_by": creator,
                "estimated_amount": "18500000.00",
                "current_status": "TEC_REPORT",
            },
        )
        ProjectMember.objects.get_or_create(project=project, user=creator, defaults={"assigned_by": admin})
        ProjectMember.objects.get_or_create(project=project, user=reviewer, defaults={"assigned_by": admin})
        if admin:
            ProjectMember.objects.get_or_create(project=project, user=admin, defaults={"assigned_by": admin})

        trail = [
            ("PROJECT_CREATED", "Project created with scope, budget estimate, and procurement department."),
            ("DOCUMENT_UPLOADED", "Uploaded initial requirements and technical specification."),
            ("PROJECT_SUBMITTED", "Submitted for procurement review."),
            ("FORWARDED", "Draft → TSC Approval. Requirement submitted."),
            ("FORWARDED", "TSC approved; board formed and TSC report sent for AS (IA) perusal."),
            ("COMMITTEE_FORMED", "Technical Evaluation Committee formed with procurement, clinical engineering, and administration representation."),
            ("VENDOR_ASSOCIATED", "Verified vendor associated: Aster Clinical Systems Pvt Ltd."),
            ("FORWARDED", "TEC report submitted for review."),
        ]
        # Fill in any missing entries if a prior seed run stopped midway.
        for event_type, message in trail:
            ProjectActivity.objects.get_or_create(
                project=project,
                activity_type=event_type,
                message=message,
                defaults={"actor": creator},
            )
        document_activity = project.activities.filter(activity_type="DOCUMENT_UPLOADED").first()

        committee, _ = Committee.objects.get_or_create(
            project=project,
            committee_name="Diagnostic Equipment Technical Evaluation Committee",
            defaults={"formed_by": admin or creator},
        )
        CommitteeMember.objects.get_or_create(
            committee=committee,
            user=creator,
            defaults={"designation": "Procurement Project Lead"},
        )
        CommitteeMember.objects.get_or_create(
            committee=committee,
            user=reviewer,
            defaults={"designation": "Clinical Engineering Reviewer"},
        )
        if admin:
            CommitteeMember.objects.get_or_create(
                committee=committee,
                user=admin,
                defaults={"designation": "Committee Chair · Procurement"},
            )

        category, _ = VendorCategory.objects.get_or_create(
            name="Medical Equipment",
            defaults={"description": "Diagnostic and clinical equipment suppliers"},
        )
        vendor, _ = Vendor.objects.get_or_create(
            vendor_name="Aster Clinical Systems Pvt Ltd",
            defaults={
                "registration_number": "U85110DL2020PTC123456",
                "gstin": "07AABCA1234F1Z5",
                "email": "tenders@asterclinical.example",
                "phone": "+91 11 4000 1200",
                "address": "New Delhi, India",
                "verification_status": "VERIFIED",
                "verified_by": admin,
                "is_active": True,
            },
        )
        VendorCategoryMapping.objects.get_or_create(vendor=vendor, category=category)
        ProjectVendor.objects.get_or_create(project=project, vendor=vendor)
        document = Document.objects.filter(
            project=project,
            document_name="Diagnostic_Equipment_Requirements.pdf",
        ).first()
        if document is None:
            document = Document.objects.create(
                project=project,
                activity=document_activity,
                uploaded_by=creator,
                document_name="Diagnostic_Equipment_Requirements.pdf",
                document_type="PDF",
                mime_type="application/pdf",
                file_size=0,
            )
        elif document.activity_id is None and document_activity:
            document.activity = document_activity
            document.save(update_fields=["activity"])
        if not document.versions.exists():
            pdf = self.sample_pdf(project.project_code)
            version = DocumentVersion.objects.create(
                document=document,
                version_number=1,
                uploaded_by=creator,
                storage_path=ContentFile(pdf, name="Diagnostic_Equipment_Requirements.pdf"),
            )
            document.file_size = len(pdf)
            document.save(update_fields=["file_size"])
            AuditLog.objects.create(
                user=creator,
                entity_type="document",
                entity_id=str(document.id),
                operation="DOCUMENT_UPLOADED",
                new_values={"version": version.version_number, "name": document.document_name},
            )

        self.stdout.write(self.style.SUCCESS(f"Demo project ready: {project.project_code}"))

    def seed_workflow_project(self, User, department):
        """Create a clean Draft project for manually exercising every stage."""
        from django.core.files.base import ContentFile
        from apps.audit.models import AuditLog
        from apps.documents.models import Document, DocumentVersion
        from apps.procurement.models import ProcurementProject, ProjectActivity
        from apps.vendors.models import ProjectVendor, Vendor

        creator = User.objects.get(email="demo.user@procurement.local")
        project, _ = ProcurementProject.objects.get_or_create(
            title="Full Workflow Test — Diagnostic Imaging Equipment",
            defaults={
                "description": "A clean local test case. Progress this from Draft through submission, review, committee formation, committee review, and final approval.",
                "department": department,
                "created_by": creator,
                "estimated_amount": "7200000.00",
                "current_status": "DRAFT",
            },
        )
        if not project.activities.exists():
            ProjectActivity.objects.create(
                project=project,
                actor=creator,
                activity_type="PROJECT_CREATED",
                message="Clean full-workflow test project created in Draft.",
            )
        vendor = Vendor.objects.filter(vendor_name="Aster Clinical Systems Pvt Ltd").first()
        if vendor:
            ProjectVendor.objects.get_or_create(project=project, vendor=vendor)
        document, _ = Document.objects.get_or_create(
            project=project,
            document_name="Workflow_Test_Specification.pdf",
            defaults={
                "activity": project.activities.filter(activity_type="PROJECT_CREATED").first(),
                "uploaded_by": creator,
                "document_type": "PDF",
                "mime_type": "application/pdf",
                "file_size": 0,
            },
        )
        if not document.versions.exists():
            pdf = self.sample_pdf(project.project_code)
            version = DocumentVersion.objects.create(
                document=document,
                version_number=1,
                uploaded_by=creator,
                storage_path=ContentFile(pdf, name="Workflow_Test_Specification.pdf"),
            )
            activity, _ = ProjectActivity.objects.get_or_create(
                project=project,
                activity_type="DOCUMENT_UPLOADED",
                message=f"Uploaded {document.document_name} (version {version.version_number}).",
                defaults={"actor": creator},
            )
            document.activity = activity
            document.file_size = len(pdf)
            document.save(update_fields=["activity", "file_size"])
            AuditLog.objects.get_or_create(
                entity_type="document",
                entity_id=str(document.id),
                operation="DOCUMENT_UPLOADED",
                defaults={
                    "user": creator,
                    "new_values": {"version": version.version_number, "name": document.document_name},
                },
            )
        elif document.activity_id is None:
            activity = project.activities.filter(activity_type="DOCUMENT_UPLOADED").first()
            if activity:
                document.activity = activity
                document.save(update_fields=["activity"])
        self.stdout.write(self.style.SUCCESS(f"Full workflow test project ready: {project.project_code} (status: {project.current_status})"))

    @staticmethod
    def sample_pdf(project_code):
        """Build a tiny valid one-page PDF without adding a PDF dependency."""
        lines = [
            "District Hospital Diagnostic Equipment Procurement",
            f"Project reference: {project_code}",
            "",
            "Procurement scope",
            "Supply and installation of diagnostic imaging equipment.",
            "Include user training and a three-year maintenance plan.",
            "",
            "Evaluation criteria",
            "Technical compliance: 60 points",
            "Lifecycle cost: 25 points",
            "Service and warranty: 15 points",
            "",
            "Committee review copy · Local development sample",
        ]
        commands = ["BT", "/F1 16 Tf", "50 790 Td", f"({lines[0]}) Tj", "/F1 10 Tf"]
        for line in lines[1:]:
            commands.extend(["0 -20 Td", f"({line}) Tj"])
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for number, body in enumerate(objects, 1):
            offsets.append(len(pdf))
            pdf.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
        xref = len(pdf)
        pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010} 00000 n \n".encode())
        pdf.extend(
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        )
        return bytes(pdf)
