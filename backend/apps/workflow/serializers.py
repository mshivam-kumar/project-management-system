from rest_framework import serializers
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import has_any_role
from apps.committees.models import Committee, CommitteeMember
from apps.procurement.models import ProcurementProject
from apps.vendors.models import ProjectVendor, Vendor
from .models import (
    ApprovalEvent,
    ApprovalPolicy,
    ApprovalPolicyLevel,
    ApprovalRequest,
    ApprovalStep,
    BidDocument,
    NegotiationMessage,
    ProjectStage,
    StageSubmission,
    TACWorkDocument,
    Tender,
    TenderDispatch,
    TECWorkDocument,
    TSCWorkDocument,
    TACVendorShortlist,
    VendorBid,
    VendorSelection,
)

def validate_pdf_upload(value):
    if value.size > 10 * 1024 * 1024:
        raise serializers.ValidationError("PDF files must be 10 MB or smaller.")
    if not value.name.lower().endswith(".pdf") or value.content_type != "application/pdf":
        raise serializers.ValidationError("Only PDF files are accepted.")
    if value.read(5) != b"%PDF-":
        raise serializers.ValidationError("The uploaded file is not a valid PDF.")
    value.seek(0)
    return value


class ProjectStageSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="project.project_code", read_only=True)
    timeline_milestones = serializers.SerializerMethodField()

    class Meta:
        model = ProjectStage
        fields = [
            "id", "project", "project_code", "stage_type", "sequence", "status",
            "planned_start", "due_date", "actual_start", "completed_at", "created_at",
            "timeline_milestones",
        ]
        read_only_fields = ["id", "status", "actual_start", "completed_at", "created_at"]

    def get_timeline_milestones(self, stage):
        if stage.stage_type != ProjectStage.Type.TENDER_DRAFT:
            return []

        submission = stage.submissions.filter(
            submission_type=StageSubmission.Type.TENDER_DRAFT,
        ).order_by("-revision").first()
        if not submission:
            return []

        milestone_specs = [
            (
                "VENDOR_DISPATCH",
                "Vendor dispatch",
                submission.expected_vendor_dispatch_date,
            ),
            (
                "BID_RECEIPT",
                "Bid receipt",
                submission.expected_bid_receipt_date,
            ),
            (
                "PRODUCT_ARRIVAL",
                "Expected product arrival",
                submission.expected_product_arrival_date,
            ),
        ]
        if submission.status != StageSubmission.Status.APPROVED:
            status = (
                "AWAITING_APPROVAL"
                if submission.status == StageSubmission.Status.IN_REVIEW
                else "AWAITING_REVISION"
            )
            return [
                {
                    "key": key,
                    "title": title,
                    "due_date": due_date,
                    "status": (
                        "NOT_TRACKED" if key == "PRODUCT_ARRIVAL" else status
                    ),
                    "completed_at": None,
                    "details": (
                        "Product delivery is outside the current workflow."
                        if key == "PRODUCT_ARRIVAL"
                        else "Milestone tracking starts after tender approval."
                    ),
                }
                for key, title, due_date in milestone_specs
            ]

        selected_vendor_ids = list(
            ProjectVendor.objects.filter(
                project_id=stage.project_id,
                participation_status__in=["SELECTED", "TENDER_SENT", "BID_RECEIVED"],
            ).values_list("vendor_id", flat=True)
        )
        tender = Tender.objects.filter(project_id=stage.project_id).first()
        dispatch_dates = {}
        bid_dates = {}
        if tender and selected_vendor_ids:
            for vendor_id, dispatched_at in TenderDispatch.objects.filter(
                tender=tender,
                vendor_id__in=selected_vendor_ids,
            ).values_list("vendor_id", "dispatched_at"):
                dispatch_dates[vendor_id] = max(
                    dispatched_at,
                    dispatch_dates.get(vendor_id, dispatched_at),
                )
            for vendor_id, received_at in VendorBid.objects.filter(
                tender=tender,
                vendor_id__in=selected_vendor_ids,
                status=VendorBid.Status.RECEIVED,
                documents__document_type=BidDocument.Type.TECHNICAL,
            ).values_list("vendor_id", "received_at").distinct():
                bid_dates[vendor_id] = max(
                    received_at,
                    bid_dates.get(vendor_id, received_at),
                )

        today = timezone.localdate()

        def milestone_status(due_date, actual_dates, total, not_tracked=False):
            if not_tracked:
                return "NOT_TRACKED", None
            complete = total > 0 and len(actual_dates) == total
            actual_at = max(actual_dates.values()) if complete else None
            if actual_at:
                actual_date = timezone.localtime(actual_at).date()
                return (
                    "COMPLETED_LATE" if due_date and actual_date > due_date else "COMPLETED",
                    timezone.localtime(actual_at).isoformat(),
                )
            if due_date and today > due_date:
                return "DELAYED", None
            return (
                "IN_PROGRESS" if actual_dates else "NOT_STARTED",
                None,
            )

        vendor_total = len(selected_vendor_ids)
        dispatch_status, dispatch_completed_at = milestone_status(
            submission.expected_vendor_dispatch_date,
            dispatch_dates,
            vendor_total,
        )
        bid_status, bid_completed_at = milestone_status(
            submission.expected_bid_receipt_date,
            bid_dates,
            vendor_total,
        )
        return [
            {
                "key": "VENDOR_DISPATCH",
                "title": "Vendor dispatch",
                "due_date": submission.expected_vendor_dispatch_date,
                "status": dispatch_status,
                "completed_at": dispatch_completed_at,
                "details": f"{len(dispatch_dates)} of {vendor_total} selected vendors dispatched.",
            },
            {
                "key": "BID_RECEIPT",
                "title": "Bid receipt",
                "due_date": submission.expected_bid_receipt_date,
                "status": bid_status,
                "completed_at": bid_completed_at,
                "details": f"{len(bid_dates)} of {vendor_total} technical bids received.",
            },
            {
                "key": "PRODUCT_ARRIVAL",
                "title": "Expected product arrival",
                "due_date": submission.expected_product_arrival_date,
                "status": "NOT_TRACKED",
                "completed_at": None,
                "details": "Product delivery is outside the current workflow.",
            },
        ]

    def validate(self, attrs):
        start = attrs.get("planned_start", getattr(self.instance, "planned_start", None))
        due = attrs.get("due_date", getattr(self.instance, "due_date", None))
        if start and due and due < start:
            raise serializers.ValidationError(
                {"due_date": "The due date cannot be earlier than the planned start."}
            )
        return attrs


class CommitteeMemberSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.name", read_only=True)
    employee_id = serializers.CharField(source="user.employee_id", read_only=True, default="")
    email = serializers.EmailField(source="user.email", read_only=True)
    designation = serializers.CharField(source="user.designation", read_only=True, default="")
    roles = serializers.SlugRelatedField(
        source="user.roles",
        many=True,
        read_only=True,
        slug_field="name",
    )

    class Meta:
        model = CommitteeMember
        fields = [
            "id", "user", "name", "employee_id", "email", "designation", "roles",
            "assigned_at",
        ]
        read_only_fields = ["id", "assigned_at"]


class CommitteeSerializer(serializers.ModelSerializer):
    member_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True
    )
    members = CommitteeMemberSerializer(many=True, read_only=True)
    chair_name = serializers.CharField(source="chair.name", read_only=True, default="")
    chair_employee_id = serializers.CharField(source="chair.employee_id", read_only=True, default="")
    project_code = serializers.CharField(source="project.project_code", read_only=True)

    class Meta:
        model = Committee
        fields = [
            "id", "project", "project_code", "committee_name", "committee_type",
            "chair", "chair_name", "chair_employee_id", "formed_by", "formed_at", "status",
            "member_ids", "members",
        ]
        read_only_fields = ["id", "formed_by", "formed_at", "status"]

    def create(self, validated_data):
        validated_data.pop("member_ids", None)
        return Committee.objects.create(**validated_data)

    def validate_member_ids(self, member_ids):
        if not member_ids:
            raise serializers.ValidationError("Select at least one committee member.")
        if len(member_ids) != len(set(member_ids)):
            raise serializers.ValidationError("A user can only be added once.")
        users = User.objects.filter(
            id__in=member_ids, is_active=True, verification_status="VERIFIED"
        )
        if users.count() != len(member_ids):
            raise serializers.ValidationError("All members must be active, verified users.")
        return member_ids

    def validate(self, attrs):
        member_ids = attrs.get("member_ids", [])
        chair = attrs.get("chair")
        if chair and member_ids and chair.id not in member_ids:
            raise serializers.ValidationError({"chair": "The chair must be a committee member."})
        return attrs


