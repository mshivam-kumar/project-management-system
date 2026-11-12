from datetime import date, timedelta

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User, UserRole
from apps.audit.models import AuditLog
from apps.committees.models import Committee, CommitteeMember
from apps.departments.models import Department
from apps.procurement.models import ProcurementProject, ProjectMember
from apps.vendors.models import ProjectVendor, Vendor, VendorCategory
from .models import (
    ApprovalEvent,
    ApprovalPolicy,
    ApprovalPolicyLevel,
    ApprovalRequest,
    ApprovalStep,
    BidDocument,
    ProjectStage,
    StageSubmission,
    TACVendorShortlist,
    TACWorkDocument,
    Tender,
    TenderDispatch,
    TECWorkDocument,
    TSCWorkDocument,
    VendorBid,
    VendorSelection,
)
from .serializers import ApprovalPolicySerializer


class ProcurementWorkflowApiTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            department_name="Procurement", department_code="PROC"
        )
        self.admin = self.make_user("admin@example.org", "ADMIN")
        self.admin.name = "Procurement Administrator"
        self.admin.employee_id = "EMP-ADMIN-01"
        self.admin.save(update_fields=["name", "employee_id"])
        self.super_admin = self.make_user(
            "super-admin@example.org", "SUPER_ADMIN", is_superuser=True
        )
        self.member = self.make_user("member@example.org", "USER")
        self.member.employee_id = "EMP-TEST-01"
        self.member.save(update_fields=["employee_id"])
        self.chair = self.make_user("chair@example.org", "USER")
        self.chair.employee_id = "EMP-TEST-02"
        self.chair.save(update_fields=["employee_id"])
        self.approver = self.make_user("approver@example.org", "SS")
        self.level2_approver = self.make_user("approver-level2@example.org", "AS")
        self.hq_approver = self.make_user("hq-approver@example.org", "HQ")
        self.level3_approver = self.make_user("approver-level3@example.org", "DGS")
        self.level4_approver = self.make_user("approver-level4@example.org", "IA_WING")
        self.outsider = self.make_user("outsider@example.org", "USER")
        self.project = ProcurementProject.objects.create(
            title="Office equipment",
            description="Procurement of office equipment for the department.",
            department=self.department,
            created_by=self.admin,
        )
        self.formation_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TSC_FORMATION,
            sequence=1,
            planned_start=date(2026, 11, 3),
            due_date=date(2026, 11, 10),
            created_by=self.admin,
        )
        self.report_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TSC_REPORT,
            sequence=2,
            created_by=self.admin,
        )
        self.formation_policy = self.make_policy(
            StageSubmission.Type.TSC_FORMATION, "Formation approval"
        )
        self.report_policy = self.make_policy(
            StageSubmission.Type.TSC_REPORT, "Report approval"
        )
        self.report_level3_policy = self.make_policy(
            StageSubmission.Type.TSC_REPORT_LEVEL3, "Level 3 report approval"
        )
        self.tender_policy = self.make_policy(
            StageSubmission.Type.TENDER_DRAFT, "Tender draft approval"
        )
        self.tec_formation_policy = self.make_policy(
            StageSubmission.Type.TEC_FORMATION, "TEC formation approval"
        )
        self.tac_formation_policy = self.make_policy(
            StageSubmission.Type.TAC_FORMATION, "TAC formation approval"
        )
        self.tec_report_policy = self.make_policy(
            StageSubmission.Type.TEC_REPORT, "TEC report HQ approval"
        )

    def make_user(self, email, role_name, is_superuser=False):
        user = User.objects.create_user(
            email=email,
            password="strong-test-password-2026",
            name=email.split("@")[0],
            is_active=True,
            verification_status="VERIFIED",
            is_superuser=is_superuser,
        )
        role, _ = Role.objects.get_or_create(name=role_name)
        UserRole.objects.create(user=user, role=role)
        return user

    def make_policy(self, submission_type, name):
        policy = ApprovalPolicy.objects.create(
            name=name,
            submission_type=submission_type,
            created_by=self.admin,
        )
        roles = {
            StageSubmission.Type.TSC_FORMATION: ["SS"],
            StageSubmission.Type.TEC_FORMATION: ["SS"],
            StageSubmission.Type.TAC_FORMATION: ["SS"],
            StageSubmission.Type.TSC_REPORT: ["AS", "HQ"],
            StageSubmission.Type.TSC_REPORT_LEVEL3: ["DGS"],
            StageSubmission.Type.TEC_REPORT: ["HQ"],
            StageSubmission.Type.TENDER_DRAFT: ["IA_WING"],
        }.get(submission_type, ["UPPER_LEVEL"])
        ApprovalPolicyLevel.objects.bulk_create([
            ApprovalPolicyLevel(
                policy=policy,
                sequence=sequence,
                approver_role=role,
            )
            for sequence, role in enumerate(roles, start=1)
        ])
        return policy

    def pdf(self, name="report.pdf"):
        return SimpleUploadedFile(
            name,
            b"%PDF-1.4\nworkflow test document\n%%EOF",
            content_type="application/pdf",
        )

    def test_seed_command_restores_tsc_report_approval_sequence(self):
        self.report_policy.is_active = False
        self.report_policy.save(update_fields=["is_active"])

        call_command("seed_initial_data", verbosity=0)

        active_policy = ApprovalPolicy.objects.get(
            submission_type=StageSubmission.Type.TSC_REPORT,
            is_active=True,
        )
        self.assertEqual(
            list(active_policy.levels.values_list("approver_role", flat=True)),
            ["AS", "HQ"],
        )
        active_policy.levels.filter(sequence=1).update(approver_role="HQ")
        active_policy.levels.filter(sequence=2).update(approver_role="AS")
        call_command("seed_initial_data", verbosity=0)
        self.assertEqual(
            ApprovalPolicy.objects.filter(
                submission_type=StageSubmission.Type.TSC_REPORT,
                is_active=True,
            ).count(),
            1,
        )
        self.assertEqual(
            list(active_policy.levels.order_by("sequence").values_list(
                "approver_role", flat=True,
            )),
            ["AS", "HQ"],
        )
        tender_policy = ApprovalPolicy.objects.get(
            submission_type=StageSubmission.Type.TENDER_DRAFT,
            is_active=True,
        )
        self.assertEqual(
            list(tender_policy.levels.values_list("approver_role", flat=True)),
            ["IA_WING"],
        )
        tec_policy = ApprovalPolicy.objects.get(
            submission_type=StageSubmission.Type.TEC_FORMATION,
            is_active=True,
        )
        self.assertEqual(tec_policy.name, "TEC Formation - SS Approval")
        self.assertEqual(
            list(tec_policy.levels.values_list("approver_role", flat=True)),
            ["SS"],
        )
        tac_policy = ApprovalPolicy.objects.get(
            submission_type=StageSubmission.Type.TAC_FORMATION,
            is_active=True,
        )
        self.assertEqual(tac_policy.name, "TAC Formation - SS Approval")
        self.assertEqual(
            list(tac_policy.levels.values_list("approver_role", flat=True)),
            ["SS"],
        )
        tec_report_policy = ApprovalPolicy.objects.get(
            submission_type=StageSubmission.Type.TEC_REPORT,
            is_active=True,
        )
        self.assertEqual(
            list(tec_report_policy.levels.values_list("approver_role", flat=True)),
            ["HQ"],
        )

    def test_seed_command_repairs_multilevel_tac_formation_policy(self):
        policy = self.tac_formation_policy
        policy.name = "Tac Formation - Three Level Approval"
        policy.save(update_fields=["name"])
        policy.levels.all().delete()
        ApprovalPolicyLevel.objects.bulk_create([
            ApprovalPolicyLevel(policy=policy, sequence=1, approver_role="SS"),
            ApprovalPolicyLevel(policy=policy, sequence=2, approver_role="AS"),
            ApprovalPolicyLevel(policy=policy, sequence=3, approver_role="DGS"),
        ])

        call_command("seed_initial_data", verbosity=0)

        policy.refresh_from_db()
        self.assertEqual(policy.name, "TAC Formation - SS Approval")
        self.assertEqual(
            list(policy.levels.values_list("sequence", "approver_role")),
            [(1, "SS")],
        )

    def test_tec_formation_requires_all_dispatches_and_uses_ss_approval_trail(self):
        ProjectStage.objects.filter(project=self.project).update(
            status=ProjectStage.Status.COMPLETED
        )
        level3_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TSC_REPORT_LEVEL3,
            sequence=3,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        tender_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TENDER_DRAFT,
            sequence=4,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        StageSubmission.objects.create(
            stage=level3_stage,
            submission_type=StageSubmission.Type.TSC_REPORT_LEVEL3,
            submitted_by=self.chair,
            title="Approved TSC report",
            status=StageSubmission.Status.APPROVED,
        )
        StageSubmission.objects.create(
            stage=tender_stage,
            submission_type=StageSubmission.Type.TENDER_DRAFT,
            submitted_by=self.admin,
            title="Approved tender draft",
            status=StageSubmission.Status.APPROVED,
        )
        tender = Tender.objects.create(
            project=self.project,
            status=Tender.Status.APPROVED,
            created_by=self.admin,
        )
        vendors = [
            Vendor.objects.create(
                vendor_name=f"TEC Supplier {index}",
                verification_status=Vendor.Status.VERIFIED,
                is_active=True,
            )
            for index in range(2)
        ]
        project_vendors = [
            ProjectVendor.objects.create(
                project=self.project,
                vendor=vendor,
                participation_status="SELECTED",
            )
            for vendor in vendors
        ]
        client = APIClient()
        client.force_authenticate(self.chair)
        payload = {
            "project": str(self.project.id),
            "committee_name": "Technical Evaluation Committee",
            "committee_type": "TEC",
            "chair": str(self.chair.id),
            "member_ids": [str(self.member.id), str(self.chair.id)],
        }
        response = client.post("/api/v1/workflow/committees/", payload, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("committee_type", response.data)
        self.assertFalse(Committee.objects.filter(
            project=self.project,
            committee_type=Committee.Type.TEC,
        ).exists())

        for project_vendor in project_vendors:
            project_vendor.participation_status = "TENDER_SENT"
            project_vendor.save(update_fields=["participation_status"])
            TenderDispatch.objects.create(
                tender=tender,
                vendor=project_vendor.vendor,
                recorded_by=self.admin,
                dispatched_at=timezone.now(),
            )
        response = client.post("/api/v1/workflow/committees/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        committee_id = response.data["id"]
        committee = Committee.objects.get(id=committee_id)
        self.assertEqual(committee.status, "SUBMITTED")
        self.assertEqual(
            ProjectStage.objects.get(
                project=self.project,
                stage_type=ProjectStage.Type.TEC_FORMATION,
            ).status,
            ProjectStage.Status.WAITING_APPROVAL,
        )
        submission = StageSubmission.objects.get(
            committee=committee,
            submission_type=StageSubmission.Type.TEC_FORMATION,
        )
        self.assertEqual(
            list(ApprovalRequest.objects.get(submission=submission).steps.values_list(
                "approver_role", flat=True,
            )),
            ["SS"],
        )
        self.assertFalse(ProjectMember.objects.filter(
            project=self.project,
            user__in=[self.member, self.chair],
        ).exists())

        client.force_authenticate(self.chair)
        response = client.get("/api/v1/projects/")
        self.assertNotIn(
            str(self.project.id),
            {project["id"] for project in response.data["results"]},
        )
        client.force_authenticate(self.level2_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn(
            str(submission.id),
            {item["submission_id"] for item in response.data["pending_approvals"]},
        )
        client.force_authenticate(self.approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(
            str(submission.id),
            {item["submission_id"] for item in response.data["pending_approvals"]},
        )

        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/query/",
            {"comment": "Please revise the committee membership."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "The requested membership revision is complete.",
                "committee_name": "Revised Technical Evaluation Committee",
                "chair": str(self.chair.id),
                "member_ids": [str(self.member.id), str(self.chair.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            submission.approval_requests.get().events.filter(
                action=ApprovalEvent.Action.RESPONSE,
            ).count(),
            1,
        )
        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/approve/",
            {"comment": "TEC formation approved."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        committee.refresh_from_db()
        self.assertEqual(committee.status, "ACTIVE")
        self.assertEqual(committee.committee_name, "Revised Technical Evaluation Committee")
        self.assertTrue(ProjectMember.objects.filter(
            project=self.project,
            user__in=[self.member, self.chair],
        ).count() == 2)

    def test_tac_formation_requires_vendor_qualification_and_ss_approval(self):
        ProjectStage.objects.filter(project=self.project).update(
            status=ProjectStage.Status.COMPLETED
        )
        qualification_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.VENDOR_QUALIFICATION,
            sequence=3,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        vendor = Vendor.objects.create(
            vendor_name="TAC eligible supplier",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        project_vendor = ProjectVendor.objects.create(
            project=self.project,
            vendor=vendor,
            participation_status="BID_RECEIVED",
            qualification_status=ProjectVendor.QualificationStatus.NOT_QUALIFIED,
        )
        payload = {
            "project": str(self.project.id),
            "committee_name": "Tender Acceptance Committee",
            "committee_type": Committee.Type.TAC,
            "chair": str(self.member.id),
            "member_ids": [str(self.member.id), str(self.level4_approver.id)],
        }
        client = APIClient()
        client.force_authenticate(self.admin)
        url = "/api/v1/workflow/committees/"
        response = client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("committee_type", response.data)

        project_vendor.qualification_status = ProjectVendor.QualificationStatus.QUALIFIED
        project_vendor.qualification_decided_by = self.admin
        project_vendor.qualification_decided_at = timezone.now()
        project_vendor.save(update_fields=[
            "qualification_status",
            "qualification_decided_by",
            "qualification_decided_at",
        ])
        invalid_payload = {**payload, "member_ids": [str(self.member.id)]}
        response = client.post(url, invalid_payload, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("member_ids", response.data)
        response = client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        committee = Committee.objects.get(id=response.data["id"])
        self.assertEqual(committee.status, "SUBMITTED")
        self.assertCountEqual(
            committee.members.values_list("user_id", flat=True),
            [self.level4_approver.id, self.member.id],
        )
        self.assertFalse(committee.members.filter(user=self.admin).exists())
        self.assertTrue(committee.members.filter(user=self.level4_approver).exists())
        formation_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FORMATION,
        )
        self.assertEqual(
            formation_stage.sequence,
            qualification_stage.sequence + 1,
        )
        self.assertEqual(
            formation_stage.status,
            ProjectStage.Status.WAITING_APPROVAL,
        )
        submission = StageSubmission.objects.get(
            committee=committee,
            submission_type=StageSubmission.Type.TAC_FORMATION,
        )
        approval = ApprovalRequest.objects.get(submission=submission)
        self.assertEqual(
            list(approval.steps.values_list("approver_role", flat=True)),
            ["SS"],
        )

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/query/",
            {"comment": "Please update the membership."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        client.force_authenticate(self.admin)
        invalid_response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "The requested membership is confirmed.",
                "committee_name": "Revised Tender Acceptance Committee",
                "chair": str(self.member.id),
                "member_ids": [str(self.member.id)],
            },
            format="json",
        )
        self.assertEqual(invalid_response.status_code, 400, invalid_response.data)
        self.assertIn("member_ids", invalid_response.data)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "The requested membership is confirmed.",
                "committee_name": "Revised Tender Acceptance Committee",
                "chair": str(self.member.id),
                "member_ids": [str(self.member.id), str(self.level4_approver.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            committee.members.count(),
            2,
        )
        self.assertFalse(committee.members.filter(user=self.admin).exists())
        self.assertTrue(committee.members.filter(user=self.level4_approver).exists())
        self.assertEqual(
            submission.approval_requests.get().events.filter(
                action=ApprovalEvent.Action.RESPONSE,
            ).count(),
            1,
        )

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/approve/",
            {"comment": "TAC formation approved."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        committee.refresh_from_db()
        self.assertEqual(committee.status, "ACTIVE")
        self.assertTrue(ProjectMember.objects.filter(
            project=self.project,
            user__in=[self.level4_approver, self.member],
        ).count() == 2)
        tac_financial_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FINANCIAL_BIDS,
        )
        self.assertEqual(
            tac_financial_stage.sequence,
            formation_stage.sequence + 1,
        )
        self.assertEqual(
            tac_financial_stage.status,
            ProjectStage.Status.NOT_STARTED,
        )
        tac_final_report_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FINAL_REPORT,
        )
        self.assertEqual(
            tac_final_report_stage.sequence,
            tac_financial_stage.sequence + 1,
        )
        self.assertEqual(
            tac_final_report_stage.status,
            ProjectStage.Status.NOT_STARTED,
        )
        tac_vendor_selection_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.VENDOR_SELECTION,
        )
        self.assertEqual(
            tac_vendor_selection_stage.sequence,
            tac_final_report_stage.sequence + 1,
        )
        self.assertEqual(
            tac_vendor_selection_stage.status,
            ProjectStage.Status.NOT_STARTED,
        )

        tender_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TENDER_DRAFT,
            sequence=tac_vendor_selection_stage.sequence + 1,
            status=ProjectStage.Status.WAITING_APPROVAL,
            created_by=self.admin,
        )
        tender_submission = StageSubmission.objects.create(
            stage=tender_stage,
            submission_type=StageSubmission.Type.TENDER_DRAFT,
            submitted_by=self.admin,
            title="Tender draft for IA Wing",
            status=StageSubmission.Status.IN_REVIEW,
        )
        tender_approval = ApprovalRequest.objects.create(
            submission=tender_submission,
            policy=self.tender_policy,
            policy_name=self.tender_policy.name,
        )
        ApprovalStep.objects.create(
            request=tender_approval,
            sequence=1,
            approver_role="IA_WING",
            status=ApprovalStep.Status.PENDING,
        )
        client.force_authenticate(self.level4_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["committee_assignments"]), 1)
        self.assertEqual(
            response.data["committee_assignments"][0]["committee_type"],
            Committee.Type.TAC,
        )
        self.assertEqual(
            response.data["committee_assignments"][0]["project_id"],
            str(self.project.id),
        )
        self.assertIn(
            str(tender_submission.id),
            {item["submission_id"] for item in response.data["pending_approvals"]},
        )
        project_response = client.get("/api/v1/projects/")
        self.assertEqual(project_response.status_code, 200, project_response.data)
        self.assertTrue(any(
            str(project["id"]) == str(self.project.id)
            for project in project_response.data["results"]
        ))

    def test_seed_command_creates_named_employees_and_50_categorized_vendors(self):
        for index in range(1, 11):
            self.make_user(
                f"committee.member{index:02d}@procurement.local",
                "USER",
            )

        call_command("seed_initial_data", verbosity=0)

        employees = User.objects.filter(employee_id__startswith="EMP-10")
        self.assertEqual(employees.count(), 10)
        self.assertEqual(employees.filter(employee_id__isnull=False).count(), 10)
        self.assertEqual(employees.values("employee_id").distinct().count(), 10)
        self.assertFalse(employees.filter(name__startswith="Committee Member").exists())
        aarav = User.objects.get(email="aarav.sharma@procurement.local")
        self.assertEqual(aarav.name, "Aarav Sharma")
        self.assertTrue(aarav.check_password("demo123"))
        self.assertGreaterEqual(
            Vendor.objects.filter(
                registration_number__startswith="DEMO-VND-2026-",
                verification_status="VERIFIED",
                is_active=True,
            ).count(),
            50,
        )
        self.assertGreaterEqual(VendorCategory.objects.count(), 10)
        self.assertEqual(
            Vendor.objects.filter(
                registration_number__startswith="DEMO-VND-2026-",
                categories__isnull=False,
            ).distinct().count(),
            50,
        )

    def test_seed_command_creates_rank_named_demo_approver_logins(self):
        legacy_ss = self.make_user("upper.level1.demo@procurement.local", "SS")
        call_command("seed_initial_data", verbosity=0)

        self.assertEqual(User.objects.get(email="ss@procurement.local").pk, legacy_ss.pk)
        self.assertFalse(User.objects.filter(email__startswith="upper.level").exists())
        for role, email, password in [
            ("SS", "ss@procurement.local", "ss123"),
            ("AS", "as@procurement.local", "as123"),
            ("DGS", "dgs@procurement.local", "dgs123"),
            ("IA_WING", "iawing@procurement.local", "ia123"),
        ]:
            user = User.objects.get(email=email)
            self.assertTrue(user.roles.filter(name=role).exists())
            self.assertTrue(user.check_password(password))
            self.assertEqual(user.verification_status, "VERIFIED")

    def test_tsc_formation_pdf_is_optional_and_available_to_level_one(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(self.project.id),
                "committee_name": "Technical Specification Committee",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [
                    str(self.member.id),
                    str(self.chair.id),
                    str(self.admin.id),
                ],
                "file": self.pdf("tsc-formation.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        submission = StageSubmission.objects.get(committee_id=response.data["id"])
        self.assertTrue(submission.file)

        client.force_authenticate(self.approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200)
        approval = next(
            item for item in response.data["pending_approvals"]
            if item["submission_id"] == str(submission.id)
        )
        self.assertEqual(
            approval["file_url"],
            f"/api/v1/workflow/submissions/{submission.id}/download/",
        )
        response = client.get(approval["file_url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF-1.4", b"".join(response.streaming_content))

        client.force_authenticate(self.level2_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["pending_approvals"], [])
        self.assertNotIn("read_only_tsc_formations", response.data)
        projects = client.get("/api/v1/projects/")
        self.assertEqual(projects.status_code, 200, projects.data)
        self.assertNotIn(
            str(self.project.id),
            {item["id"] for item in projects.data["results"]},
        )
        self.assertEqual(
            client.get(f"/api/v1/projects/{self.project.id}/").status_code,
            404,
        )
        for decision in ("approve", "query", "reject"):
            response = client.post(
                f"/api/v1/workflow/submissions/{submission.id}/{decision}/",
                {"comment": "Level 2 cannot review TSC formation."},
                format="json",
            )
            self.assertIn(response.status_code, [403, 404], response.data)

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/approve/",
            {"comment": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        client.force_authenticate(self.level2_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["pending_approvals"], [])
        self.assertNotIn("read_only_tsc_formations", response.data)
        self.assertEqual(
            client.get(f"/api/v1/projects/{self.project.id}/").status_code,
            404,
        )

        client.force_authenticate(self.outsider)
        response = client.get(approval["file_url"])
        self.assertEqual(response.status_code, 404)

    def test_tsc_chair_cannot_see_project_or_submit_report_before_ss_approves_formation(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(self.project.id),
                "committee_name": "Technical Specification Committee",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [str(self.member.id), str(self.chair.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        committee_id = response.data["id"]
        formation = StageSubmission.objects.get(committee_id=committee_id)

        client.force_authenticate(self.chair)
        projects = client.get("/api/v1/projects/")
        self.assertEqual(projects.status_code, 200, projects.data)
        self.assertNotIn(
            str(self.project.id),
            {project["id"] for project in projects.data["results"]},
        )
        self.assertEqual(client.get(f"/api/v1/projects/{self.project.id}/").status_code, 404)
        committees = client.get("/api/v1/workflow/committees/").data
        self.assertNotIn(
            committee_id,
            {
                committee["id"]
                for committee in committees.get("results", committees)
            },
        )
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(self.report_stage.id),
                "committee": committee_id,
                "submission_type": "TSC_REPORT",
                "title": "Specification report",
                "file": self.pdf(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 403, response.data)

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{formation.id}/approve/",
            {"comment": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        client.force_authenticate(self.chair)
        self.assertIn(
            str(self.project.id),
            {
                project["id"]
                for project in client.get("/api/v1/projects/").data["results"]
            },
        )
        committees = client.get("/api/v1/workflow/committees/").data
        self.assertIn(
            committee_id,
            {
                committee["id"]
                for committee in committees.get("results", committees)
            },
        )
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(self.report_stage.id),
                "committee": committee_id,
                "submission_type": "TSC_REPORT",
                "title": "Specification report",
                "file": self.pdf(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_tsc_formation_pdf_rejects_non_pdf_uploads(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(self.project.id),
                "committee_name": "Technical Specification Committee",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [str(self.member.id), str(self.chair.id)],
                "file": SimpleUploadedFile(
                    "not-a-pdf.pdf",
                    b"not a PDF file",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Committee.objects.filter(
            project=self.project,
            committee_type=Committee.Type.TSC,
        ).exists())

    def test_tsc_creation_submits_to_level_one_and_waits_for_approval(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(self.project.id),
                "committee_name": "Technical Specification Committee",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [
                    str(self.member.id),
                    str(self.chair.id),
                    str(self.admin.id),
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        committee_id = response.data["id"]
        self.assertEqual(response.data["status"], "SUBMITTED")
        admin_member = next(
            (
                item for item in response.data["members"]
                if str(item["user"]) == str(self.admin.id)
            ),
            None,
        )
        self.assertIsNotNone(admin_member, response.data)
        self.assertEqual(admin_member["name"], "Procurement Administrator")
        self.assertEqual(admin_member["employee_id"], "EMP-ADMIN-01")
        self.assertIn("ADMIN", admin_member["roles"])
        committee = Committee.objects.get(id=committee_id)
        submission = StageSubmission.objects.get(committee=committee)
        self.assertEqual(submission.submission_type, StageSubmission.Type.TSC_FORMATION)
        self.assertEqual(submission.status, StageSubmission.Status.IN_REVIEW)
        self.assertEqual(submission.revision, 1)
        self.assertEqual(
            list(submission.approval_requests.first().steps.values_list(
                "sequence", "approver_role", "status"
            )),
            [(1, "SS", ApprovalStep.Status.PENDING)],
        )
        self.assertFalse(
            ProjectMember.objects.filter(project=self.project, user=self.member).exists()
        )

        client.force_authenticate(self.approver)
        response = client.get(f"/api/v1/projects/{self.project.id}/")
        self.assertEqual(response.status_code, 200, response.data)
        response = client.get(f"/api/v1/projects/{self.project.id}/activities/")
        self.assertEqual(response.status_code, 200, response.data)
        response = client.get("/api/v1/workflow/stages/")
        self.assertIn(
            str(self.formation_stage.id),
            {stage["id"] for stage in response.data["results"]},
        )
        response = client.get("/api/v1/workflow/committees/")
        self.assertIn(committee_id, {item["id"] for item in response.data["results"]})
        response = client.get("/api/v1/workflow/submissions/")
        self.assertIn(str(submission.id), {item["id"] for item in response.data["results"]})

        client.force_authenticate(self.outsider)
        self.assertEqual(client.get(f"/api/v1/projects/{self.project.id}/").status_code, 404)

        for non_approver in (self.admin, self.super_admin):
            client.force_authenticate(non_approver)
            response = client.get("/api/v1/workflow/dashboard/")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["pending_approvals"], [])
            for decision in ("approve", "query", "reject"):
                response = client.post(
                    f"/api/v1/workflow/submissions/{submission.id}/{decision}/",
                    {"comment": "Approval must be limited to Level 1."},
                    format="json",
                )
                self.assertEqual(response.status_code, 403, response.data)

        response = client.post(
            f"/api/v1/workflow/committees/{committee_id}/submit-formation/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

        client.force_authenticate(self.member)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            self.project.id,
            [stage["project"] for stage in response.data["stages"]],
        )

        client.force_authenticate(self.approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200)
        approval = next(
            item for item in response.data["pending_approvals"]
            if item["submission_id"] == str(submission.id)
        )
        self.assertEqual(approval["project"]["title"], "Office equipment")
        self.assertEqual(
            approval["project"]["description"],
            "Procurement of office equipment for the department.",
        )
        self.assertEqual(approval["project"]["department"], "Procurement")
        self.assertEqual(approval["project"]["created_by"], self.admin.name)
        self.assertEqual(approval["committee"]["name"], "Technical Specification Committee")
        self.assertEqual(approval["committee"]["chair"]["email"], self.chair.email)
        self.assertIsNone(approval["file_url"])
        self.assertEqual(
            {member["email"] for member in approval["committee"]["members"]},
            {self.member.email, self.chair.email, self.admin.email},
        )
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/query/",
            {"comment": "Please clarify the committee's scope."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            StageSubmission.objects.get(id=submission.id).status,
            StageSubmission.Status.NEEDS_RESPONSE,
        )
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200)
        queried_approval = next(
            item for item in response.data["pending_approvals"]
            if item["submission_id"] == str(submission.id)
        )
        self.assertEqual(queried_approval["step_status"], ApprovalStep.Status.QUERY)
        self.assertEqual(
            {member["email"] for member in queried_approval["committee"]["members"]},
            {self.member.email, self.chair.email, self.admin.email},
        )

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "Only the Admin may revise a queried TSC.",
                "committee_name": "Unauthorized revision",
                "member_ids": [str(self.outsider.id)],
                "chair": str(self.outsider.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)

        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "Invalid chair selection.",
                "committee_name": "Invalid revision",
                "member_ids": [str(self.outsider.id)],
                "chair": str(self.chair.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        committee.refresh_from_db()
        self.assertEqual(committee.committee_name, "Technical Specification Committee")

        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "Updated the committee membership as requested.",
                "committee_name": "Revised Technical Specification Committee",
                "member_ids": [str(self.outsider.id), str(self.chair.id)],
                "chair": str(self.outsider.id),
                "file": self.pdf("revised-tsc-formation.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        submission.refresh_from_db()
        self.assertEqual(submission.status, StageSubmission.Status.IN_REVIEW)
        self.assertTrue(submission.file)
        committee.refresh_from_db()
        self.assertEqual(committee.committee_name, "Revised Technical Specification Committee")
        self.assertEqual(committee.chair_id, self.outsider.id)
        self.assertEqual(
            set(committee.members.values_list("user_id", flat=True)),
            {self.outsider.id, self.chair.id},
        )
        self.assertEqual(
            ApprovalStep.objects.get(request__submission=submission).status,
            ApprovalStep.Status.PENDING,
        )
        self.assertEqual(
            list(submission.approval_requests.first().events.values_list("action", flat=True)),
            [
                ApprovalEvent.Action.SUBMITTED,
                ApprovalEvent.Action.QUERY,
                ApprovalEvent.Action.RESPONSE,
            ],
        )

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/approve/",
            {"comment": "Approved"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        committee = Committee.objects.get(id=committee_id)
        self.assertEqual(committee.status, "ACTIVE")
        self.assertTrue(
            ProjectMember.objects.filter(project=self.project, user=self.outsider).exists()
        )
        self.assertEqual(
            ApprovalRequest.objects.get(submission=submission).status,
            ApprovalRequest.Status.APPROVED,
        )
        response = client.get(
            f"/api/v1/workflow/submissions/{submission.id}/download/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"%PDF-1.4", b"".join(response.streaming_content))
        response = client.get(f"/api/v1/projects/{self.project.id}/")
        self.assertEqual(response.status_code, 200, response.data)
        response = client.get("/api/v1/workflow/submissions/")
        reviewed_submission = next(
            item for item in response.data["results"] if item["id"] == str(submission.id)
        )
        self.assertEqual(
            [event["action"] for request in reviewed_submission["approval_requests"] for event in request["events"]],
            ["SUBMITTED", "QUERY", "RESPONSE", "APPROVED"],
        )

    def test_tsc_query_response_allows_no_pdf_and_rejects_invalid_pdf(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(self.project.id),
                "committee_name": "Technical Specification Committee",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [str(self.member.id), str(self.chair.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        submission = StageSubmission.objects.get(committee_id=response.data["id"])
        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/query/",
            {"comment": "Please update the membership details."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        committee = Committee.objects.get(id=submission.committee_id)
        self.assertEqual(committee.status, "SUBMITTED")

        client.force_authenticate(self.chair)
        projects = client.get("/api/v1/projects/")
        self.assertNotIn(
            str(self.project.id),
            {project["id"] for project in projects.data["results"]},
        )

        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "Attempting to attach an invalid document.",
                "committee_name": "Revised TSC",
                "member_ids": [str(self.member.id), str(self.chair.id)],
                "chair": str(self.chair.id),
                "file": SimpleUploadedFile(
                    "invalid.pdf",
                    b"not a PDF",
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        submission.refresh_from_db()
        self.assertEqual(submission.status, StageSubmission.Status.NEEDS_RESPONSE)
        self.assertFalse(submission.file)

        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/respond/",
            {
                "comment": "Updated the TSC details without an attachment.",
                "committee_name": "Revised TSC",
                "member_ids": [str(self.member.id), str(self.chair.id)],
                "chair": str(self.chair.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        submission.refresh_from_db()
        self.assertEqual(submission.status, StageSubmission.Status.IN_REVIEW)
        self.assertFalse(submission.file)
        committee.refresh_from_db()
        self.assertEqual(committee.status, "SUBMITTED")
        self.assertFalse(
            ProjectMember.objects.filter(
                project=self.project,
                user=self.chair,
            ).exists()
        )
        client.force_authenticate(self.chair)
        projects = client.get("/api/v1/projects/")
        self.assertNotIn(
            str(self.project.id),
            {project["id"] for project in projects.data["results"]},
        )

    def test_rejected_tsc_can_be_resubmitted_as_a_new_revision(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(self.project.id),
                "committee_name": "Technical Specification Committee",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [str(self.member.id), str(self.chair.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        first_committee = Committee.objects.get(id=response.data["id"])
        first_submission = StageSubmission.objects.get(committee=first_committee)

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{first_submission.id}/reject/",
            {"comment": "Please revise the membership."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        first_committee.refresh_from_db()
        self.assertEqual(first_committee.status, "REJECTED")

        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(self.project.id),
                "committee_name": "Revised Technical Specification Committee",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [str(self.member.id), str(self.chair.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        revised = StageSubmission.objects.get(committee_id=response.data["id"])
        self.assertEqual(revised.revision, 2)
        self.assertEqual(revised.supersedes_id, first_submission.id)

    def test_report_approval_policies_require_the_hq_route(self):
        expected_routes = {
            StageSubmission.Type.TSC_REPORT: ["AS", "HQ"],
            StageSubmission.Type.TEC_REPORT: ["HQ"],
        }
        invalid_routes = {
            StageSubmission.Type.TSC_REPORT: [
                {"sequence": 1, "approver_role": "SS"},
            ],
            StageSubmission.Type.TEC_REPORT: [
                {"sequence": 1, "approver_role": "AS"},
            ],
            StageSubmission.Type.TAC_FORMATION: [
                {"sequence": 1, "approver_role": "SS"},
                {"sequence": 2, "approver_role": "AS"},
            ],
            StageSubmission.Type.TSC_FORMATION: [
                {"sequence": 1, "approver_role": "SS"},
                {"sequence": 2, "approver_role": "AS"},
            ],
        }

        for submission_type, expected_roles in expected_routes.items():
            policy = ApprovalPolicy.objects.get(
                submission_type=submission_type,
                is_active=True,
            )
            self.assertEqual(
                list(policy.levels.values_list("approver_role", flat=True)),
                expected_roles,
            )

        for submission_type, levels in invalid_routes.items():
            policy = ApprovalPolicy.objects.get(
                submission_type=submission_type,
                is_active=True,
            )
            serializer = ApprovalPolicySerializer(
                instance=policy,
                data={"levels": levels},
                partial=True,
            )
            self.assertFalse(serializer.is_valid())

    def test_tsc_chair_submits_directly_to_level_two_and_history_is_retained(self):
        self.formation_stage.status = ProjectStage.Status.COMPLETED
        self.formation_stage.save(update_fields=["status"])
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Specification Committee",
            committee_type=Committee.Type.TSC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.member)
        CommitteeMember.objects.create(committee=committee, user=self.chair)

        client = APIClient()
        client.force_authenticate(self.member)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "committee": str(committee.id),
                "submission_type": "TSC_REPORT",
                "title": "Specification report",
                "comments": "First version",
                "file": self.pdf(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 403, response.data)

        client.force_authenticate(self.chair)
        downstream_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TENDER_DRAFT,
            sequence=3,
            created_by=self.admin,
        )
        self.report_stage.delete()
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "committee": str(committee.id),
                "submission_type": "TSC_REPORT",
                "title": "Specification report",
                "file": self.pdf(),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["comments"], "")
        first_submission_id = response.data["id"]
        report_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TSC_REPORT,
        )
        self.assertEqual(str(response.data["stage"]), str(report_stage.id))
        self.assertEqual(report_stage.sequence, 2)
        downstream_stage.refresh_from_db()
        self.assertEqual(downstream_stage.sequence, 3)
        self.assertEqual(report_stage.created_by_id, self.chair.id)
        self.assertTrue(response.data["file_url"].endswith(
            f"/api/v1/workflow/submissions/{first_submission_id}/download/"
        ))

        first_request = ApprovalRequest.objects.get(submission_id=first_submission_id)
        self.assertEqual(first_request.steps.count(), 2)
        self.assertEqual(first_request.steps.get(sequence=1).approver_role, "AS")
        self.assertEqual(first_request.steps.get(sequence=2).approver_role, "HQ")
        self.assertEqual(
            first_request.steps.get(sequence=1).status,
            ApprovalStep.Status.PENDING,
        )
        self.assertEqual(
            first_request.steps.get(sequence=2).status,
            ApprovalStep.Status.BLOCKED,
        )

        other_project = ProcurementProject.objects.create(
            title="Another procurement",
            description="A project awaiting TSC formation approval.",
            department=self.department,
            created_by=self.admin,
        )
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/committees/",
            {
                "project": str(other_project.id),
                "committee_name": "Another TSC",
                "committee_type": "TSC",
                "chair": str(self.chair.id),
                "member_ids": [str(self.member.id), str(self.chair.id)],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        client.force_authenticate(self.level2_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["pending_approvals"]), 1)
        report_approval = response.data["pending_approvals"][0]
        self.assertEqual(report_approval["submission_id"], first_submission_id)
        self.assertEqual(report_approval["submission_type"], "TSC_REPORT")
        self.assertEqual(report_approval["submitted_by"], self.chair.name)
        self.assertTrue(report_approval["file_url"])
        projects = client.get("/api/v1/projects/")
        self.assertEqual(projects.status_code, 200, projects.data)
        self.assertEqual(
            {item["id"] for item in projects.data["results"]},
            {str(self.project.id)},
        )
        summary = client.get("/api/v1/dashboard/summary/")
        self.assertEqual(summary.status_code, 200, summary.data)
        self.assertEqual(summary.data["total_projects"], 1)
        self.assertEqual(summary.data["pending_actions"], 1)
        self.assertEqual(
            client.get(f"/api/v1/projects/{other_project.id}/").status_code,
            404,
        )

        client.force_authenticate(self.approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{first_submission_id}/query/",
            {"comment": "Please clarify the scope."},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)

        client.force_authenticate(self.level2_approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{first_submission_id}/query/",
            {"comment": "Please clarify the scope."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            ApprovalRequest.objects.get(submission_id=first_submission_id).status,
            ApprovalRequest.Status.NEEDS_RESPONSE,
        )
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["pending_approvals"], [])
        self.assertEqual(client.get("/api/v1/projects/").data["count"], 0)
        self.assertEqual(
            client.get("/api/v1/dashboard/summary/").data["total_projects"],
            0,
        )

        client.force_authenticate(self.chair)
        response = client.post(
            f"/api/v1/workflow/submissions/{first_submission_id}/respond/",
            {"comment": "The scope is clarified in the revised report."},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("file", response.data)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "committee": str(committee.id),
                "submission_type": "TSC_REPORT",
                "title": "Specification report",
                "file": self.pdf("report-revision-without-comment.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("comments", response.data)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "committee": str(committee.id),
                "submission_type": "TSC_REPORT",
                "title": "Specification report",
                "comments": "Revised version",
                "file": self.pdf("report-revision.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["revision"], 2)
        self.assertEqual(str(response.data["supersedes"]), first_submission_id)
        self.assertEqual(
            StageSubmission.objects.get(id=first_submission_id).status,
            StageSubmission.Status.SUPERSEDED,
        )
        old_request = ApprovalRequest.objects.get(submission_id=first_submission_id)
        self.assertEqual(old_request.status, ApprovalRequest.Status.SUPERSEDED)
        self.assertEqual(
            list(old_request.events.values_list("action", flat=True)),
            [
                ApprovalEvent.Action.SUBMITTED,
                ApprovalEvent.Action.QUERY,
                ApprovalEvent.Action.RESPONSE,
                ApprovalEvent.Action.RESUBMITTED,
            ],
        )
        self.assertEqual(
            old_request.events.get(action=ApprovalEvent.Action.RESPONSE).comment,
            "Revised version",
        )
        self.assertEqual(
            old_request.events.get(action=ApprovalEvent.Action.RESUBMITTED).comment,
            "Revised TSC report submitted for approval (revision 2).",
        )

    def test_tsc_report_requires_as_then_hq_then_dgs_approval(self):
        self.formation_stage.status = ProjectStage.Status.COMPLETED
        self.formation_stage.save(update_fields=["status"])
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Specification Committee",
            committee_type=Committee.Type.TSC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.chair)
        CommitteeMember.objects.create(committee=committee, user=self.member)
        client = APIClient()

        client.force_authenticate(self.chair)
        level2_response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "committee": str(committee.id),
                "submission_type": StageSubmission.Type.TSC_REPORT,
                "title": "TSC Report",
                "file": self.pdf("level2-approved.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(level2_response.status_code, 201, level2_response.data)
        level2_submission_id = level2_response.data["id"]

        level3_payload = {
            "committee": str(committee.id),
            "submission_type": StageSubmission.Type.TSC_REPORT_LEVEL3,
            "title": "TSC Report",
            "source_report": level2_submission_id,
        }
        client.force_authenticate(self.chair)
        response = client.post(
            "/api/v1/workflow/submissions/",
            level3_payload,
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

        client.force_authenticate(self.level2_approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{level2_submission_id}/approve/",
            {"comment": "Level 2 approved."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        report_request = ApprovalRequest.objects.get(submission_id=level2_submission_id)
        self.assertEqual(report_request.status, ApprovalRequest.Status.IN_PROGRESS)
        self.assertEqual(
            report_request.steps.get(sequence=2).status,
            ApprovalStep.Status.PENDING,
        )
        client.force_authenticate(self.chair)
        response = client.post(
            "/api/v1/workflow/submissions/",
            level3_payload,
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

        client.force_authenticate(self.hq_approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{level2_submission_id}/approve/",
            {"comment": "HQ approved the TSC report."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/submissions/",
            level3_payload,
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        level3_submission_id = response.data["id"]
        self.assertEqual(str(response.data["source_report"]), level2_submission_id)
        self.assertTrue(response.data["file_url"])
        level3_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TSC_REPORT_LEVEL3,
        )
        self.assertEqual(level3_stage.sequence, self.report_stage.sequence + 1)
        self.assertEqual(
            StageSubmission.objects.get(id=level3_submission_id).file.name,
            StageSubmission.objects.get(id=level2_submission_id).file.name,
        )
        level3_request = ApprovalRequest.objects.get(submission_id=level3_submission_id)
        self.assertEqual(
            list(level3_request.steps.values_list("approver_role", flat=True)),
            ["DGS"],
        )

        client.force_authenticate(self.level2_approver)
        self.assertEqual(
            client.get("/api/v1/workflow/dashboard/").data["pending_approvals"],
            [],
        )
        self.assertEqual(
            client.post(
                f"/api/v1/workflow/submissions/{level3_submission_id}/approve/",
                {"comment": "Wrong level."},
                format="json",
            ).status_code,
            404,
        )

        client.force_authenticate(self.level3_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["submission_id"] for item in response.data["pending_approvals"]],
            [level3_submission_id],
        )
        response = client.post(
            f"/api/v1/workflow/submissions/{level3_submission_id}/query/",
            {"comment": "Clarify the technical evaluation."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)

        client.force_authenticate(self.admin)
        response = client.post(
            f"/api/v1/workflow/submissions/{level3_submission_id}/respond/",
            {"comment": "Response without a revised report."},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                **level3_payload,
                "comments": "Clarification is included in this revised report.",
                "file": self.pdf("level3-revised.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["revision"], 2)
        self.assertEqual(str(response.data["source_report"]), level2_submission_id)
        old_level3_request = ApprovalRequest.objects.get(
            submission_id=level3_submission_id
        )
        self.assertEqual(
            old_level3_request.events.get(
                action=ApprovalEvent.Action.RESPONSE
            ).comment,
            "Clarification is included in this revised report.",
        )
        revised_level3_id = response.data["id"]

        client.force_authenticate(self.level3_approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{revised_level3_id}/approve/",
            {"comment": "Level 3 approved."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            StageSubmission.objects.get(id=revised_level3_id).status,
            StageSubmission.Status.APPROVED,
        )
        self.assertTrue(ProjectStage.objects.filter(
            project=self.project,
            stage_type=ProjectStage.Type.TENDER_DRAFT,
            sequence=level3_stage.sequence + 1,
        ).exists())

    def test_tender_draft_is_reviewed_by_level_four_and_can_be_revised_after_query(self):
        expected_dates = {
            "expected_vendor_dispatch_date": "2026-12-01",
            "expected_bid_receipt_date": "2026-12-15",
            "expected_product_arrival_date": "2027-01-15",
        }
        ProjectStage.objects.filter(project=self.project).update(
            status=ProjectStage.Status.COMPLETED
        )
        level3_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TSC_REPORT_LEVEL3,
            sequence=3,
            created_by=self.admin,
        )
        tender_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TENDER_DRAFT,
            sequence=4,
            created_by=self.admin,
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        early_response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(tender_stage.id),
                "submission_type": StageSubmission.Type.TENDER_DRAFT,
                "title": "Tender draft",
                **expected_dates,
                "file": self.pdf("premature-tender-draft.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(early_response.status_code, 400, early_response.data)
        self.assertFalse(StageSubmission.objects.filter(
            stage=tender_stage,
            submission_type=StageSubmission.Type.TENDER_DRAFT,
        ).exists())
        StageSubmission.objects.create(
            stage=level3_stage,
            submission_type=StageSubmission.Type.TSC_REPORT_LEVEL3,
            submitted_by=self.chair,
            title="TSC Report — Level 3 Review",
            status=StageSubmission.Status.APPROVED,
        )
        level3_stage.status = ProjectStage.Status.COMPLETED
        level3_stage.save(update_fields=["status"])
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(tender_stage.id),
                "submission_type": StageSubmission.Type.TENDER_DRAFT,
                "title": "Tender draft",
                "file": self.pdf("missing-tender-dates.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("expected_vendor_dispatch_date", response.data)
        self.assertIn("expected_bid_receipt_date", response.data)
        self.assertIn("expected_product_arrival_date", response.data)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(tender_stage.id),
                "submission_type": StageSubmission.Type.TENDER_DRAFT,
                "title": "Tender draft",
                "expected_vendor_dispatch_date": "2026-12-20",
                "expected_bid_receipt_date": "2026-12-15",
                "expected_product_arrival_date": "2027-01-15",
                "file": self.pdf("out-of-order-tender-dates.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("expected_product_arrival_date", response.data)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(tender_stage.id),
                "submission_type": StageSubmission.Type.TENDER_DRAFT,
                "title": "Tender draft",
                **expected_dates,
                "file": self.pdf("tender-draft.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        submission_id = response.data["id"]
        self.assertEqual(response.data["comments"], "")
        for field, expected_date in expected_dates.items():
            self.assertEqual(response.data[field], expected_date)
        approval_request = ApprovalRequest.objects.get(submission_id=submission_id)
        self.assertEqual(
            list(approval_request.steps.values_list("approver_role", flat=True)),
            ["IA_WING"],
        )

        client.force_authenticate(self.level2_approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission_id}/approve/",
            {"comment": "Wrong approver."},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

        client.force_authenticate(self.level4_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["submission_id"] for item in response.data["pending_approvals"]],
            [submission_id],
        )
        response = client.post(
            f"/api/v1/workflow/submissions/{submission_id}/query/",
            {"comment": "Please clarify the delivery requirements."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(tender_stage.id),
                "submission_type": StageSubmission.Type.TENDER_DRAFT,
                "title": "Tender draft",
                "supersedes": submission_id,
                **expected_dates,
                "file": self.pdf("revised-tender-draft.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(tender_stage.id),
                "submission_type": StageSubmission.Type.TENDER_DRAFT,
                "title": "Tender draft",
                "comments": "Delivery requirements are clarified.",
                "supersedes": submission_id,
                **expected_dates,
                "file": self.pdf("revised-tender-draft.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        revised_id = response.data["id"]
        self.assertEqual(response.data["revision"], 2)
        for field, expected_date in expected_dates.items():
            self.assertEqual(response.data[field], expected_date)
        self.assertEqual(
            approval_request.events.get(action=ApprovalEvent.Action.RESPONSE).comment,
            "Delivery requirements are clarified.",
        )
        client.force_authenticate(self.level4_approver)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200, response.data)
        pending_tender = next(
            item for item in response.data["pending_approvals"]
            if item["submission_id"] == revised_id
        )
        for field, expected_date in expected_dates.items():
            self.assertEqual(str(pending_tender[field]), expected_date)

        response = client.post(
            f"/api/v1/workflow/submissions/{revised_id}/approve/",
            {"comment": "Approved."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            StageSubmission.objects.get(id=revised_id).status,
            StageSubmission.Status.APPROVED,
        )
        self.assertTrue(Tender.objects.filter(project=self.project).exists())
        self.assertEqual(
            Tender.objects.get(project=self.project).created_by,
            self.admin,
        )

    def test_tender_timeline_marks_late_dispatch_and_bid_receipt(self):
        today = timezone.localdate()
        tender_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TENDER_DRAFT,
            sequence=4,
            created_by=self.admin,
        )
        StageSubmission.objects.create(
            stage=tender_stage,
            submission_type=StageSubmission.Type.TENDER_DRAFT,
            submitted_by=self.admin,
            title="Tender draft",
            expected_vendor_dispatch_date=today - timedelta(days=2),
            expected_bid_receipt_date=today - timedelta(days=1),
            expected_product_arrival_date=today + timedelta(days=20),
            status=StageSubmission.Status.APPROVED,
        )
        tender = Tender.objects.create(
            project=self.project,
            status=Tender.Status.DISTRIBUTED,
            created_by=self.admin,
        )
        vendors = [
            Vendor.objects.create(
                vendor_name=f"Timeline supplier {index}",
                verification_status=Vendor.Status.VERIFIED,
                is_active=True,
            )
            for index in range(2)
        ]
        for vendor in vendors:
            ProjectVendor.objects.create(
                project=self.project,
                vendor=vendor,
                participation_status="TENDER_SENT",
            )

        client = APIClient()
        client.force_authenticate(self.admin)

        def timeline_milestones():
            response = client.get("/api/v1/workflow/stages/")
            self.assertEqual(response.status_code, 200, response.data)
            stage_data = next(
                item for item in response.data["results"]
                if item["id"] == str(tender_stage.id)
            )
            return {
                item["key"]: item
                for item in stage_data["timeline_milestones"]
            }

        milestones = timeline_milestones()
        self.assertEqual(milestones["VENDOR_DISPATCH"]["status"], "DELAYED")
        self.assertEqual(milestones["BID_RECEIPT"]["status"], "DELAYED")
        self.assertEqual(milestones["PRODUCT_ARRIVAL"]["status"], "NOT_TRACKED")

        received_at = timezone.now()
        for vendor in vendors:
            TenderDispatch.objects.create(
                tender=tender,
                vendor=vendor,
                recorded_by=self.admin,
                dispatched_at=received_at,
            )
            bid = VendorBid.objects.create(
                tender=tender,
                vendor=vendor,
                recorded_by=self.admin,
                received_at=received_at,
            )
            BidDocument.objects.create(
                bid=bid,
                document_type=BidDocument.Type.TECHNICAL,
                version=1,
                file=self.pdf(f"{vendor.id}-technical.pdf"),
                uploaded_by=self.admin,
            )

        milestones = timeline_milestones()
        self.assertEqual(milestones["VENDOR_DISPATCH"]["status"], "COMPLETED_LATE")
        self.assertEqual(milestones["VENDOR_DISPATCH"]["details"], "2 of 2 selected vendors dispatched.")
        self.assertEqual(milestones["BID_RECEIPT"]["status"], "COMPLETED_LATE")
        self.assertEqual(milestones["BID_RECEIPT"]["details"], "2 of 2 technical bids received.")
        self.assertEqual(milestones["PRODUCT_ARRIVAL"]["status"], "NOT_TRACKED")

    def test_admin_can_record_offline_dispatch_and_upload_technical_bid(self):
        level3_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TSC_REPORT_LEVEL3,
            sequence=3,
            created_by=self.admin,
        )
        level3_stage.status = ProjectStage.Status.COMPLETED
        level3_stage.save(update_fields=["status"])
        StageSubmission.objects.create(
            stage=level3_stage,
            submission_type=StageSubmission.Type.TSC_REPORT_LEVEL3,
            submitted_by=self.chair,
            title="TSC Report — Level 3 Review",
            status=StageSubmission.Status.APPROVED,
        )
        tender_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TENDER_DRAFT,
            sequence=4,
            created_by=self.admin,
        )
        StageSubmission.objects.create(
            stage=tender_stage,
            submission_type=StageSubmission.Type.TENDER_DRAFT,
            submitted_by=self.admin,
            title="Tender draft",
            status=StageSubmission.Status.APPROVED,
        )
        vendor = Vendor.objects.create(
            vendor_name="Verified Supplier",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        ProjectVendor.objects.create(
            project=self.project,
            vendor=vendor,
            participation_status="SELECTED",
        )
        client = APIClient()
        client.force_authenticate(self.admin)

        response = client.post(
            "/api/v1/workflow/tenders/ensure/",
            {"project": str(self.project.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        tender_id = response.data["id"]
        response = client.get(
            "/api/v1/workflow/tenders/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [tender_id],
        )

        client.force_authenticate(self.outsider)
        response = client.post(
            f"/api/v1/workflow/tenders/{tender_id}/dispatch/",
            {"vendor": str(vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)

        client.force_authenticate(self.admin)
        unselected_vendor = Vendor.objects.create(
            vendor_name="Not Selected Supplier",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        response = client.post(
            f"/api/v1/workflow/tenders/{tender_id}/dispatch/",
            {"vendor": str(unselected_vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        response = client.post(
            f"/api/v1/workflow/tenders/{tender_id}/dispatch/",
            {"vendor": str(vendor.id), "method": "OFFLINE"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["vendor_name"], vendor.vendor_name)
        self.assertIsNotNone(response.data["dispatched_at"])
        self.assertEqual(
            ProjectVendor.objects.get(project=self.project, vendor=vendor).participation_status,
            "TENDER_SENT",
        )
        response = client.delete(
            f"/api/v1/projects/{self.project.id}/vendors/",
            {"vendor_id": str(vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)

        response = client.post(
            "/api/v1/workflow/bids/receive/",
            {
                "tender": tender_id,
                "vendor": str(vendor.id),
                "technical_file": self.pdf("technical-bid.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Evaluation Committee",
            committee_type=Committee.Type.TEC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.chair)
        CommitteeMember.objects.create(committee=committee, user=self.member)
        response = client.post(
            "/api/v1/workflow/bids/receive/",
            {
                "tender": tender_id,
                "vendor": str(vendor.id),
                "technical_file": self.pdf("technical-bid.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertCountEqual(
            [document["document_type"] for document in response.data["documents"]],
            ["TECHNICAL"],
        )
        self.assertEqual(
            ProjectVendor.objects.get(project=self.project, vendor=vendor).participation_status,
            "BID_RECEIVED",
        )
        response = client.get(
            "/api/v1/workflow/bids/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [str(item["vendor"]) for item in response.data["results"]],
            [str(vendor.id)],
        )
        client.force_authenticate(self.member)
        response = client.get(
            "/api/v1/workflow/bids/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [document["document_type"] for document in response.data["results"][0]["documents"]],
            ["TECHNICAL"],
        )

        client.force_authenticate(self.outsider)
        response = client.post(
            "/api/v1/workflow/bids/receive/",
            {
                "tender": tender_id,
                "vendor": str(vendor.id),
                "technical_file": self.pdf("technical-bid.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 403, response.data)

    def test_vendor_match_ranks_verified_vendors_by_products_and_categories(self):
        category = VendorCategory.objects.create(
            name="Office equipment",
            description="Printers, scanners, and document imaging devices.",
        )
        matching = Vendor.objects.create(
            vendor_name="Central Imaging Supplies",
            products_services="Industrial printers and high-volume scanners",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        matching.categories.add(category)
        Vendor.objects.create(
            vendor_name="Unrelated supplier",
            products_services="Catering and food service",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        Vendor.objects.create(
            vendor_name="Unverified printer vendor",
            products_services="Printers and scanners",
            verification_status=Vendor.Status.PENDING,
            is_active=True,
        )
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/vendors/match/",
            {"query": "industrial printer"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([result["id"] for result in response.data], [str(matching.id)])
        self.assertGreater(response.data[0]["similarity_score"], 0)
        self.assertEqual(response.data[0]["matched_terms"], ["industrial", "printer"])

    def test_dashboard_excludes_projects_without_membership(self):
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Specification Committee",
            committee_type=Committee.Type.TSC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.member)
        client = APIClient()
        client.force_authenticate(self.member)
        response = client.get("/api/v1/workflow/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            self.project.id,
            [stage["project"] for stage in response.data["stages"]],
        )
        response = client.get("/api/v1/workflow/bids/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_tsc_members_can_share_and_download_work_documents(self):
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Specification Committee",
            committee_type=Committee.Type.TSC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.member)
        CommitteeMember.objects.create(committee=committee, user=self.chair)

        client = APIClient()
        client.force_authenticate(self.member)
        response = client.post(
            "/api/v1/workflow/tsc-documents/",
            {"committee": str(committee.id), "file": self.pdf("working-notes.pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        document_id = response.data["id"]
        self.assertEqual(response.data["uploaded_by_name"], self.member.name)
        self.assertEqual(response.data["version"], 1)
        self.assertEqual(TSCWorkDocument.objects.count(), 1)
        response = client.post(
            "/api/v1/workflow/tsc-documents/",
            {"committee": str(committee.id), "file": self.pdf("working-notes-revised.pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["version"], 2)

        client.force_authenticate(self.chair)
        response = client.get("/api/v1/workflow/tsc-documents/")
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            [document["version"] for document in response.data["results"]],
            [1, 2],
        )
        response = client.get(f"/api/v1/workflow/tsc-documents/{document_id}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

        client.force_authenticate(self.outsider)
        response = client.get(f"/api/v1/workflow/tsc-documents/{document_id}/download/")
        self.assertEqual(response.status_code, 404)
        response = client.post(
            "/api/v1/workflow/tsc-documents/",
            {"committee": str(committee.id), "file": self.pdf("outsider.pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403, response.data)

    def test_tec_final_report_requires_hq_approval_with_query_response_history(self):
        ProjectStage.objects.filter(project=self.project).update(
            status=ProjectStage.Status.COMPLETED
        )
        tec_formation_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TEC_FORMATION,
            sequence=3,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        tender = Tender.objects.create(
            project=self.project,
            status=Tender.Status.DISTRIBUTED,
            created_by=self.admin,
        )
        vendors = [
            Vendor.objects.create(
                vendor_name=f"TEC report supplier {index}",
                verification_status=Vendor.Status.VERIFIED,
                is_active=True,
            )
            for index in range(2)
        ]
        for vendor in vendors:
            ProjectVendor.objects.create(
                project=self.project,
                vendor=vendor,
                participation_status="TENDER_SENT",
            )
            TenderDispatch.objects.create(
                tender=tender,
                vendor=vendor,
                recorded_by=self.admin,
                dispatched_at=timezone.now(),
            )
        bid = VendorBid.objects.create(
            tender=tender,
            vendor=vendors[0],
            recorded_by=self.admin,
            received_at=timezone.now(),
        )
        BidDocument.objects.create(
            bid=bid,
            document_type=BidDocument.Type.TECHNICAL,
            version=1,
            file=self.pdf("supplier-one-technical.pdf"),
            uploaded_by=self.admin,
        )
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Evaluation Committee",
            committee_type=Committee.Type.TEC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.member)
        CommitteeMember.objects.create(committee=committee, user=self.chair)
        ProjectMember.objects.create(
            project=self.project,
            user=self.member,
            assigned_by=self.admin,
        )

        client = APIClient()
        client.force_authenticate(self.member)
        response = client.get(f"/api/v1/projects/{self.project.id}/vendors/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["vendors"]), len(vendors))
        response = client.post(
            "/api/v1/workflow/tec-documents/",
            {
                "committee": str(committee.id),
                "document_type": TECWorkDocument.Type.WORKING,
                "file": self.pdf("working-report.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        working_document_id = response.data["id"]
        response = client.post(
            "/api/v1/workflow/tec-documents/",
            {
                "committee": str(committee.id),
                "document_type": TECWorkDocument.Type.FINAL,
                "file": self.pdf("not-the-chair.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(ProjectStage.objects.filter(
            project=self.project,
            stage_type=ProjectStage.Type.TEC_REPORT,
        ).exists())

        client.force_authenticate(self.chair)
        response = client.post(
            "/api/v1/workflow/tec-documents/",
            {
                "committee": str(committee.id),
                "document_type": TECWorkDocument.Type.FINAL,
                "file": self.pdf("final-report-too-early.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("document_type", response.data)

        second_bid = VendorBid.objects.create(
            tender=tender,
            vendor=vendors[1],
            recorded_by=self.admin,
            received_at=timezone.now(),
        )
        BidDocument.objects.create(
            bid=second_bid,
            document_type=BidDocument.Type.TECHNICAL,
            version=1,
            file=self.pdf("supplier-two-technical.pdf"),
            uploaded_by=self.admin,
        )
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "committee": str(committee.id),
                "submission_type": StageSubmission.Type.TEC_REPORT,
                "title": "TEC Final Report",
                "file": self.pdf("final-tec-report.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            response.data["submission_type"],
            StageSubmission.Type.TEC_REPORT,
        )
        report_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TEC_REPORT,
        )
        self.assertEqual(report_stage.status, ProjectStage.Status.WAITING_APPROVAL)
        self.assertEqual(report_stage.sequence, tec_formation_stage.sequence + 1)
        self.assertEqual(str(response.data["stage"]), str(report_stage.id))
        final_document = TECWorkDocument.objects.get(
            committee=committee,
            document_type=TECWorkDocument.Type.FINAL,
        )
        final_document_id = str(final_document.id)
        submission = StageSubmission.objects.get(
            committee=committee,
            submission_type=StageSubmission.Type.TEC_REPORT,
        )
        self.assertEqual(
            submission.approval_requests.get().steps.get().approver_role,
            "HQ",
        )

        client.force_authenticate(self.hq_approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{submission.id}/query/",
            {"comment": "Please clarify the evaluation findings."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        submission.refresh_from_db()
        report_stage.refresh_from_db()
        self.assertEqual(submission.status, StageSubmission.Status.NEEDS_RESPONSE)
        self.assertEqual(report_stage.status, ProjectStage.Status.NEEDS_REVISION)

        client.force_authenticate(self.chair)
        response = client.post(
            "/api/v1/workflow/submissions/",
            {
                "stage": str(report_stage.id),
                "committee": str(committee.id),
                "submission_type": StageSubmission.Type.TEC_REPORT,
                "title": "TEC Final Report",
                "comments": "Clarified the evaluation findings.",
                "file": self.pdf("revised-final-tec-report.pdf"),
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        revised_submission = StageSubmission.objects.get(
            committee=committee,
            submission_type=StageSubmission.Type.TEC_REPORT,
            revision=2,
        )
        self.assertTrue(
            submission.approval_requests.get().events.filter(
                action=ApprovalEvent.Action.RESPONSE,
                comment="Clarified the evaluation findings.",
            ).exists()
        )

        client.force_authenticate(self.hq_approver)
        response = client.post(
            f"/api/v1/workflow/submissions/{revised_submission.id}/approve/",
            {"comment": "Approved."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        report_stage.refresh_from_db()
        self.assertEqual(report_stage.status, ProjectStage.Status.COMPLETED)

        client.force_authenticate(self.admin)
        response = client.get(
            "/api/v1/workflow/tec-documents/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        expected_document_ids = {
            str(working_document_id),
            str(final_document_id),
        } | {
            str(document_id)
            for document_id in TECWorkDocument.objects.filter(
                committee=committee,
                document_type=TECWorkDocument.Type.FINAL,
            ).values_list("id", flat=True)
        }
        self.assertEqual(
            {document["id"] for document in response.data["results"]},
            expected_document_ids,
        )
        response = client.get(
            f"/api/v1/workflow/tec-documents/{final_document_id}/download/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

        client.force_authenticate(self.outsider)
        self.assertEqual(
            client.get(
                f"/api/v1/workflow/tec-documents/{final_document_id}/download/"
            ).status_code,
            404,
        )

    def test_bid_files_are_visible_only_to_admin_and_active_tec_members(self):
        vendor = Vendor.objects.create(
            vendor_name="Verified Supplier",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        tender = Tender.objects.create(
            project=self.project,
            reference="T-2026-01",
            status=Tender.Status.DISTRIBUTED,
            created_by=self.admin,
        )
        bid = VendorBid.objects.create(
            tender=tender,
            vendor=vendor,
            recorded_by=self.admin,
            received_at=timezone.now(),
        )
        document = BidDocument.objects.create(
            bid=bid,
            document_type=BidDocument.Type.TECHNICAL,
            version=1,
            file=self.pdf("technical.pdf"),
            uploaded_by=self.admin,
        )
        financial_document = BidDocument.objects.create(
            bid=bid,
            document_type=BidDocument.Type.FINANCIAL,
            version=1,
            file=self.pdf("financial.pdf"),
            uploaded_by=self.admin,
        )
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Evaluation Committee",
            committee_type=Committee.Type.TEC,
            chair=self.member,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.member)

        client = APIClient()
        client.force_authenticate(self.member)
        response = client.get(f"/api/v1/workflow/bids/{bid.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["document_type"] for item in response.data["documents"]],
            ["TECHNICAL"],
        )
        file_url = response.data["documents"][0]["file_url"]
        self.assertIn(f"/workflow/bids/{bid.id}/documents/{document.id}/download/", file_url)
        response = client.get(file_url.replace("http://testserver", ""))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            client.get(
                f"/api/v1/workflow/bids/{bid.id}/documents/{financial_document.id}/download/"
            ).status_code,
            404,
        )

        client.force_authenticate(self.admin)
        response = client.get(f"/api/v1/workflow/bids/{bid.id}/")
        self.assertCountEqual(
            [item["document_type"] for item in response.data["documents"]],
            ["TECHNICAL", "FINANCIAL"],
        )
        client.force_authenticate(self.outsider)
        self.assertEqual(client.get(f"/api/v1/workflow/bids/{bid.id}/").status_code, 404)
        self.assertEqual(client.get(file_url.replace("http://testserver", "")).status_code, 404)

    def test_admin_shortlists_three_qualified_vendors_and_tac_can_review_financial_bids(self):
        tec_committee = Committee.objects.create(
            project=self.project,
            committee_name="Technical Evaluation Committee",
            committee_type=Committee.Type.TEC,
            chair=self.member,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=tec_committee, user=self.member)
        final_report = TECWorkDocument.objects.create(
            committee=tec_committee,
            document_type=TECWorkDocument.Type.FINAL,
            version=1,
            file=self.pdf("tec-final-report.pdf"),
            uploaded_by=self.member,
        )
        ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TEC_REPORT,
            sequence=3,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.VENDOR_QUALIFICATION,
            sequence=4,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        ProjectStage.objects.filter(project=self.project).update(
            status=ProjectStage.Status.COMPLETED,
        )
        ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FORMATION,
            sequence=5,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        tender = Tender.objects.create(
            project=self.project,
            status=Tender.Status.DISTRIBUTED,
            created_by=self.admin,
        )
        vendors = [
            Vendor.objects.create(
                vendor_name=f"TEC-ranked supplier {index}",
                verification_status=Vendor.Status.VERIFIED,
                is_active=True,
            )
            for index in range(4)
        ]
        bids = []
        for vendor in vendors:
            ProjectVendor.objects.create(
                project=self.project,
                vendor=vendor,
                participation_status="BID_RECEIVED",
                qualification_status=ProjectVendor.QualificationStatus.QUALIFIED,
                qualification_decided_by=self.admin,
                qualification_decided_at=timezone.now(),
            )
            bid = VendorBid.objects.create(
                tender=tender,
                vendor=vendor,
                recorded_by=self.admin,
                received_at=timezone.now(),
            )
            BidDocument.objects.create(
                bid=bid,
                document_type=BidDocument.Type.TECHNICAL,
                version=1,
                file=self.pdf(f"{vendor.id}-technical.pdf"),
                uploaded_by=self.admin,
            )
            bids.append(bid)
        tac = Committee.objects.create(
            project=self.project,
            committee_name="Tender Acceptance Committee",
            committee_type=Committee.Type.TAC,
            chair=self.level4_approver,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=tac, user=self.level4_approver)
        url = "/api/v1/workflow/tac-shortlist/select/"
        client = APIClient()
        client.force_authenticate(self.admin)
        too_few = {
            "project": str(self.project.id),
            "vendor_ids": [str(vendors[0].id), str(vendors[1].id)],
        }
        response = client.post(url, too_few, format="multipart")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("vendor_ids", response.data)
        missing_financial = {
            "project": str(self.project.id),
            "vendor_ids": [str(vendor.id) for vendor in vendors[:3]],
        }
        response = client.post(url, missing_financial, format="multipart")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(TACVendorShortlist.objects.filter(committee=tac).exists())
        payload = {
            "project": str(self.project.id),
            "vendor_ids": [str(vendor.id) for vendor in vendors[:3]],
        }
        payload.update({
            f"financial_file_{vendor.id}": self.pdf(f"{vendor.id}-financial.pdf")
            for vendor in vendors[:3]
        })
        response = client.post(url, payload, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data), 3)
        self.assertEqual(TACVendorShortlist.objects.filter(committee=tac).count(), 3)
        shortlist_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FINANCIAL_BIDS,
        )
        self.assertEqual(shortlist_stage.status, ProjectStage.Status.COMPLETED)
        self.assertFalse(ProjectStage.objects.filter(
            project=self.project,
            stage_type=ProjectStage.Type.VENDOR_SELECTION,
        ).exists())
        self.assertFalse(TACVendorShortlist.objects.filter(
            committee=tac,
            vendor=vendors[3],
        ).exists())

        client.force_authenticate(self.level4_approver)
        response = client.get(
            "/api/v1/workflow/tac-shortlist/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["results"]), 3)
        self.assertTrue(all(
            item["financial_document"]["document_type"] == BidDocument.Type.FINANCIAL
            for item in response.data["results"]
        ))
        response = client.get(
            "/api/v1/workflow/tec-documents/",
            {"project": str(self.project.id)},
        )
        self.assertIn(
            str(final_report.id),
            {item["id"] for item in response.data["results"]},
        )
        response = client.get(
            "/api/v1/workflow/bids/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(len(response.data["results"]), 3)
        tac_bid = next(
            item for item in response.data["results"]
            if str(item["vendor"]) == str(vendors[0].id)
        )
        self.assertCountEqual(
            [item["document_type"] for item in tac_bid["documents"]],
            [BidDocument.Type.TECHNICAL, BidDocument.Type.FINANCIAL],
        )
        financial_document = TACVendorShortlist.objects.get(
            committee=tac,
            vendor=vendors[0],
        ).financial_document
        response = client.get(
            f"/api/v1/workflow/bids/{tac_bid['id']}/documents/{financial_document.id}/download/"
        )
        self.assertEqual(response.status_code, 200)

        client.force_authenticate(self.member)
        response = client.get(f"/api/v1/workflow/bids/{bids[0].id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["document_type"] for item in response.data["documents"]],
            [BidDocument.Type.TECHNICAL],
        )
        self.assertEqual(
            client.get(
                f"/api/v1/workflow/bids/{bids[0].id}/documents/{financial_document.id}/download/"
            ).status_code,
            404,
        )
        client.force_authenticate(self.outsider)
        response = client.get(
            "/api/v1/workflow/tac-shortlist/",
            {"project": str(self.project.id)},
        )
        self.assertEqual(response.data["results"], [])

    def test_tac_chair_submits_final_report_for_admin_after_financial_bids(self):
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Tender Acceptance Committee",
            committee_type=Committee.Type.TAC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.chair)
        CommitteeMember.objects.create(committee=committee, user=self.member)
        ProjectStage.objects.filter(project=self.project).update(
            status=ProjectStage.Status.COMPLETED,
        )
        formation_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FORMATION,
            sequence=3,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        financial_bids_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FINANCIAL_BIDS,
            sequence=formation_stage.sequence + 1,
            status=ProjectStage.Status.IN_PROGRESS,
            created_by=self.admin,
        )
        client = APIClient()
        endpoint = "/api/v1/workflow/tac-documents/"
        client.force_authenticate(self.chair)
        response = client.post(
            endpoint,
            {"committee": str(committee.id), "file": self.pdf("early-tac-report.pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(TACWorkDocument.objects.filter(committee=committee).exists())

        client.force_authenticate(self.member)
        response = client.post(
            endpoint,
            {"committee": str(committee.id), "file": self.pdf("not-chair-tac-report.pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403, response.data)

        financial_bids_stage.status = ProjectStage.Status.COMPLETED
        financial_bids_stage.save(update_fields=["status"])
        client.force_authenticate(self.chair)
        response = client.post(
            endpoint,
            {"committee": str(committee.id), "file": self.pdf("final-tac-report.pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        document_id = response.data["id"]
        report_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FINAL_REPORT,
        )
        self.assertEqual(report_stage.status, ProjectStage.Status.COMPLETED)
        self.assertEqual(report_stage.sequence, financial_bids_stage.sequence + 1)

        client.force_authenticate(self.member)
        response = client.get(endpoint, {"project": str(self.project.id)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["results"]), 1)

        client.force_authenticate(self.admin)
        response = client.get(endpoint, {"project": str(self.project.id)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            [document["id"] for document in response.data["results"]],
            [document_id],
        )
        response = client.get(f"{endpoint}{document_id}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

        client.force_authenticate(self.outsider)
        self.assertEqual(
            client.get(endpoint, {"project": str(self.project.id)}).data["results"],
            [],
        )
        self.assertEqual(
            client.get(f"{endpoint}{document_id}/download/").status_code,
            404,
        )

    def test_admin_selects_final_vendor_only_from_shortlist_after_tac_report(self):
        committee = Committee.objects.create(
            project=self.project,
            committee_name="Tender Acceptance Committee",
            committee_type=Committee.Type.TAC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        CommitteeMember.objects.create(committee=committee, user=self.chair)
        CommitteeMember.objects.create(committee=committee, user=self.member)
        ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FINANCIAL_BIDS,
            sequence=3,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        report_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TAC_FINAL_REPORT,
            sequence=4,
            created_by=self.admin,
        )
        selection_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.VENDOR_SELECTION,
            sequence=5,
            created_by=self.admin,
        )
        vendor = Vendor.objects.create(
            vendor_name="Shortlisted supplier",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        other_vendor = Vendor.objects.create(
            vendor_name="Not shortlisted supplier",
            verification_status=Vendor.Status.VERIFIED,
            is_active=True,
        )
        tender = Tender.objects.create(project=self.project, created_by=self.admin)
        bid = VendorBid.objects.create(
            tender=tender,
            vendor=vendor,
            recorded_by=self.admin,
            received_at=timezone.now(),
        )
        financial_document = BidDocument.objects.create(
            bid=bid,
            document_type=BidDocument.Type.FINANCIAL,
            version=1,
            file=self.pdf("shortlisted-financial.pdf"),
            uploaded_by=self.admin,
        )
        TACVendorShortlist.objects.create(
            committee=committee,
            vendor=vendor,
            financial_document=financial_document,
            selected_by=self.admin,
        )
        TACWorkDocument.objects.create(
            committee=committee,
            version=1,
            file=self.pdf("final-tac-report.pdf"),
            uploaded_by=self.chair,
        )
        endpoint = "/api/v1/workflow/tac-shortlist/final-selection/"
        client = APIClient()

        client.force_authenticate(self.admin)
        response = client.post(
            endpoint,
            {"project": str(self.project.id), "vendor": str(vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

        report_stage.status = ProjectStage.Status.COMPLETED
        report_stage.save(update_fields=["status"])
        client.force_authenticate(self.member)
        response = client.post(
            endpoint,
            {"project": str(self.project.id), "vendor": str(vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.data)

        client.force_authenticate(self.admin)
        response = client.post(
            endpoint,
            {"project": str(self.project.id), "vendor": str(other_vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        response = client.post(
            endpoint,
            {"project": str(self.project.id), "vendor": str(vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["vendor_name"], vendor.vendor_name)
        self.assertEqual(
            VendorSelection.objects.get(committee=committee).vendor,
            vendor,
        )
        selection_stage.refresh_from_db()
        self.assertEqual(selection_stage.status, ProjectStage.Status.COMPLETED)
        self.assertTrue(
            AuditLog.objects.filter(
                user=self.admin,
                operation="SELECT_FINAL_VENDOR",
            ).exists()
        )
        self.assertTrue(
            self.project.activities.filter(
                message__contains="selected Shortlisted supplier as the final vendor"
            ).exists()
        )

        response = client.post(
            endpoint,
            {"project": str(self.project.id), "vendor": str(vendor.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        client.force_authenticate(self.chair)
        response = client.get(endpoint, {"project": str(self.project.id)})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(str(response.data["vendor"]), str(vendor.id))
        client.force_authenticate(self.outsider)
        self.assertEqual(
            client.get(endpoint, {"project": str(self.project.id)}).status_code,
            403,
        )

    def test_admin_shortlists_all_eligible_vendors_when_fewer_than_three(self):
        project = ProcurementProject.objects.create(
            title="Small supplier pool",
            description="Procurement with two qualified vendors.",
            department=self.department,
            created_by=self.admin,
        )
        tec = Committee.objects.create(
            project=project,
            committee_name="Technical Evaluation Committee",
            committee_type=Committee.Type.TEC,
            chair=self.member,
            formed_by=self.admin,
            status="ACTIVE",
        )
        TECWorkDocument.objects.create(
            committee=tec,
            document_type=TECWorkDocument.Type.FINAL,
            version=1,
            file=self.pdf("small-pool-tec-report.pdf"),
            uploaded_by=self.member,
        )
        for sequence, stage_type in enumerate(
            (
                ProjectStage.Type.TEC_REPORT,
                ProjectStage.Type.VENDOR_QUALIFICATION,
                ProjectStage.Type.TAC_FORMATION,
            ),
            start=1,
        ):
            ProjectStage.objects.create(
                project=project,
                stage_type=stage_type,
                sequence=sequence,
                status=ProjectStage.Status.COMPLETED,
                created_by=self.admin,
            )
        tender = Tender.objects.create(project=project, created_by=self.admin)
        vendors = [
            Vendor.objects.create(
                vendor_name=f"Small-pool supplier {index}",
                verification_status=Vendor.Status.VERIFIED,
                is_active=True,
            )
            for index in range(2)
        ]
        for vendor in vendors:
            ProjectVendor.objects.create(
                project=project,
                vendor=vendor,
                participation_status="BID_RECEIVED",
                qualification_status=ProjectVendor.QualificationStatus.QUALIFIED,
                qualification_decided_by=self.admin,
                qualification_decided_at=timezone.now(),
            )
            bid = VendorBid.objects.create(
                tender=tender,
                vendor=vendor,
                recorded_by=self.admin,
                received_at=timezone.now(),
            )
            BidDocument.objects.create(
                bid=bid,
                document_type=BidDocument.Type.TECHNICAL,
                version=1,
                file=self.pdf(f"{vendor.id}-small-pool-technical.pdf"),
                uploaded_by=self.admin,
            )
        tac = Committee.objects.create(
            project=project,
            committee_name="Tender Acceptance Committee",
            committee_type=Committee.Type.TAC,
            chair=self.member,
            formed_by=self.admin,
            status="ACTIVE",
        )
        payload = {
            "project": str(project.id),
            "vendor_ids": [str(vendor.id) for vendor in vendors],
        }
        payload.update({
            f"financial_file_{vendor.id}": self.pdf(f"{vendor.id}-financial.pdf")
            for vendor in vendors
        })
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/v1/workflow/tac-shortlist/select/",
            payload,
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data), 2)
        self.assertEqual(
            {str(item["vendor"]) for item in response.data},
            {str(vendor.id) for vendor in vendors},
        )
        self.assertEqual(
            ProjectStage.objects.get(
                project=project,
                stage_type=ProjectStage.Type.TAC_FINANCIAL_BIDS,
            ).status,
            ProjectStage.Status.COMPLETED,
        )

    def test_admin_qualifies_bid_vendors_after_tec_final_report(self):
        vendors = [
            Vendor.objects.create(
                vendor_name=name,
                verification_status=Vendor.Status.VERIFIED,
                is_active=True,
            )
            for name in ("Qualified Supplier", "Other Supplier")
        ]
        for vendor in vendors:
            ProjectVendor.objects.create(
                project=self.project,
                vendor=vendor,
                participation_status="TENDER_SENT",
            )
        client = APIClient()
        client.force_authenticate(self.admin)
        url = f"/api/v1/projects/{self.project.id}/qualified-vendors/"

        response = client.get(url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["can_qualify"])
        response = client.post(
            url,
            {"vendor_ids": [str(vendors[0].id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

        tender = Tender.objects.create(project=self.project, created_by=self.admin)
        for vendor in vendors:
            bid = VendorBid.objects.create(
                tender=tender,
                vendor=vendor,
                recorded_by=self.admin,
                received_at=timezone.now(),
            )
            BidDocument.objects.create(
                bid=bid,
                document_type=BidDocument.Type.TECHNICAL,
                version=1,
                file=self.pdf("technical-bid.pdf"),
                uploaded_by=self.admin,
            )
        tec = Committee.objects.create(
            project=self.project,
            committee_name="Technical Evaluation Committee",
            committee_type=Committee.Type.TEC,
            chair=self.chair,
            formed_by=self.admin,
            status="ACTIVE",
        )
        report_stage = ProjectStage.objects.create(
            project=self.project,
            stage_type=ProjectStage.Type.TEC_REPORT,
            sequence=6,
            status=ProjectStage.Status.COMPLETED,
            created_by=self.admin,
        )
        TECWorkDocument.objects.create(
            committee=tec,
            document_type=TECWorkDocument.Type.FINAL,
            version=1,
            file=self.pdf("tec-final.pdf"),
            uploaded_by=self.chair,
        )

        response = client.post(
            url,
            {"vendor_ids": [str(vendors[0].id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["qualification_complete"])
        qualified = ProjectVendor.objects.get(project=self.project, vendor=vendors[0])
        not_qualified = ProjectVendor.objects.get(project=self.project, vendor=vendors[1])
        self.assertEqual(
            qualified.qualification_status,
            ProjectVendor.QualificationStatus.QUALIFIED,
        )
        self.assertEqual(
            not_qualified.qualification_status,
            ProjectVendor.QualificationStatus.NOT_QUALIFIED,
        )
        self.assertEqual(not_qualified.qualification_decided_by, self.admin)
        self.assertIsNotNone(not_qualified.qualification_decided_at)
        qualification_stage = ProjectStage.objects.get(
            project=self.project,
            stage_type=ProjectStage.Type.VENDOR_QUALIFICATION,
        )
        self.assertEqual(qualification_stage.sequence, report_stage.sequence + 1)
        self.assertEqual(qualification_stage.status, ProjectStage.Status.COMPLETED)
        self.assertTrue(AuditLog.objects.filter(
            entity_type="vendor_qualification",
            entity_id=str(self.project.id),
            user=self.admin,
        ).exists())
        response = client.post(
            url,
            {"vendor_ids": [str(vendors[1].id)]},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        qualified.refresh_from_db()
        self.assertEqual(
            qualified.qualification_status,
            ProjectVendor.QualificationStatus.QUALIFIED,
        )

    def test_non_admin_cannot_read_vendor_qualification(self):
        client = APIClient()
        client.force_authenticate(self.outsider)
        response = client.get(
            f"/api/v1/projects/{self.project.id}/qualified-vendors/"
        )
        self.assertEqual(response.status_code, 404)
