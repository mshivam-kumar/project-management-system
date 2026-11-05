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

        # Ready-to-use accounts for the stage-by-stage manual procurement run.
        # Like the other demo accounts, these are local DEBUG-only fixtures.
        stage_password = "StageWalk!4826a"
        stage_users = [
            ("tsc.a@procurement.local", "TSC Reviewer", "TSC Member"),
            ("as.ia.a@procurement.local", "AS IA Reviewer", "AS IA"),
            ("dg.ss.a@procurement.local", "DG SS Approver", "DG SS"),
            ("hq.a@procurement.local", "HQ Reviewer", "HQ"),
            ("cs.sr.a@procurement.local", "CS SR Reviewer", "CS SR"),
            ("ia.a@procurement.local", "IA Reviewer", "IA"),
            ("tender.a@procurement.local", "Tender Committee Member", "Procurement Member"),
            ("ss.a@procurement.local", "SS Approver", "SS"),
            ("tec.a@procurement.local", "TEC Member", "TEC Member"),
            ("tac.a@procurement.local", "TAC Member", "TAC Member"),
            ("user.rep.a@procurement.local", "User Representative", "User Representative"),
            ("ifd.cfa.a@procurement.local", "IFD CFA Approver", "IFD CFA"),
        ]
        verifier = User.objects.filter(is_superuser=True).first()
        for stage_email, stage_name, designation in stage_users:
            user, created = User.objects.get_or_create(
                email=stage_email,
                defaults={
                    "name": stage_name,
                    "designation": designation,
                    "department": departments["PROC"],
                    "is_active": True,
                    "verification_status": "VERIFIED",
                },
            )
            if created:
                user.set_password(stage_password)
                user.save()
            UserRole.objects.get_or_create(user=user, role=roles["USER"])
            UserVerification.objects.get_or_create(
                user=user,
                status="VERIFIED",
                defaults={
                    "verified_by": verifier,
                    "remarks": "Seeded local manual workflow account",
                },
            )
            self.stdout.write(self.style.SUCCESS(f"Manual workflow account ready: {stage_email}"))

        self.seed_demo_project(User, departments["PROC"], stage_users)

    def seed_demo_project(self, User, department, stage_users):
        """Create one realistic in-progress record for the manual review flow."""
        from django.core.files.base import ContentFile
        from apps.audit.models import AuditLog
        from apps.committees.models import Committee, CommitteeMember
        from apps.documents.models import Document, DocumentVersion
        from apps.procurement.models import ProcurementProject, ProjectActivity, ProjectMember, ProjectQuery, ProjectQueryReply
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
            ("COMMITTEE_FORMED", "TSC Committee formed and members assigned."),
            ("APPROVED", "TSC approved; board formed."),
            ("COMMITTEE_FORMED", "TSC Board formed with assigned members."),
            ("FORWARDED", "TSC report submitted for AS (IA) perusal."),
            ("APPROVED", "AS (IA) reviewed and approved the TSC report."),
            ("APPROVED", "DG/SS approval recorded."),
            ("STATUS_CHANGED", "HQ query raised and answered; file forwarded for CS (SR) review."),
            ("STATUS_CHANGED", "CS (SR) query raised and answered."),
            ("FORWARDED", "TSC report forwarded to CS (SR), then draft tender sent to IA Wing."),
            ("APPROVED", "IA acknowledged the draft tender and issued the tender."),
            ("VENDOR_ASSOCIATED", "Verified vendor associated: Aster Clinical Systems Pvt Ltd."),
            ("DOCUMENT_UPLOADED", "Vendor technical response received by the committee."),
            ("COMMITTEE_FORMED", "Technical Bid Opening Board formed."),
            ("COMMITTEE_FORMED", "TEC formed after SS approval; TEC report preparation started."),
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

        stage_committees = [
            ("TSC Committee", ["tsc.a@procurement.local"]),
            ("TSC Board", ["tsc.a@procurement.local"]),
            ("AS IA Committee", ["as.ia.a@procurement.local"]),
            ("DG SS Committee", ["dg.ss.a@procurement.local"]),
            ("HQ Committee", ["hq.a@procurement.local"]),
            ("CS SR Committee", ["cs.sr.a@procurement.local"]),
            ("IA Wing Committee", ["ia.a@procurement.local"]),
            ("Procurement Tender Committee", ["tender.a@procurement.local"]),
            ("Technical Bid Opening Board", ["tender.a@procurement.local", "tec.a@procurement.local"]),
            ("TEC", ["tec.a@procurement.local"]),
            ("TAC", ["tac.a@procurement.local", "user.rep.a@procurement.local"]),
            ("IFD CFA Committee", ["ifd.cfa.a@procurement.local"]),
        ]
        for committee_name, member_emails in stage_committees:
            committee, created = Committee.objects.get_or_create(
                project=project,
                committee_name=committee_name,
                defaults={"formed_by": admin or creator},
            )
            if created:
                ProjectActivity.objects.get_or_create(
                    project=project,
                    activity_type="COMMITTEE_FORMED",
                    message=f"Committee formed: {committee_name}.",
                    defaults={"actor": admin or creator},
                )
            for member_email in member_emails:
                member_user = User.objects.get(email=member_email)
                CommitteeMember.objects.get_or_create(
                    committee=committee,
                    user=member_user,
                    defaults={"designation": member_user.designation},
                )

        # Every local workflow login can open this seeded project. Stage actions
        # still use the designation and committee checks in the workflow view.
        stage_emails = [email for email, _, _ in stage_users]
        for member_user in User.objects.filter(email__in=stage_emails):
            ProjectMember.objects.get_or_create(
                project=project,
                user=member_user,
                defaults={"assigned_by": admin or creator},
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
        seeded_documents = [
            ("TSC_Committee_Report.pdf", "Uploaded TSC committee report for AS (IA) perusal."),
            ("Draft_Tender.pdf", "Uploaded draft tender reviewed by IA Wing."),
            ("Vendor_Technical_Response.pdf", "Vendor technical response received by the committee."),
            ("TEC_Report_Draft.pdf", "TEC report preparation started."),
        ]
        for document_name, activity_message in [("Diagnostic_Equipment_Requirements.pdf", "Uploaded initial requirements and technical specification."), *seeded_documents]:
            activity, _ = ProjectActivity.objects.get_or_create(
                project=project,
                activity_type="DOCUMENT_UPLOADED",
                message=activity_message,
                defaults={"actor": creator},
            )
            doc, _ = Document.objects.get_or_create(
                project=project,
                document_name=document_name,
                defaults={
                    "activity": activity,
                    "uploaded_by": creator,
                    "document_type": "PDF",
                    "mime_type": "application/pdf",
                    "file_size": 0,
                },
            )
            if not doc.versions.exists():
                pdf = self.sample_pdf(project.project_code)
                version = DocumentVersion.objects.create(
                    document=doc,
                    version_number=1,
                    uploaded_by=creator,
                    storage_path=ContentFile(pdf, name=document_name),
                )
                doc.file_size = len(pdf)
                doc.save(update_fields=["file_size"])
                AuditLog.objects.create(
                    user=creator,
                    entity_type="document",
                    entity_id=str(doc.id),
                    operation="DOCUMENT_UPLOADED",
                    new_values={"version": version.version_number, "name": document_name},
                )

        seeded_queries = [
            ("HQ_REVIEW", "Confirm equipment compatibility", "Please confirm the requested interface standard.", "hq.a@procurement.local", "tsc.a@procurement.local", ""),
            ("CS_SR_REVIEW", "Confirm service coverage", "Please confirm the proposed service period.", "cs.sr.a@procurement.local", "tsc.a@procurement.local", ""),
            ("VENDOR_RESPONSE", "Clarify delivery schedule", "Please confirm the requested installation timeline.", "tender.a@procurement.local", "tender.a@procurement.local", ""),
            ("TEC_REPORT", "Clarify evaluation criterion", "Please confirm the interpretation of criterion 4.", "hq.a@procurement.local", "tec.a@procurement.local", "TEC"),
        ]
        for stage, subject, body, raised_email, reply_email, target_designation in seeded_queries:
            raised_by = User.objects.get(email=raised_email)
            replied_by = User.objects.get(email=reply_email)
            query, _ = ProjectQuery.objects.get_or_create(
                project=project,
                stage=stage,
                subject=subject,
                defaults={
                    "body": body,
                    "raised_by": raised_by,
                    "target_designation": target_designation,
                    "target_vendor": vendor if stage == "VENDOR_RESPONSE" else None,
                    "status": "ANSWERED",
                },
            )
            ProjectQueryReply.objects.get_or_create(
                query=query,
                actor=replied_by,
                body="Confirmed. The requirement and evaluation record have been updated accordingly.",
            )
            ProjectActivity.objects.get_or_create(
                project=project,
                activity_type="STATUS_CHANGED",
                message=f"Query raised and answered at {stage.replace('_', ' ')}: {subject}",
                defaults={"actor": replied_by},
            )

        self.stdout.write(self.style.SUCCESS(f"Demo project ready: {project.project_code}"))

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