def _required_approval_roles(submission_type):
    return {
        StageSubmission.Type.TSC_REPORT: ["AS", "HQ"],
        StageSubmission.Type.TSC_REPORT_LEVEL3: ["DGS"],
        StageSubmission.Type.TEC_REPORT: ["HQ"],
        StageSubmission.Type.TENDER_DRAFT: ["IA_WING"],
    }.get(submission_type)


class ApprovalPolicyLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalPolicyLevel
        fields = ["id", "policy", "sequence", "approver_role", "approver"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        role = attrs.get("approver_role", "")
        approver = attrs.get("approver")
        policy = attrs.get("policy", getattr(self.instance, "policy", None))
        if bool(role) == bool(approver):
            raise serializers.ValidationError(
                "Set exactly one of approver_role or approver."
            )
        formation_types = {
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
            StageSubmission.Type.TAC_FORMATION,
        }
        if policy and policy.submission_type in formation_types:
            if role != "SS" or approver:
                raise serializers.ValidationError(
                    "Committee formation approval must be assigned to the SS role."
                )
            if not self.instance and policy.levels.exists():
                raise serializers.ValidationError(
                    "Committee formation can have only one approval level."
                )
        expected_report_roles = (
            _required_approval_roles(policy.submission_type) if policy else None
        )
        if expected_report_roles:
            sequence = attrs.get(
                "sequence",
                self.instance.sequence if self.instance else None,
            )
            expected_report_role = (
                expected_report_roles[sequence - 1]
                if sequence and sequence <= len(expected_report_roles)
                else None
            )
            if role != expected_report_role or approver:
                raise serializers.ValidationError(
                    f"{policy.get_submission_type_display()} approval level {sequence} "
                    f"must be assigned to the {expected_report_role or 'required'} role."
                )
        if approver and (not approver.is_active or approver.verification_status != "VERIFIED"):
            raise serializers.ValidationError(
                {"approver": "The assigned approver must be active and verified."}
            )
        return attrs


class ApprovalPolicySerializer(serializers.ModelSerializer):
    levels = serializers.ListField(child=serializers.DictField(), write_only=True, required=True)
    approval_levels = ApprovalPolicyLevelSerializer(many=True, read_only=True, source="levels")

    class Meta:
        model = ApprovalPolicy
        fields = [
            "id", "name", "submission_type", "is_active", "created_by",
            "created_at", "levels", "approval_levels",
        ]
        read_only_fields = ["id", "created_by", "created_at"]

    def validate_levels(self, levels):
        if not levels:
            raise serializers.ValidationError("Configure at least one approval level.")
        expected = 1
        for level in levels:
            if level.get("sequence") != expected:
                raise serializers.ValidationError(
                    "Approval levels must use contiguous sequences starting at 1."
                )
            role = level.get("approver_role", "")
            approver_id = level.get("approver")
            if bool(role) == bool(approver_id):
                raise serializers.ValidationError(
                    f"Level {expected} must specify exactly one role or user."
                )
            if approver_id:
                try:
                    approver = User.objects.get(
                        id=approver_id,
                        is_active=True,
                        verification_status="VERIFIED",
                    )
                except (User.DoesNotExist, ValueError, TypeError):
                    raise serializers.ValidationError(
                        f"Level {expected} must assign an active, verified user."
                    )
            expected += 1
        return levels

    def validate(self, attrs):
        submission_type = attrs.get(
            "submission_type",
            getattr(self.instance, "submission_type", None),
        )
        levels = attrs.get("levels")
        if submission_type in {
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
            StageSubmission.Type.TAC_FORMATION,
        }:
            if levels is None and self.instance:
                levels = list(self.instance.levels.values(
                    "sequence", "approver_role", "approver_id"
                ))
            if (
                levels is None
                or len(levels) != 1
                or levels[0].get("approver_role") != "SS"
                or levels[0].get("approver", levels[0].get("approver_id"))
            ):
                raise serializers.ValidationError({
                    "levels": (
                        "Committee formation must have exactly one approval level assigned "
                        "to the SS role."
                    )
                })
        expected_report_roles = _required_approval_roles(submission_type)
        if expected_report_roles:
            if levels is None and self.instance:
                levels = list(self.instance.levels.values(
                    "sequence", "approver_role", "approver_id"
                ))
            if (
                levels is None
                or len(levels) != len(expected_report_roles)
                or any(
                    level.get("sequence") != sequence
                    or level.get("approver_role") != expected_role
                    or level.get("approver", level.get("approver_id"))
                    for sequence, (level, expected_role) in enumerate(
                        zip(levels, expected_report_roles),
                        start=1,
                    )
                )
            ):
                raise serializers.ValidationError({
                    "levels": (
                        f"{dict(StageSubmission.Type.choices).get(submission_type)} must use "
                        f"the approval sequence {' -> '.join(expected_report_roles)}."
                    )
                })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        levels = validated_data.pop("levels")
        policy = ApprovalPolicy.objects.create(**validated_data)
        ApprovalPolicyLevel.objects.bulk_create([
            ApprovalPolicyLevel(
                policy=policy,
                sequence=level["sequence"],
                approver_role=level.get("approver_role", ""),
                approver_id=level.get("approver"),
            )
            for level in levels
        ])
        return policy

    def update(self, instance, validated_data):
        if instance.requests.exists():
            raise serializers.ValidationError(
                "A policy used by submitted work cannot be modified; create a new policy instead."
            )
        validated_data.pop("levels", None)
        return super().update(instance, validated_data)


class ApprovalStepSerializer(serializers.ModelSerializer):
    assigned_user_name = serializers.CharField(
        source="assigned_user.name", read_only=True, default=""
    )

    class Meta:
        model = ApprovalStep
        fields = [
            "id", "sequence", "approver_role", "assigned_user",
            "assigned_user_name", "status",
        ]


class ApprovalEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.name", read_only=True)

    class Meta:
        model = ApprovalEvent
        fields = ["id", "step", "actor", "actor_name", "action", "comment", "created_at"]


class ApprovalRequestSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    events = ApprovalEventSerializer(many=True, read_only=True)

    class Meta:
        model = ApprovalRequest
        fields = ["id", "policy_name", "status", "supersedes", "created_at", "closed_at", "steps", "events"]


class StageSubmissionSerializer(serializers.ModelSerializer):
    stage = serializers.PrimaryKeyRelatedField(
        queryset=ProjectStage.objects.all(),
        required=False,
    )
    submitted_by_name = serializers.CharField(source="submitted_by.name", read_only=True)
    source_report = serializers.PrimaryKeyRelatedField(
        queryset=StageSubmission.objects.all(),
        required=False,
        allow_null=True,
    )
    approval_requests = ApprovalRequestSerializer(many=True, read_only=True)
    file_url = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True, required=False)
    expected_vendor_dispatch_date = serializers.DateField(
        required=False, allow_null=True,
    )
    expected_bid_receipt_date = serializers.DateField(
        required=False, allow_null=True,
    )
    expected_product_arrival_date = serializers.DateField(
        required=False, allow_null=True,
    )

    class Meta:
        model = StageSubmission
        validators = []
        fields = [
            "id", "stage", "committee", "submission_type", "revision", "supersedes",
            "submitted_by", "submitted_by_name", "source_report", "title", "comments", "file",
            "expected_vendor_dispatch_date", "expected_bid_receipt_date",
            "expected_product_arrival_date",
            "file_url", "status", "created_at", "approval_requests",
        ]
        read_only_fields = ["id", "revision", "submitted_by", "status", "created_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if not obj.file:
            return None
        url = f"/api/v1/workflow/submissions/{obj.id}/download/"
        return request.build_absolute_uri(url) if request else url

    def validate_file(self, value):
        return validate_pdf_upload(value)

    def validate(self, attrs):
        submission_type = attrs.get("submission_type")
        tender_dates = (
            "expected_vendor_dispatch_date",
            "expected_bid_receipt_date",
            "expected_product_arrival_date",
        )
        if submission_type == StageSubmission.Type.TENDER_DRAFT:
            missing_dates = [
                field for field in tender_dates
                if attrs.get(field) is None
            ]
            if missing_dates:
                raise serializers.ValidationError({
                    field: "This expected date is required for tender draft approval."
                    for field in missing_dates
                })
            if not (
                attrs["expected_vendor_dispatch_date"]
                <= attrs["expected_bid_receipt_date"]
                <= attrs["expected_product_arrival_date"]
            ):
                raise serializers.ValidationError({
                    "expected_product_arrival_date": (
                        "Expected dates must follow this order: vendor dispatch, "
                        "bid receipt, then product arrival."
                    )
                })
        elif any(attrs.get(field) is not None for field in tender_dates):
            raise serializers.ValidationError({
                field: "Expected tender dates are only valid for a tender draft."
                for field in tender_dates
                if attrs.get(field) is not None
            })
        requires_file = submission_type in {
            StageSubmission.Type.TSC_REPORT,
            StageSubmission.Type.TEC_REPORT,
            StageSubmission.Type.TENDER_DRAFT,
        }
        if submission_type == StageSubmission.Type.TSC_REPORT_LEVEL3:
            requires_file = not attrs.get("source_report") or bool(attrs.get("supersedes"))
        if requires_file and not attrs.get("file"):
            raise serializers.ValidationError({"file": "A PDF file is required for this submission."})
        stage = attrs.get("stage")
        if stage and submission_type and stage.stage_type != submission_type:
            raise serializers.ValidationError(
                {"stage": "The stage type must match the submission type."}
            )
        if not stage and submission_type not in {
            StageSubmission.Type.TSC_REPORT,
            StageSubmission.Type.TSC_REPORT_LEVEL3,
            StageSubmission.Type.TEC_REPORT,
        }:
            raise serializers.ValidationError({"stage": "A project stage is required."})
        return attrs


class TenderDispatchSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.vendor_name", read_only=True)

    class Meta:
        model = TenderDispatch
        fields = [
            "id", "vendor", "vendor_name", "recorded_by", "method",
            "reference", "notes", "dispatched_at",
        ]
        read_only_fields = ["id", "recorded_by", "dispatched_at"]


class TenderEnsureSerializer(serializers.Serializer):
    project = serializers.PrimaryKeyRelatedField(queryset=ProcurementProject.objects.all())


class VendorBidReceiptSerializer(serializers.Serializer):
    tender = serializers.PrimaryKeyRelatedField(queryset=Tender.objects.all())
    vendor = serializers.PrimaryKeyRelatedField(queryset=Vendor.objects.all())
    technical_file = serializers.FileField()
    financial_file = serializers.FileField(required=False)

    def validate_technical_file(self, value):
        return validate_pdf_upload(value)

    def validate_financial_file(self, value):
        return validate_pdf_upload(value)


class TenderSerializer(serializers.ModelSerializer):
    dispatches = TenderDispatchSerializer(many=True, read_only=True)
    project_code = serializers.CharField(source="project.project_code", read_only=True)

    class Meta:
        model = Tender
        fields = [
            "id", "project", "project_code", "reference", "status",
            "bid_due_at", "created_by", "created_at", "dispatches",
        ]
        read_only_fields = ["id", "status", "created_by", "created_at"]


class BidDocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = BidDocument
        fields = ["id", "document_type", "version", "file", "file_url", "uploaded_by", "uploaded_at"]
        read_only_fields = ["id", "version", "uploaded_by", "uploaded_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        url = f"/api/v1/workflow/bids/{obj.bid_id}/documents/{obj.id}/download/"
        return request.build_absolute_uri(url) if request else url

    def validate_file(self, value):
        return validate_pdf_upload(value)


class TSCWorkDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.name", read_only=True)
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True)

    class Meta:
        model = TSCWorkDocument
        fields = ["id", "committee", "version", "file", "file_name", "file_url", "uploaded_by", "uploaded_by_name", "uploaded_at"]
        read_only_fields = ["id", "version", "uploaded_by", "uploaded_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        url = f"/api/v1/workflow/tsc-documents/{obj.id}/download/"
        return request.build_absolute_uri(url) if request else url

    def get_file_name(self, obj):
        return obj.file.name.rsplit("/", 1)[-1]

    def validate_file(self, value):
        return validate_pdf_upload(value)

class TECWorkDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.name", read_only=True)
    committee_name = serializers.CharField(source="committee.committee_name", read_only=True)
    project_code = serializers.CharField(source="committee.project.project_code", read_only=True)
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True)

    class Meta:
        model = TECWorkDocument
        fields = [
            "id", "committee", "committee_name", "project_code", "document_type",
            "version", "file", "file_name", "file_url", "uploaded_by",
            "uploaded_by_name", "uploaded_at",
        ]
        read_only_fields = ["id", "version", "uploaded_by", "uploaded_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        url = f"/api/v1/workflow/tec-documents/{obj.id}/download/"
        return request.build_absolute_uri(url) if request else url

    def get_file_name(self, obj):
        return obj.file.name.rsplit("/", 1)[-1]

    def validate_file(self, value):
        return validate_pdf_upload(value)

class TACWorkDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.name", read_only=True)
    committee_name = serializers.CharField(source="committee.committee_name", read_only=True)
    project_code = serializers.CharField(source="committee.project.project_code", read_only=True)
    file_url = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()
    file = serializers.FileField(write_only=True)

    class Meta:
        model = TACWorkDocument
        fields = [
            "id", "committee", "committee_name", "project_code", "version",
            "file", "file_name", "file_url", "uploaded_by", "uploaded_by_name",
            "uploaded_at",
        ]
        read_only_fields = ["id", "version", "uploaded_by", "uploaded_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        url = f"/api/v1/workflow/tac-documents/{obj.id}/download/"
        return request.build_absolute_uri(url) if request else url

    def get_file_name(self, obj):
        return obj.file.name.rsplit("/", 1)[-1]

    def validate_file(self, value):
        return validate_pdf_upload(value)


class VendorBidSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.vendor_name", read_only=True)
    documents = serializers.SerializerMethodField()

    class Meta:
        model = VendorBid
        fields = [
            "id", "tender", "vendor", "vendor_name", "recorded_by",
            "received_at", "status", "created_at", "documents",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    def get_documents(self, obj):
        documents = obj.documents.all()
        request = self.context.get("request")
        if request and not has_any_role(request.user, "ADMIN", "SUPER_ADMIN"):
            is_shortlisted_tac_member = TACVendorShortlist.objects.filter(
                committee__project=obj.tender.project,
                committee__committee_type=Committee.Type.TAC,
                committee__status="ACTIVE",
                committee__members__user=request.user,
                vendor=obj.vendor,
            ).exists()
            if not is_shortlisted_tac_member:
                documents = documents.filter(document_type=BidDocument.Type.TECHNICAL)
        return BidDocumentSerializer(
            documents,
            many=True,
            context=self.context,
        ).data


class TACVendorShortlistSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.vendor_name", read_only=True)
    financial_document = BidDocumentSerializer(read_only=True)
    selected_by_name = serializers.CharField(source="selected_by.name", read_only=True)

    class Meta:
        model = TACVendorShortlist
        fields = [
            "id", "committee", "vendor", "vendor_name", "financial_document",
            "selected_by", "selected_by_name", "selected_at",
        ]
        read_only_fields = fields


class VendorSelectionSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.vendor_name", read_only=True, default="")
    selected_by_name = serializers.CharField(source="selected_by.name", read_only=True, default="")

    class Meta:
        model = VendorSelection
        fields = [
            "id", "committee", "vendor", "vendor_name", "selected_by",
            "selected_by_name", "round_number", "status", "decided_at",
        ]


class NegotiationMessageSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(source="recorded_by.name", read_only=True)

    class Meta:
        model = NegotiationMessage
        fields = [
            "id", "project", "vendor", "direction", "message",
            "external_reference", "recorded_by", "recorded_by_name", "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]
        extra_kwargs = {"message": {"allow_blank": False}}
