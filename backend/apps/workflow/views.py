from uuid import UUID

from django.db import models, transaction
from django.db.models import Max
from django.http import FileResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import has_any_role
from apps.audit.models import AuditLog
from apps.committees.models import Committee, CommitteeMember
from apps.notifications.models import Notification
from apps.procurement.models import ProjectActivity, ProjectMember, ProcurementProject
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
    TACVendorShortlist,
    TACWorkDocument,
    Tender,
    TenderDispatch,
    TECWorkDocument,
    TSCWorkDocument,
    VendorBid,
    VendorSelection,
)
from .serializers import (
    ApprovalEventSerializer,
    ApprovalPolicyLevelSerializer,
    ApprovalPolicySerializer,
    ApprovalRequestSerializer,
    BidDocumentSerializer,
    CommitteeSerializer,
    NegotiationMessageSerializer,
    ProjectStageSerializer,
    StageSubmissionSerializer,
    TACVendorShortlistSerializer,
    TACWorkDocumentSerializer,
    TenderDispatchSerializer,
    TenderEnsureSerializer,
    TenderSerializer,
    TECWorkDocumentSerializer,
    TSCWorkDocumentSerializer,
    VendorBidReceiptSerializer,
    VendorBidSerializer,
    VendorSelectionSerializer,
)


def _is_admin(user):
    return has_any_role(user, "ADMIN", "SUPER_ADMIN")


def _require_admin(user):
    if not _is_admin(user):
        raise PermissionDenied("Administrator access is required.")


def _project_is_visible(project, user):
    if _is_admin(user) or project.created_by_id == user.id:
        return True
    is_project_member = (
        ProjectMember.objects.filter(project=project, user=user).exists()
        or CommitteeMember.objects.filter(
            committee__project=project,
            committee__status="ACTIVE",
            user=user,
        ).exists()
    )
    if is_project_member:
        return True
    review_types = []
    if has_any_role(user, "SS"):
        review_types.extend([
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
            StageSubmission.Type.TAC_FORMATION,
        ])
    if has_any_role(user, "AS"):
        review_types.append(StageSubmission.Type.TSC_REPORT)
    if has_any_role(user, "HQ"):
        review_types.extend([
            StageSubmission.Type.TSC_REPORT,
            StageSubmission.Type.TEC_REPORT,
        ])
    if has_any_role(user, "DGS"):
        review_types.append(StageSubmission.Type.TSC_REPORT_LEVEL3)
    if has_any_role(user, "IA_WING"):
        review_types.append(StageSubmission.Type.TENDER_DRAFT)
    has_pending_review = ApprovalStep.objects.filter(
        request__submission__stage__project=project,
        request__submission__submission_type__in=review_types,
        status__in=[ApprovalStep.Status.PENDING, ApprovalStep.Status.QUERY],
    ).filter(
        models.Q(assigned_user=user)
        | models.Q(approver_role__in=user.roles.values_list("name", flat=True))
    ).exists()
    has_reviewed_submission = ApprovalEvent.objects.filter(
        request__submission__stage__project=project,
        request__submission__submission_type__in=review_types,
        request__status__in=[
            ApprovalRequest.Status.APPROVED,
            ApprovalRequest.Status.REJECTED,
        ],
        actor=user,
    ).exists()
    return has_pending_review or has_reviewed_submission


def _projects_visible_to_approver(user):
    review_types = []
    if has_any_role(user, "SS"):
        review_types.extend([
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
            StageSubmission.Type.TAC_FORMATION,
        ])
    if has_any_role(user, "AS"):
        review_types.append(StageSubmission.Type.TSC_REPORT)
    if has_any_role(user, "HQ"):
        review_types.extend([
            StageSubmission.Type.TSC_REPORT,
            StageSubmission.Type.TEC_REPORT,
        ])
    if has_any_role(user, "DGS"):
        review_types.append(StageSubmission.Type.TSC_REPORT_LEVEL3)
    if has_any_role(user, "IA_WING"):
        review_types.append(StageSubmission.Type.TENDER_DRAFT)
    if review_types:
        review_filter = models.Q(
            workflow_stages__submissions__approval_requests__steps__status=ApprovalStep.Status.PENDING,
        )
        if has_any_role(user, "SS"):
            review_filter |= models.Q(
                workflow_stages__submissions__submission_type__in=[
                    StageSubmission.Type.TSC_FORMATION,
                    StageSubmission.Type.TEC_FORMATION,
                    StageSubmission.Type.TAC_FORMATION,
                ],
                workflow_stages__submissions__approval_requests__steps__status=ApprovalStep.Status.QUERY,
            )
        return ProcurementProject.objects.filter(
            workflow_stages__submissions__submission_type__in=review_types,
        ).filter(review_filter).filter(
            models.Q(
                workflow_stages__submissions__approval_requests__steps__assigned_user=user
            )
            | models.Q(
                workflow_stages__submissions__approval_requests__steps__approver_role__in=
                user.roles.values_list("name", flat=True)
            )
        ).values("id")
    pending_projects = ProcurementProject.objects.filter(
        workflow_stages__submissions__approval_requests__steps__status__in=[
            ApprovalStep.Status.PENDING,
            ApprovalStep.Status.QUERY,
        ],
    ).filter(
        models.Q(
            workflow_stages__submissions__approval_requests__steps__assigned_user=user
        )
        | models.Q(
            workflow_stages__submissions__approval_requests__steps__approver_role__in=
            user.roles.values_list("name", flat=True)
        )
    ).values("id")
    reviewed_projects = ProcurementProject.objects.filter(
        workflow_stages__submissions__approval_requests__events__actor=user
    ).values("id")
    return ProcurementProject.objects.filter(
        models.Q(id__in=pending_projects) | models.Q(id__in=reviewed_projects)
    ).values("id")


def _is_committee_member(committee, user):
    return CommitteeMember.objects.filter(committee=committee, user=user).exists()


def _get_active_policy(submission_type):
    policy = ApprovalPolicy.objects.filter(
        submission_type=submission_type, is_active=True
    ).prefetch_related("levels").first()
    if not policy or not policy.levels.exists():
        raise ValidationError(
            {"approval_policy": f"No active approval policy is configured for {submission_type}."}
        )
    return policy


def _latest_tender_draft(project):
    return StageSubmission.objects.filter(
        stage__project=project,
        submission_type=StageSubmission.Type.TENDER_DRAFT,
    ).order_by("-revision").first()


def _latest_tsc_level3_report(project):
    return StageSubmission.objects.filter(
        stage__project=project,
        submission_type=StageSubmission.Type.TSC_REPORT_LEVEL3,
    ).order_by("-revision").first()


def _ensure_tender_for_approved_draft(project, submitted_by):
    latest_level3_report = _latest_tsc_level3_report(project)
    if not latest_level3_report or latest_level3_report.status != StageSubmission.Status.APPROVED:
        raise ValidationError({
            "tsc_report_level3": "DGS must approve the latest TSC report before tendering."
        })
    latest_submission = _latest_tender_draft(project)
    if not latest_submission or latest_submission.status != StageSubmission.Status.APPROVED:
        raise ValidationError({
            "tender_draft": "The latest tender draft must be approved before vendor dispatch."
        })
    tender, created = Tender.objects.get_or_create(
        project=project,
        defaults={
            "created_by": submitted_by,
            "status": Tender.Status.APPROVED,
        },
    )
    if not created and tender.status == Tender.Status.DRAFT:
        tender.status = Tender.Status.APPROVED
        tender.save(update_fields=["status"])
    return tender


def _validate_committee_formation_policy(policy):
    levels = list(policy.levels.all())
    if (
        len(levels) != 1
        or levels[0].approver_role != "SS"
        or levels[0].approver_id
    ):
        raise ValidationError({
            "approval_policy": (
                "Committee formation must have exactly one approver level: SS."
            )
        })


def _validate_single_role_policy(policy, approver_role):
    _validate_role_policy(policy, [approver_role])


def _validate_role_policy(policy, approver_roles):
    levels = list(policy.levels.all())
    if (
        [level.approver_role for level in levels] != approver_roles
        or any(level.approver_id for level in levels)
    ):
        raise ValidationError({
            "approval_policy": (
                "This submission type must use the approval sequence "
                f"{' -> '.join(approver_roles)}."
            )
        })


def _create_submission(submission, user):
    policy = _get_active_policy(submission.submission_type)
    if submission.submission_type in {
        StageSubmission.Type.TSC_FORMATION,
        StageSubmission.Type.TEC_FORMATION,
        StageSubmission.Type.TAC_FORMATION,
    }:
        _validate_committee_formation_policy(policy)
    if submission.submission_type == StageSubmission.Type.TSC_REPORT:
        _validate_role_policy(policy, ["AS", "HQ"])
    if submission.submission_type == StageSubmission.Type.TSC_REPORT_LEVEL3:
        _validate_single_role_policy(policy, "DGS")
    if submission.submission_type == StageSubmission.Type.TEC_REPORT:
        _validate_single_role_policy(policy, "HQ")
    if submission.submission_type == StageSubmission.Type.TENDER_DRAFT:
        _validate_single_role_policy(policy, "IA_WING")
    request = ApprovalRequest.objects.create(
        submission=submission,
        policy=policy,
        policy_name=policy.name,
        supersedes=(
            submission.supersedes.approval_requests.order_by("-created_at").first()
            if submission.supersedes_id else None
        ),
    )
    steps = []
    sequence = 1
    for level in policy.levels.all():
        steps.append(ApprovalStep(
            request=request,
            sequence=sequence,
            approver_role=level.approver_role,
            assigned_user=level.approver,
            status=ApprovalStep.Status.PENDING if sequence == 1 else ApprovalStep.Status.BLOCKED,
        ))
        sequence += 1
    ApprovalStep.objects.bulk_create(steps)
    first_step = next(step for step in steps if step.status == ApprovalStep.Status.PENDING)
    ApprovalEvent.objects.create(
        request=request,
        step=first_step,
        actor=user,
        action=ApprovalEvent.Action.SUBMITTED,
        comment=submission.comments,
    )
    if first_step.assigned_user_id:
        approvers = [first_step.assigned_user]
    elif first_step.approver_role:
        approvers = User.objects.filter(
            roles__name=first_step.approver_role,
            is_active=True,
            verification_status="VERIFIED",
        ).distinct()
    else:
        approvers = []
    for approver in approvers:
        Notification.objects.create(
            recipient=approver,
            project=submission.stage.project,
            title="Approval required",
            message=f"{submission.title} is awaiting your approval.",
        )
    submission.status = StageSubmission.Status.IN_REVIEW
    submission.save(update_fields=["status"])
    submission.stage.status = ProjectStage.Status.WAITING_APPROVAL
    if not submission.stage.actual_start:
        submission.stage.actual_start = timezone.now()
    submission.stage.save(update_fields=["status", "actual_start"])
    return request


def _validate_stage_is_ready(stage):
    unfinished = ProjectStage.objects.filter(
        project=stage.project,
        sequence__lt=stage.sequence,
    ).exclude(status__in=[
        ProjectStage.Status.COMPLETED, ProjectStage.Status.CANCELLED
    ]).exists()
    if unfinished:
        raise ValidationError(
            {"stage": "Complete or cancel all earlier project stages before submitting this stage."}
        )


def _get_or_create_stage_after(project, user, stage_type, previous_stage_type):
    stage = ProjectStage.objects.filter(
        project=project,
        stage_type=stage_type,
    ).first()
    if stage:
        return stage

    previous_sequence = ProjectStage.objects.filter(
        project=project,
        stage_type=previous_stage_type,
    ).values_list("sequence", flat=True).first()
    sequence = previous_sequence + 1 if previous_sequence else 1
    occupied = ProjectStage.objects.filter(
        project=project,
        sequence=sequence,
    ).exists()
    if occupied:
        max_sequence = ProjectStage.objects.filter(
            project=project,
        ).aggregate(max_sequence=Max("sequence"))["max_sequence"] or 0
        offset = max_sequence + 1
        later_stages = ProjectStage.objects.filter(
            project=project,
            sequence__gte=sequence,
        )
        later_stages.update(sequence=models.F("sequence") + offset)
        later_stages.update(sequence=models.F("sequence") - offset + 1)

    return ProjectStage.objects.create(
        project=project,
        stage_type=stage_type,
        sequence=sequence,
        created_by=user,
    )


def _get_or_create_tsc_report_stage(
    project,
    user,
    stage_type=ProjectStage.Type.TSC_REPORT,
):
    previous_stage_type = (
        ProjectStage.Type.TSC_REPORT
        if stage_type == ProjectStage.Type.TSC_REPORT_LEVEL3
        else ProjectStage.Type.TSC_FORMATION
    )
    return _get_or_create_stage_after(
        project,
        user,
        stage_type,
        previous_stage_type,
    )


def _can_act_on_step(step, user):
    if step.assigned_user_id:
        return step.assigned_user_id == user.id
    if step.approver_role:
        return user.roles.filter(name=step.approver_role).exists()
    return False


def _active_step(request):
    return request.steps.filter(status__in=[
        ApprovalStep.Status.PENDING, ApprovalStep.Status.QUERY
    ]).order_by("sequence").first()


class ProjectStageViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectStageSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = ProjectStage.objects.select_related("project")
        if _is_admin(self.request.user):
            return queryset
        return queryset.filter(
            models.Q(project__created_by=self.request.user)
            | models.Q(project__members__user=self.request.user)
            | models.Q(
                project__committees__status="ACTIVE",
                project__committees__members__user=self.request.user,
            )
            | models.Q(project_id__in=_projects_visible_to_approver(self.request.user))
        ).distinct()

    def perform_create(self, serializer):
        _require_admin(self.request.user)
        project = serializer.validated_data["project"]
        if ProjectStage.objects.filter(
            project=project, stage_type=serializer.validated_data["stage_type"]
        ).exists():
            raise ValidationError({"stage_type": "This project stage already exists."})
        serializer.save(created_by=self.request.user)
        AuditLog.objects.create(
            user=self.request.user,
            entity_type="project_stage",
            entity_id=str(serializer.instance.id),
            operation="CREATE",
            new_values={"stage_type": serializer.instance.stage_type},
        )

    def perform_update(self, serializer):
        _require_admin(self.request.user)
        stage = serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            entity_type="project_stage",
            entity_id=str(stage.id),
            operation="UPDATE",
            new_values={"due_date": str(stage.due_date) if stage.due_date else None},
        )


class CommitteeViewSet(viewsets.ModelViewSet):
    serializer_class = CommitteeSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = Committee.objects.select_related("project", "chair").prefetch_related(
            "members__user__roles"
        )
        if _is_admin(self.request.user):
            return queryset
        return queryset.filter(
            models.Q(project__created_by=self.request.user)
            | models.Q(project__members__user=self.request.user)
            | models.Q(status="ACTIVE", members__user=self.request.user)
            | models.Q(project_id__in=_projects_visible_to_approver(self.request.user))
        ).distinct()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        _require_admin(request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.validated_data["project"]
        member_ids = serializer.validated_data["member_ids"]
        chair = serializer.validated_data.get("chair")
        committee_type = serializer.validated_data["committee_type"]
        if committee_type in {
            Committee.Type.TSC,
            Committee.Type.TEC,
            Committee.Type.TAC,
        } and not chair:
            raise ValidationError({"chair": "Select a chair for this committee."})
        if committee_type == Committee.Type.TAC:
            ia_wing_members = User.objects.filter(
                id__in=member_ids,
                roles__name="IA_WING",
                is_active=True,
                verification_status="VERIFIED",
            ).distinct().count()
            if ia_wing_members != 1:
                raise ValidationError({
                    "member_ids": "Select exactly one active, verified IA Wing user as a TAC member."
                })
        if chair and chair.id not in member_ids:
            raise ValidationError({"chair": "The chair must be selected as a committee member."})
        if committee_type == Committee.Type.TAC and len(member_ids) < 2:
            raise ValidationError({
                "member_ids": "Select the IA Wing member and at least one other TAC member."
            })
        if Committee.objects.filter(project=project, committee_type=committee_type).exclude(
            status="REJECTED"
        ).exists():
            raise ValidationError({"committee_type": "This project already has this committee."})
        formation_stage = None
        supersedes = None
        revision = 1
        formation_file = None
        formation_submission_type = {
            Committee.Type.TSC: StageSubmission.Type.TSC_FORMATION,
            Committee.Type.TEC: StageSubmission.Type.TEC_FORMATION,
            Committee.Type.TAC: StageSubmission.Type.TAC_FORMATION,
        }.get(committee_type)
        if formation_submission_type:
            if committee_type == Committee.Type.TSC:
                formation_stage = ProjectStage.objects.filter(
                    project=project,
                    stage_type=ProjectStage.Type.TSC_FORMATION,
                ).first()
                if not formation_stage:
                    max_sequence = ProjectStage.objects.filter(project=project).aggregate(
                        value=Max("sequence")
                    )["value"] or 0
                    formation_stage = ProjectStage.objects.create(
                        project=project,
                        stage_type=ProjectStage.Type.TSC_FORMATION,
                        sequence=max_sequence + 1,
                        created_by=request.user,
                    )
            elif committee_type == Committee.Type.TEC:
                latest_tender_draft = _latest_tender_draft(project)
                tender_is_approved = (
                    latest_tender_draft
                    and latest_tender_draft.status == StageSubmission.Status.APPROVED
                    and Tender.objects.filter(
                        project=project,
                        status__in=[Tender.Status.APPROVED, Tender.Status.DISTRIBUTED],
                    ).exists()
                )
                if not tender_is_approved:
                    raise ValidationError({
                        "committee_type": (
                            "TEC formation can start after the tender draft is approved."
                        )
                    })
                selected_vendors = list(ProjectVendor.objects.filter(
                    project=project,
                    participation_status__in=[
                        "SELECTED", "TENDER_SENT", "BID_RECEIVED",
                    ],
                ))
                if not selected_vendors or any(
                    vendor.participation_status == "SELECTED"
                    or not TenderDispatch.objects.filter(
                        tender__project=project,
                        vendor_id=vendor.vendor_id,
                    ).exists()
                    for vendor in selected_vendors
                ):
                    raise ValidationError({
                        "committee_type": (
                            "Record the tender dispatch to every selected vendor before "
                            "forming the TEC."
                        )
                    })
                formation_stage = _get_or_create_stage_after(
                    project,
                    request.user,
                    ProjectStage.Type.TEC_FORMATION,
                    ProjectStage.Type.TENDER_DRAFT,
                )
            else:
                qualification_stage = ProjectStage.objects.filter(
                    project=project,
                    stage_type=ProjectStage.Type.VENDOR_QUALIFICATION,
                    status=ProjectStage.Status.COMPLETED,
                ).first()
                qualified_vendors_exist = ProjectVendor.objects.filter(
                    project=project,
                    qualification_status=ProjectVendor.QualificationStatus.QUALIFIED,
                    participation_status__in=[
                        "SELECTED", "TENDER_SENT", "BID_RECEIVED",
                    ],
                ).exists()
                if not qualification_stage or not qualified_vendors_exist:
                    raise ValidationError({
                        "committee_type": (
                            "TAC formation can start after vendor qualification is "
                            "complete and at least one vendor is qualified."
                        )
                    })
                formation_stage = _get_or_create_stage_after(
                    project,
                    request.user,
                    ProjectStage.Type.TAC_FORMATION,
                    ProjectStage.Type.VENDOR_QUALIFICATION,
                )
            _validate_stage_is_ready(formation_stage)
            policy = _get_active_policy(formation_submission_type)
            _validate_committee_formation_policy(policy)
            uploaded_file = request.FILES.get("file")
            if uploaded_file:
                file_serializer = StageSubmissionSerializer(
                    data={
                        "stage": str(formation_stage.id),
                        "submission_type": formation_submission_type,
                        "title": f"{serializer.validated_data['committee_name']} formation",
                        "file": uploaded_file,
                    },
                    context={"request": request},
                )
                file_serializer.is_valid(raise_exception=True)
                formation_file = file_serializer.validated_data["file"]
            supersedes = StageSubmission.objects.filter(
                stage=formation_stage,
                submission_type=formation_submission_type,
            ).order_by("-revision").first()
            if supersedes:
                if supersedes.status != StageSubmission.Status.REJECTED:
                    raise ValidationError({
                        "committee_type": (
                            f"A {committee_type} formation is already awaiting approval "
                            "or has been approved."
                        )
                    })
                revision = supersedes.revision + 1

        committee = serializer.save(
            formed_by=request.user,
            status="SUBMITTED" if formation_submission_type else "DRAFT",
        )
        memberships = [
            CommitteeMember(committee=committee, user_id=user_id)
            for user_id in member_ids
        ]
        CommitteeMember.objects.bulk_create(memberships)
        if not formation_submission_type:
            for user_id in member_ids:
                ProjectMember.objects.get_or_create(
                    project=project,
                    user_id=user_id,
                    defaults={"assigned_by": request.user},
                )
            ProjectActivity.objects.create(
                project=project,
                actor=request.user,
                activity_type="COMMITTEE_FORMED",
                message=f"{committee.get_committee_type_display()} membership drafted",
            )
        else:
            submission = StageSubmission.objects.create(
                stage=formation_stage,
                committee=committee,
                submission_type=formation_submission_type,
                revision=revision,
                supersedes=supersedes,
                submitted_by=request.user,
                title=f"{committee.committee_name} formation",
            )
            if formation_file:
                submission.file = formation_file
                submission.save(update_fields=["file"])
            _create_submission(submission, request.user)
            ProjectActivity.objects.create(
                project=project,
                actor=request.user,
                activity_type="FORWARDED",
                message=f"{committee.committee_name} formation sent to SS for approval.",
            )
        AuditLog.objects.create(
            user=request.user,
            entity_type="committee",
            entity_id=str(committee.id),
            operation=(
                "SUBMIT_FORMATION"
                if formation_submission_type
                else "CREATE"
            ),
            new_values={"type": committee.committee_type, "members": [str(x) for x in member_ids]},
        )
        headers = self.get_success_headers(serializer.data)
        return Response(
            self.get_serializer(committee).data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

    @action(detail=True, methods=["post"], url_path="submit-formation")
    @transaction.atomic
    def submit_formation(self, request, pk=None):
        _require_admin(request.user)
        committee = self.get_object()
        if committee.committee_type in {
            Committee.Type.TSC,
            Committee.Type.TEC,
            Committee.Type.TAC,
        }:
            raise ValidationError({
                "status": "Committee formation is submitted for SS approval when it is created."
            })
        if committee.status != "DRAFT":
            raise ValidationError({"status": "Only draft committees can be submitted."})
        stage_type = f"{committee.committee_type}_FORMATION"
        stage = ProjectStage.objects.filter(
            project=committee.project, stage_type=stage_type
        ).first()
        if not stage:
            raise ValidationError({"stage": f"Create the {stage_type} stage first."})
        _validate_stage_is_ready(stage)
        submission = StageSubmission.objects.create(
            stage=stage,
            committee=committee,
            submission_type=stage_type,
            submitted_by=request.user,
            title=f"{committee.committee_name} formation",
            comments=request.data.get("comments", ""),
        )
        _create_submission(submission, request.user)
        committee.status = "SUBMITTED"
        committee.save(update_fields=["status"])
        AuditLog.objects.create(
            user=request.user,
            entity_type="committee",
            entity_id=str(committee.id),
            operation="SUBMIT_FORMATION",
        )
        return Response(StageSubmissionSerializer(submission, context={"request": request}).data, status=201)


class ApprovalPolicyViewSet(viewsets.ModelViewSet):
    serializer_class = ApprovalPolicySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = ApprovalPolicy.objects.prefetch_related("levels")
        return queryset if _is_admin(self.request.user) else queryset.none()

    def perform_create(self, serializer):
        _require_admin(self.request.user)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        _require_admin(self.request.user)
        serializer.save()


class ApprovalPolicyLevelViewSet(viewsets.ModelViewSet):
    serializer_class = ApprovalPolicyLevelSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        queryset = ApprovalPolicyLevel.objects.select_related("policy", "approver")
        if not _is_admin(self.request.user):
            return queryset.none()
        policy_id = self.request.query_params.get("policy")
        return queryset.filter(policy_id=policy_id) if policy_id else queryset

    def perform_create(self, serializer):
        _require_admin(self.request.user)
        policy = serializer.validated_data["policy"]
        if not policy.is_active:
            raise ValidationError({"policy": "Cannot add levels to an inactive policy."})
        if policy.requests.exists():
            raise ValidationError({"policy": "A policy used by submitted work cannot be changed."})
        serializer.save()

    def perform_destroy(self, instance):
        _require_admin(self.request.user)
        if ApprovalRequest.objects.filter(policy=instance.policy).exists():
            raise ValidationError("A policy already used by a request cannot be edited.")
        instance.delete()


class StageSubmissionViewSet(viewsets.ModelViewSet):
    serializer_class = StageSubmissionSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = StageSubmission.objects.select_related(
            "stage__project", "committee", "submitted_by"
        ).prefetch_related("approval_requests__steps", "approval_requests__events")
        user = self.request.user
        if _is_admin(user):
            return queryset
        return queryset.filter(
            models.Q(stage__project__created_by=user)
            | models.Q(stage__project__members__user=user)
            | models.Q(
                stage__project__committees__status="ACTIVE",
                stage__project__committees__members__user=user,
            )
            | models.Q(
                approval_requests__steps__status__in=[
                    ApprovalStep.Status.PENDING,
                    ApprovalStep.Status.QUERY,
                ],
                approval_requests__steps__assigned_user=user,
            )
            | models.Q(
                approval_requests__steps__status__in=[
                    ApprovalStep.Status.PENDING,
                    ApprovalStep.Status.QUERY,
                ],
                approval_requests__steps__approver_role__in=user.roles.values_list("name", flat=True),
            )
            | models.Q(approval_requests__events__actor=user)
        ).distinct()

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        submission = self.get_object()
        if not submission.file:
            raise NotFound("This submission has no attached file.")
        response = FileResponse(submission.file.open("rb"), content_type="application/pdf")
        filename = submission.file.name.rsplit("/", 1)[-1].replace('"', "")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submission_type = serializer.validated_data["submission_type"]
        committee = serializer.validated_data.get("committee")
        if submission_type in {
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
        }:
            raise ValidationError({
                "submission_type": "Create and submit committee formation through the committee form."
            })
        stage = serializer.validated_data.get("stage")
        if submission_type in {
            StageSubmission.Type.TSC_REPORT,
            StageSubmission.Type.TSC_REPORT_LEVEL3,
        }:
            if not committee or committee.committee_type != Committee.Type.TSC:
                raise ValidationError({"committee": "Choose the project's TSC."})
            if not _project_is_visible(committee.project, request.user):
                raise PermissionDenied("You do not have access to this project.")
            if (
                submission_type == StageSubmission.Type.TSC_REPORT
                and committee.chair_id != request.user.id
            ):
                raise PermissionDenied("Only the TSC chair can submit the TSC report to AS.")
            if (
                submission_type == StageSubmission.Type.TSC_REPORT_LEVEL3
                and committee.chair_id != request.user.id
                and not _is_admin(request.user)
            ):
                raise PermissionDenied(
                    "Only the TSC chair or an administrator can submit the TSC report to DGS."
                )
            if committee.status != "ACTIVE":
                raise ValidationError({
                    "committee": "The TSC must be approved and active before submitting its report."
                })
            expected_stage_type = (
                ProjectStage.Type.TSC_REPORT
                if submission_type == StageSubmission.Type.TSC_REPORT
                else ProjectStage.Type.TSC_REPORT_LEVEL3
            )
            if stage and (stage.project_id != committee.project_id or stage.stage_type != expected_stage_type):
                raise ValidationError({"stage": "The TSC report stage must match the project and approval level."})
            if submission_type == StageSubmission.Type.TSC_REPORT:
                _validate_role_policy(
                    _get_active_policy(StageSubmission.Type.TSC_REPORT),
                    ["AS", "HQ"],
                )
            else:
                source_report = serializer.validated_data.get("source_report")
                latest_level3 = StageSubmission.objects.filter(
                    committee=committee,
                    submission_type=StageSubmission.Type.TSC_REPORT_LEVEL3,
                ).order_by("-revision").first()
                if latest_level3 and latest_level3.status in {
                    StageSubmission.Status.NEEDS_RESPONSE,
                    StageSubmission.Status.REJECTED,
                }:
                    source_report = source_report or latest_level3.source_report
                latest_level2 = (
                    StageSubmission.objects.filter(
                        stage=source_report.stage,
                        submission_type=StageSubmission.Type.TSC_REPORT,
                    ).order_by("-revision").first()
                    if source_report else None
                )
                if not source_report or (
                    source_report.submission_type != StageSubmission.Type.TSC_REPORT
                    or source_report.committee_id != committee.id
                    or source_report.status != StageSubmission.Status.APPROVED
                    or not latest_level2
                    or latest_level2.id != source_report.id
                ):
                    raise ValidationError({
                        "source_report": (
                            "DGS review can start only after the latest TSC report "
                            "is approved by AS and HQ."
                        )
                    })
                latest_level2_request = source_report.approval_requests.order_by(
                    "-created_at"
                ).first()
                if not latest_level2_request or latest_level2_request.status != ApprovalRequest.Status.APPROVED:
                    raise ValidationError({
                        "source_report": "The selected report must have AS and HQ approval."
                    })
                serializer.validated_data["source_report"] = source_report
                if not serializer.validated_data.get("file"):
                    serializer.validated_data["file"] = source_report.file
            if not stage:
                stage = _get_or_create_tsc_report_stage(
                    committee.project,
                    request.user,
                    stage_type=expected_stage_type,
                )
                serializer.validated_data["stage"] = stage
        if submission_type == StageSubmission.Type.TEC_REPORT and not stage:
            if not committee or committee.committee_type != Committee.Type.TEC:
                raise ValidationError({"committee": "Choose the project's TEC."})
            stage = _get_or_create_stage_after(
                committee.project,
                request.user,
                ProjectStage.Type.TEC_REPORT,
                ProjectStage.Type.TEC_FORMATION,
            )
            serializer.validated_data["stage"] = stage
        if not stage:
            raise ValidationError({"stage": "A project stage is required."})
        if not _project_is_visible(stage.project, request.user):
            raise PermissionDenied("You do not have access to this project.")
        if submission_type == StageSubmission.Type.TENDER_DRAFT:
            latest_level3_report = _latest_tsc_level3_report(stage.project)
            if (
                not latest_level3_report
                or latest_level3_report.status != StageSubmission.Status.APPROVED
            ):
                raise ValidationError({
                    "submission_type": (
                        "A tender draft can be submitted only after DGS approves "
                        "the latest TSC report."
                    )
                })
        _validate_stage_is_ready(stage)
        if submission_type in {
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
            StageSubmission.Type.TAC_FORMATION,
            StageSubmission.Type.TENDER_DRAFT,
        }:
            _require_admin(request.user)
        if submission_type in {
            StageSubmission.Type.TSC_REPORT,
            StageSubmission.Type.TSC_REPORT_LEVEL3,
            StageSubmission.Type.TEC_REPORT,
        }:
            expected_type = (
                Committee.Type.TSC
                if submission_type in {
                    StageSubmission.Type.TSC_REPORT,
                    StageSubmission.Type.TSC_REPORT_LEVEL3,
                }
                else Committee.Type.TEC
            )
            if not committee or committee.project_id != stage.project_id or committee.committee_type != expected_type:
                raise ValidationError({"committee": "Choose the matching project committee."})
            if submission_type in {
                StageSubmission.Type.TSC_REPORT,
                StageSubmission.Type.TSC_REPORT_LEVEL3,
            }:
                if (
                    submission_type == StageSubmission.Type.TSC_REPORT
                    and committee.chair_id != request.user.id
                ):
                    raise PermissionDenied("Only the TSC chair can submit the TSC report to AS.")
                if (
                    submission_type == StageSubmission.Type.TSC_REPORT_LEVEL3
                    and committee.chair_id != request.user.id
                    and not _is_admin(request.user)
                ):
                    raise PermissionDenied(
                        "Only the TSC chair or an administrator can submit the TSC report to DGS."
                    )
                role = (
                    ["AS", "HQ"]
                    if submission_type == StageSubmission.Type.TSC_REPORT
                    else ["DGS"]
                )
                _validate_role_policy(
                    _get_active_policy(submission_type),
                    role,
                )
            elif submission_type == StageSubmission.Type.TEC_REPORT:
                if committee.chair_id != request.user.id:
                    raise PermissionDenied("Only the TEC chair can submit the final TEC report.")
                _validate_single_role_policy(
                    _get_active_policy(submission_type),
                    "HQ",
                )
            elif not _is_committee_member(committee, request.user) and not _is_admin(request.user):
                raise PermissionDenied("Only assigned committee members can submit this report.")
            if committee.status != "ACTIVE":
                raise ValidationError({"committee": "The committee must be approved and active before submitting its report."})
        if submission_type in {
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
            StageSubmission.Type.TAC_FORMATION,
        }:
            raise ValidationError(
                {"submission_type": "Submit committee formation through the committee's submit-formation action."}
            )
        supersedes = serializer.validated_data.get("supersedes")
        revision = 1
        latest = StageSubmission.objects.filter(
            stage=stage, submission_type=submission_type
        ).order_by("-revision").first()
        if latest and not supersedes:
            if (
                submission_type in {
                    StageSubmission.Type.TSC_REPORT,
                    StageSubmission.Type.TSC_REPORT_LEVEL3,
                    StageSubmission.Type.TEC_REPORT,
                    StageSubmission.Type.TENDER_DRAFT,
                }
                and latest.status in {
                    StageSubmission.Status.NEEDS_RESPONSE,
                    StageSubmission.Status.REJECTED,
                }
            ):
                supersedes = latest
            else:
                raise ValidationError(
                    {"supersedes": "A new submission must reference the prior submission revision."}
                )
        if supersedes:
            if not latest or supersedes.id != latest.id:
                raise ValidationError({"supersedes": "Revise the latest submission only."})
            if supersedes.stage_id != stage.id or supersedes.submission_type != submission_type:
                raise ValidationError({"supersedes": "The prior submission must be for the same stage and type."})
            if supersedes.status not in {
                StageSubmission.Status.NEEDS_RESPONSE,
                StageSubmission.Status.REJECTED,
            }:
                raise ValidationError({"supersedes": "Only queried or rejected submissions can be revised."})
            if (
                submission_type in {
                    StageSubmission.Type.TSC_REPORT,
                    StageSubmission.Type.TSC_REPORT_LEVEL3,
                    StageSubmission.Type.TEC_REPORT,
                    StageSubmission.Type.TENDER_DRAFT,
                }
                and supersedes.status == StageSubmission.Status.NEEDS_RESPONSE
                and not str(serializer.validated_data.get("comments", "")).strip()
            ):
                raise ValidationError({
                    "comments": "Add a response to the query when resubmitting this document."
                })
            revision = supersedes.revision + 1
            old_request = supersedes.approval_requests.order_by("-created_at").first()
            if old_request:
                active_step = _active_step(old_request)
                old_request.status = ApprovalRequest.Status.SUPERSEDED
                old_request.closed_at = timezone.now()
                old_request.save(update_fields=["status", "closed_at"])
                if (
                    submission_type in {
                        StageSubmission.Type.TSC_REPORT,
                        StageSubmission.Type.TSC_REPORT_LEVEL3,
                        StageSubmission.Type.TEC_REPORT,
                        StageSubmission.Type.TENDER_DRAFT,
                    }
                    and active_step
                    and active_step.status == ApprovalStep.Status.QUERY
                ):
                    ApprovalEvent.objects.create(
                        request=old_request,
                        step=active_step,
                        actor=request.user,
                        action=ApprovalEvent.Action.RESPONSE,
                        comment=serializer.validated_data.get("comments", ""),
                    )
                document_label = {
                    StageSubmission.Type.TSC_REPORT: "TSC report",
                    StageSubmission.Type.TSC_REPORT_LEVEL3: "TSC report for DGS",
                    StageSubmission.Type.TEC_REPORT: "TEC final report",
                    StageSubmission.Type.TENDER_DRAFT: "tender draft",
                }.get(submission_type, "document")
                ApprovalEvent.objects.create(
                    request=old_request,
                    step=active_step,
                    actor=request.user,
                    action=ApprovalEvent.Action.RESUBMITTED,
                    comment=f"Revised {document_label} submitted for approval (revision {revision}).",
                )
            supersedes.status = StageSubmission.Status.SUPERSEDED
            supersedes.save(update_fields=["status"])
        submission = serializer.save(
            submitted_by=request.user,
            revision=revision,
            supersedes=supersedes,
            source_report=(
                serializer.validated_data.get("source_report")
                or (supersedes.source_report if supersedes else None)
            ),
        )
        _create_submission(submission, request.user)
        if submission_type == StageSubmission.Type.TEC_REPORT:
            latest_version = TECWorkDocument.objects.filter(
                committee=committee,
                document_type=TECWorkDocument.Type.FINAL,
            ).aggregate(max_version=Max("version"))["max_version"] or 0
            TECWorkDocument.objects.create(
                committee=committee,
                document_type=TECWorkDocument.Type.FINAL,
                version=latest_version + 1,
                file=submission.file,
                uploaded_by=request.user,
            )
            ProjectActivity.objects.create(
                project=committee.project,
                actor=request.user,
                activity_type="DOCUMENT_UPLOADED",
                message=(
                    f"{committee.committee_name} submitted a revised final report "
                    f"(revision {submission.revision}) for HQ approval."
                ),
            )
        AuditLog.objects.create(
            user=request.user,
            entity_type="stage_submission",
            entity_id=str(submission.id),
            operation="SUBMIT",
            new_values={"type": submission_type, "revision": revision},
        )
        return Response(
            self.get_serializer(submission).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    def _get_step(self, request, submission):
        if (
            submission.submission_type == StageSubmission.Type.TSC_FORMATION
            and not has_any_role(request.user, "SS")
        ):
            raise PermissionDenied("Only SS can review TSC formation.")
        if (
            submission.submission_type == StageSubmission.Type.TEC_FORMATION
            and not has_any_role(request.user, "SS")
        ):
            raise PermissionDenied("Only SS can review TEC formation.")
        if (
            submission.submission_type == StageSubmission.Type.TSC_REPORT
            and not has_any_role(request.user, "AS", "HQ")
        ):
            raise PermissionDenied("Only AS or HQ can review TSC reports.")
        if (
            submission.submission_type == StageSubmission.Type.TSC_REPORT_LEVEL3
            and not has_any_role(request.user, "DGS")
        ):
            raise PermissionDenied("Only DGS can review TSC reports.")
        if (
            submission.submission_type == StageSubmission.Type.TEC_REPORT
            and not has_any_role(request.user, "HQ")
        ):
            raise PermissionDenied("Only HQ can review TEC final reports.")
        if (
            submission.submission_type == StageSubmission.Type.TENDER_DRAFT
            and not has_any_role(request.user, "IA_WING")
        ):
            raise PermissionDenied("Only IA Wing can review tender drafts.")
        approval_request = submission.approval_requests.select_for_update().order_by(
            "-created_at"
        ).first()
        if not approval_request:
            raise NotFound("No approval request exists for this submission.")
        step = approval_request.steps.select_for_update().filter(
            status__in=[ApprovalStep.Status.PENDING, ApprovalStep.Status.QUERY]
        ).order_by("sequence").first()
        if not step:
            raise ValidationError({"approval": "This submission has no active approval step."})
        if not _can_act_on_step(step, request.user):
            raise PermissionDenied("You are not the approver for the active approval step.")
        return approval_request, step

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def approve(self, request, pk=None):
        submission = self.get_object()
        approval_request, step = self._get_step(request, submission)
        if step.status != ApprovalStep.Status.PENDING:
            raise ValidationError({"status": "Only a pending step can be approved."})
        comment = request.data.get("comment", "")
        ApprovalEvent.objects.create(
            request=approval_request, step=step, actor=request.user,
            action=ApprovalEvent.Action.APPROVED, comment=comment,
        )
        step.status = ApprovalStep.Status.APPROVED
        step.save(update_fields=["status"])
        next_step = approval_request.steps.filter(
            status=ApprovalStep.Status.BLOCKED
        ).order_by("sequence").first()
        if next_step:
            next_step.status = ApprovalStep.Status.PENDING
            next_step.save(update_fields=["status"])
            Notification.objects.create(
                recipient=next_step.assigned_user,
                project=submission.stage.project,
                title="Approval required",
                message=f"{submission.title} is awaiting your approval.",
            ) if next_step.assigned_user_id else None
            if next_step.approver_role:
                for approver in User.objects.filter(
                    roles__name=next_step.approver_role,
                    is_active=True,
                    verification_status="VERIFIED",
                ).distinct():
                    Notification.objects.create(
                        recipient=approver,
                        project=submission.stage.project,
                        title="Approval required",
                        message=f"{submission.title} is awaiting your approval.",
                    )
        else:
            approval_request.status = ApprovalRequest.Status.APPROVED
            approval_request.closed_at = timezone.now()
            submission.status = StageSubmission.Status.APPROVED
            stage = submission.stage
            stage.status = ProjectStage.Status.COMPLETED
            stage.completed_at = timezone.now()
            stage.save(update_fields=["status", "completed_at"])
            committee = submission.committee
            if committee and submission.submission_type.endswith("_FORMATION"):
                committee.status = "ACTIVE"
                committee.save(update_fields=["status"])
                for member in committee.members.select_related("user"):
                    ProjectMember.objects.get_or_create(
                        project=committee.project,
                        user=member.user,
                        defaults={"assigned_by": committee.formed_by},
                    )
                    Notification.objects.create(
                        recipient=member.user,
                        project=committee.project,
                        title="Committee formation approved",
                        message=f"{committee.committee_name} is now active.",
                    )
                if committee.committee_type == Committee.Type.TAC:
                    _get_or_create_stage_after(
                        committee.project,
                        request.user,
                        ProjectStage.Type.TAC_FINANCIAL_BIDS,
                        ProjectStage.Type.TAC_FORMATION,
                    )
                    _get_or_create_stage_after(
                        committee.project,
                        request.user,
                        ProjectStage.Type.TAC_FINAL_REPORT,
                        ProjectStage.Type.TAC_FINANCIAL_BIDS,
                    )
                    selection_stage = _get_or_create_stage_after(
                        committee.project,
                        request.user,
                        ProjectStage.Type.VENDOR_SELECTION,
                        ProjectStage.Type.TAC_FINAL_REPORT,
                    )
                    if selection_stage.status == ProjectStage.Status.CANCELLED:
                        selection_stage.status = ProjectStage.Status.NOT_STARTED
                        selection_stage.save(update_fields=["status"])
            if submission.submission_type == StageSubmission.Type.TSC_REPORT_LEVEL3:
                _get_or_create_stage_after(
                    submission.stage.project,
                    request.user,
                    ProjectStage.Type.TENDER_DRAFT,
                    ProjectStage.Type.TSC_REPORT_LEVEL3,
                )
        approval_request.save(update_fields=["status", "closed_at"])
        submission.save(update_fields=["status"])
        if submission.submission_type == StageSubmission.Type.TENDER_DRAFT:
            latest_submission = _latest_tender_draft(submission.stage.project)
            if latest_submission and latest_submission.id == submission.id:
                _ensure_tender_for_approved_draft(
                    submission.stage.project,
                    submission.submitted_by,
                )
        ProjectActivity.objects.create(
            project=submission.stage.project,
            actor=request.user,
            activity_type="APPROVED",
            message=f"Approved {submission.title}",
        )
        return Response(self.get_serializer(submission).data)

    @action(detail=True, methods=["post"], url_path="query")
    @transaction.atomic
    def raise_query(self, request, pk=None):
        submission = self.get_object()
        approval_request, step = self._get_step(request, submission)
        comment = str(request.data.get("comment", "")).strip()
        if not comment:
            raise ValidationError({"comment": "A query must include a comment."})
        if step.status != ApprovalStep.Status.PENDING:
            raise ValidationError({"status": "Only a pending step can raise a query."})
        ApprovalEvent.objects.create(
            request=approval_request, step=step, actor=request.user,
            action=ApprovalEvent.Action.QUERY, comment=comment,
        )
        step.status = ApprovalStep.Status.QUERY
        step.save(update_fields=["status"])
        approval_request.status = ApprovalRequest.Status.NEEDS_RESPONSE
        approval_request.save(update_fields=["status"])
        submission.status = StageSubmission.Status.NEEDS_RESPONSE
        submission.save(update_fields=["status"])
        submission.stage.status = ProjectStage.Status.NEEDS_REVISION
        submission.stage.save(update_fields=["status"])
        Notification.objects.create(
            recipient=submission.submitted_by,
            project=submission.stage.project,
            title="Submission query",
            message=f"A query was raised on {submission.title}: {comment}",
        )
        return Response(ApprovalEventSerializer(
            approval_request.events.order_by("-created_at").first()
        ).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def respond(self, request, pk=None):
        submission = self.get_object()
        if submission.submission_type in {
            StageSubmission.Type.TSC_REPORT,
            StageSubmission.Type.TSC_REPORT_LEVEL3,
            StageSubmission.Type.TEC_REPORT,
        }:
            if request.user.id != submission.submitted_by_id:
                raise PermissionDenied("Only the committee chair can respond to a report query.")
            raise ValidationError({
                "file": "Respond to a report query by uploading a revised report with your comments."
            })
        if request.user.id != submission.submitted_by_id and not _is_admin(request.user):
            raise PermissionDenied("Only the submitter or an administrator can respond.")
        approval_request = submission.approval_requests.filter(
            status=ApprovalRequest.Status.NEEDS_RESPONSE
        ).order_by("-created_at").first()
        if not approval_request:
            raise ValidationError({"status": "This submission is not awaiting a response."})
        comment = str(request.data.get("comment", "")).strip()
        if not comment:
            raise ValidationError({"comment": "A response cannot be empty."})
        step = _active_step(approval_request)
        if not step or step.status != ApprovalStep.Status.QUERY:
            raise ValidationError({"status": "This submission has no active query to respond to."})
        revised_committee = None
        member_ids = None
        response_file = None
        formation_types = {
            StageSubmission.Type.TSC_FORMATION,
            StageSubmission.Type.TEC_FORMATION,
            StageSubmission.Type.TAC_FORMATION,
        }
        if submission.submission_type in formation_types:
            _require_admin(request.user)
            revised_committee = submission.committee
            if not revised_committee:
                raise ValidationError({"committee": "The committee proposal has no membership to revise."})
            raw_member_ids = (
                request.data.getlist("member_ids")
                if hasattr(request.data, "getlist")
                else request.data.get("member_ids")
            )
            if not isinstance(raw_member_ids, list) or not raw_member_ids:
                raise ValidationError({
                    "member_ids": "Select at least one active, verified committee member."
                })
            uploaded_file = request.FILES.get("file")
            if uploaded_file:
                file_serializer = StageSubmissionSerializer(
                    data={
                        "stage": str(submission.stage_id),
                        "submission_type": submission.submission_type,
                        "title": submission.title,
                        "file": uploaded_file,
                    },
                    context={"request": request},
                )
                file_serializer.is_valid(raise_exception=True)
                response_file = file_serializer.validated_data["file"]
            member_ids = []
            for value in raw_member_ids:
                try:
                    member_id = str(UUID(str(value)))
                except (AttributeError, TypeError, ValueError):
                    raise ValidationError({"member_ids": "One or more member IDs are invalid."})
                member_ids.append(member_id)
            if len(member_ids) != len(set(member_ids)):
                raise ValidationError({"member_ids": "A user can only be selected once."})
            if revised_committee.committee_type == Committee.Type.TAC:
                ia_wing_members = User.objects.filter(
                    id__in=member_ids,
                    roles__name="IA_WING",
                    is_active=True,
                    verification_status="VERIFIED",
                ).distinct().count()
                if ia_wing_members != 1:
                    raise ValidationError({
                        "member_ids": "Select exactly one active, verified IA Wing user as a TAC member."
                    })
            if (
                revised_committee.committee_type == Committee.Type.TAC
                and len(member_ids) < 2
            ):
                raise ValidationError({
                    "member_ids": "Select the IA Wing member and at least one other TAC member."
                })
            valid_members = User.objects.filter(
                id__in=member_ids,
                is_active=True,
                verification_status="VERIFIED",
            )
            if valid_members.count() != len(member_ids):
                raise ValidationError({
                    "member_ids": "All selected members must be active, verified users."
                })
            try:
                chair_id = str(UUID(str(request.data.get("chair"))))
            except (AttributeError, TypeError, ValueError):
                chair_id = ""
            if not chair_id or chair_id not in member_ids:
                raise ValidationError({
                    "chair": "Select a chair who is included in the committee members."
                })
            committee_name = str(
                request.data.get("committee_name", revised_committee.committee_name)
            ).strip()
            if not committee_name:
                raise ValidationError({"committee_name": "Enter a committee name."})
            old_members = list(
                revised_committee.members.values_list("user_id", flat=True)
            )
            old_chair_id = revised_committee.chair_id
            old_name = revised_committee.committee_name
            revised_committee.committee_name = committee_name
            revised_committee.chair_id = chair_id
            revised_committee.save(update_fields=["committee_name", "chair"])
            revised_committee.members.all().delete()
            CommitteeMember.objects.bulk_create([
                CommitteeMember(committee=revised_committee, user_id=member_id)
                for member_id in member_ids
            ])
            AuditLog.objects.create(
                user=request.user,
                entity_type="committee",
                entity_id=str(revised_committee.id),
                operation=f"UPDATE_{revised_committee.committee_type}_FOR_RESUBMISSION",
                old_values={
                    "committee_name": old_name,
                    "chair": str(old_chair_id) if old_chair_id else None,
                    "members": [str(member_id) for member_id in old_members],
                },
                new_values={
                    "committee_name": committee_name,
                    "chair": str(chair_id),
                    "members": member_ids,
                },
            )
        ApprovalEvent.objects.create(
            request=approval_request,
            step=step,
            actor=request.user,
            action=ApprovalEvent.Action.RESPONSE,
            comment=comment,
        )
        if submission.submission_type in formation_types:
            step.status = ApprovalStep.Status.PENDING
            step.save(update_fields=["status"])
            approval_request.status = ApprovalRequest.Status.IN_PROGRESS
            approval_request.save(update_fields=["status"])
            submission.status = StageSubmission.Status.IN_REVIEW
            if response_file:
                submission.file = response_file
            submission.save(
                update_fields=["status", "file"] if response_file else ["status"]
            )
            submission.stage.status = ProjectStage.Status.WAITING_APPROVAL
            submission.stage.save(update_fields=["status"])
            if revised_committee:
                ProjectActivity.objects.create(
                    project=submission.stage.project,
                    actor=request.user,
                    activity_type="FORWARDED",
                    message=(
                        f"Revised {revised_committee.committee_name} membership "
                        "and resubmitted it to SS for approval."
                    ),
                )
                Notification.objects.create(
                    recipient=step.assigned_user,
                    project=submission.stage.project,
                    title="Revised committee awaiting approval",
                    message=(
                        f"{revised_committee.committee_name} membership was revised "
                        "and resubmitted for your approval."
                    ),
                ) if step.assigned_user_id else None
                if step.approver_role:
                    for approver in User.objects.filter(
                        roles__name=step.approver_role,
                        is_active=True,
                        verification_status="VERIFIED",
                    ).distinct():
                        Notification.objects.create(
                            recipient=approver,
                            project=submission.stage.project,
                            title="Revised committee awaiting approval",
                            message=(
                                f"{revised_committee.committee_name} membership was revised "
                                "and resubmitted for your approval."
                            ),
                        )
        return Response(ApprovalRequestSerializer(approval_request).data, status=201)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reject(self, request, pk=None):
        submission = self.get_object()
        approval_request, step = self._get_step(request, submission)
        comment = str(request.data.get("comment", "")).strip()
        if not comment:
            raise ValidationError({"comment": "A rejection must include a reason."})
        if step.status != ApprovalStep.Status.PENDING:
            raise ValidationError({"status": "Only a pending step can be rejected."})
        ApprovalEvent.objects.create(
            request=approval_request, step=step, actor=request.user,
            action=ApprovalEvent.Action.REJECTED, comment=comment,
        )
        step.status = ApprovalStep.Status.REJECTED
        step.save(update_fields=["status"])
        approval_request.status = ApprovalRequest.Status.REJECTED
        approval_request.closed_at = timezone.now()
        approval_request.save(update_fields=["status", "closed_at"])
        submission.status = StageSubmission.Status.REJECTED
        submission.save(update_fields=["status"])
        if (
            submission.committee_id
            and submission.submission_type in {
                StageSubmission.Type.TSC_FORMATION,
                StageSubmission.Type.TEC_FORMATION,
            }
        ):
            submission.committee.status = "REJECTED"
            submission.committee.save(update_fields=["status"])
        submission.stage.status = ProjectStage.Status.NEEDS_REVISION
        submission.stage.save(update_fields=["status"])
        ProjectActivity.objects.create(
            project=submission.stage.project,
            actor=request.user,
            activity_type="REJECTED",
            message=f"Rejected {submission.title}: {comment}",
        )
        Notification.objects.create(
            recipient=submission.submitted_by,
            project=submission.stage.project,
            title="Submission rejected",
            message=f"{submission.title} was rejected: {comment}",
        )
        return Response(self.get_serializer(submission).data)


class TenderViewSet(viewsets.ModelViewSet):
    serializer_class = TenderSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Tender.objects.select_related("project").prefetch_related(
            "dispatches__vendor"
        ).order_by("created_at")
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        user = self.request.user
        if _is_admin(user):
            return queryset
        return queryset.filter(
            models.Q(project__created_by=user)
            | models.Q(project__members__user=user)
            | models.Q(
                project__committees__status="ACTIVE",
                project__committees__members__user=user,
            )
            | models.Q(project_id__in=_projects_visible_to_approver(user))
        ).distinct()

    def perform_create(self, serializer):
        _require_admin(self.request.user)
        project = serializer.validated_data["project"]
        latest_level3_report = _latest_tsc_level3_report(project)
        if (
            not latest_level3_report
            or latest_level3_report.status != StageSubmission.Status.APPROVED
        ):
            raise ValidationError({
                "project": "DGS must approve the TSC report before creating a tender."
            })
        latest_submission = _latest_tender_draft(project)
        if not latest_submission or latest_submission.status != StageSubmission.Status.APPROVED:
            raise ValidationError({"project": "The latest tender draft must be approved first."})
        if Tender.objects.filter(project=project).exists():
            raise ValidationError({"project": "A tender record already exists for this project."})
        serializer.save(created_by=self.request.user, status=Tender.Status.APPROVED)

    @action(detail=False, methods=["post"], url_path="ensure")
    @transaction.atomic
    def ensure(self, request):
        _require_admin(request.user)
        input_serializer = TenderEnsureSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        project = input_serializer.validated_data["project"]
        existed = Tender.objects.filter(project=project).exists()
        tender = _ensure_tender_for_approved_draft(project, request.user)
        return Response(
            self.get_serializer(tender).data,
            status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        _require_admin(self.request.user)
        serializer.save()

    @action(detail=True, methods=["post"], url_path="dispatch")
    @transaction.atomic
    def record_dispatch(self, request, pk=None):
        _require_admin(request.user)
        tender = self.get_object()
        latest_submission = _latest_tender_draft(tender.project)
        if not latest_submission or latest_submission.status != StageSubmission.Status.APPROVED:
            raise ValidationError({
                "tender_draft": "The latest tender draft must be approved before vendor dispatch."
            })
        if tender.status not in {Tender.Status.APPROVED, Tender.Status.DISTRIBUTED}:
            raise ValidationError({"status": "Only approved tenders can be distributed."})
        serializer = TenderDispatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = serializer.validated_data["vendor"]
        project_vendor = ProjectVendor.objects.select_for_update().filter(
            project=tender.project,
            vendor=vendor,
        ).first()
        if not project_vendor or project_vendor.participation_status not in {
            "SELECTED",
            "TENDER_SENT",
            "BID_RECEIVED",
        }:
            raise ValidationError({"vendor": "Select this vendor for the project before dispatch."})
        if not vendor.is_active or vendor.verification_status != Vendor.Status.VERIFIED:
            raise ValidationError({"vendor": "Only active, verified vendors can receive a tender."})
        dispatch = TenderDispatch.objects.create(
            tender=tender,
            recorded_by=request.user,
            dispatched_at=timezone.now(),
            **serializer.validated_data,
        )
        tender.status = Tender.Status.DISTRIBUTED
        tender.save(update_fields=["status"])
        if project_vendor.participation_status == "SELECTED":
            project_vendor.participation_status = "TENDER_SENT"
            project_vendor.save(update_fields=["participation_status"])
        ProjectActivity.objects.create(
            project=tender.project,
            actor=request.user,
            activity_type="FORWARDED",
            message=f"Recorded offline tender dispatch to {vendor.vendor_name}.",
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="tender_dispatch",
            entity_id=str(dispatch.id),
            operation="RECORD_OFFLINE_DISPATCH",
            new_values={
                "project_code": tender.project.project_code,
                "vendor": vendor.vendor_name,
                "method": dispatch.method,
                "reference": dispatch.reference,
                "notes": dispatch.notes,
                "dispatched_at": dispatch.dispatched_at.isoformat(),
            },
        )
        return Response(
            TenderDispatchSerializer(dispatch).data,
            status=status.HTTP_201_CREATED,
        )


class TSCWorkDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = TSCWorkDocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = TSCWorkDocument.objects.select_related(
            "committee", "uploaded_by"
        ).filter(
            committee__committee_type=Committee.Type.TSC,
            committee__status="ACTIVE",
        )
        if not _is_admin(self.request.user):
            queryset = queryset.filter(committee__members__user=self.request.user)
        committee_id = self.request.query_params.get("committee")
        if committee_id:
            queryset = queryset.filter(committee_id=committee_id)
        return queryset.distinct()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        committee = Committee.objects.select_for_update().get(
            pk=serializer.validated_data["committee"].pk
        )
        if committee.committee_type != Committee.Type.TSC:
            raise ValidationError({"committee": "Choose a TSC committee."})
        if committee.status != "ACTIVE":
            raise ValidationError({"committee": "Documents can be shared after the TSC is approved."})
        if not _is_admin(request.user) and not _is_committee_member(committee, request.user):
            raise PermissionDenied("Only members of this TSC can upload shared documents.")
        latest_version = TSCWorkDocument.objects.filter(
            committee=committee,
        ).aggregate(max_version=Max("version"))["max_version"] or 0
        document = serializer.save(
            committee=committee,
            version=latest_version + 1,
            uploaded_by=request.user,
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="tsc_work_document",
            entity_id=str(document.id),
            operation="UPLOAD",
            new_values={
                "committee": str(committee.id),
                "version": document.version,
                "file": document.file.name.rsplit("/", 1)[-1],
            },
        )
        return Response(
            self.get_serializer(document).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(document.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{document.file.name.rsplit("/", 1)[-1]}"'
        )
        return response


class TECWorkDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = TECWorkDocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = TECWorkDocument.objects.select_related(
            "committee__project", "uploaded_by"
        ).filter(
            committee__committee_type=Committee.Type.TEC,
            committee__status="ACTIVE",
        )
        if not _is_admin(self.request.user):
            queryset = queryset.filter(
                models.Q(committee__members__user=self.request.user)
                | models.Q(
                    committee__project__committees__committee_type=Committee.Type.TAC,
                    committee__project__committees__status="ACTIVE",
                    committee__project__committees__members__user=self.request.user,
                    document_type=TECWorkDocument.Type.FINAL,
                )
            )
        committee_id = self.request.query_params.get("committee")
        if committee_id:
            queryset = queryset.filter(committee_id=committee_id)
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(committee__project_id=project_id)
        return queryset.distinct()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        committee = Committee.objects.select_for_update().select_related(
            "project"
        ).get(pk=serializer.validated_data["committee"].pk)
        if committee.committee_type != Committee.Type.TEC:
            raise ValidationError({"committee": "Choose a TEC committee."})
        if committee.status != "ACTIVE":
            raise ValidationError({"committee": "Documents can be shared after the TEC is approved."})
        if not _is_committee_member(committee, request.user):
            raise PermissionDenied("Only TEC members can share committee reports.")

        document_type = serializer.validated_data["document_type"]
        report_stage = None
        if document_type == TECWorkDocument.Type.FINAL:
            if committee.chair_id != request.user.id:
                raise PermissionDenied("Only the TEC chair can upload the final TEC report.")
            if StageSubmission.objects.filter(
                committee=committee,
                submission_type=StageSubmission.Type.TEC_REPORT,
            ).exists():
                raise ValidationError({
                    "document_type": (
                        "A final TEC report has already been submitted. Use the "
                        "report-query response or resubmission form for revisions."
                    )
                })
            selected_vendor_ids = set(ProjectVendor.objects.filter(
                project=committee.project,
                participation_status__in=["SELECTED", "TENDER_SENT", "BID_RECEIVED"],
            ).values_list("vendor_id", flat=True))
            technical_bid_vendor_ids = set(BidDocument.objects.filter(
                bid__tender__project=committee.project,
                bid__status=VendorBid.Status.RECEIVED,
                document_type=BidDocument.Type.TECHNICAL,
            ).values_list("bid__vendor_id", flat=True))
            if not selected_vendor_ids or not selected_vendor_ids.issubset(
                technical_bid_vendor_ids
            ):
                raise ValidationError({
                    "document_type": (
                        "The final TEC report can be uploaded after a technical bid "
                        "has been recorded for every selected vendor."
                    )
                })
            tec_formation_stage = ProjectStage.objects.filter(
                project=committee.project,
                stage_type=ProjectStage.Type.TEC_FORMATION,
            ).first()
            if (
                not tec_formation_stage
                or tec_formation_stage.status != ProjectStage.Status.COMPLETED
            ):
                raise ValidationError({
                    "committee": "TEC formation approval must be complete before submitting its final report."
                })
            report_stage = _get_or_create_stage_after(
                committee.project,
                request.user,
                ProjectStage.Type.TEC_REPORT,
                ProjectStage.Type.TEC_FORMATION,
            )
            _validate_stage_is_ready(report_stage)

        latest_version = TECWorkDocument.objects.filter(
            committee=committee,
            document_type=document_type,
        ).aggregate(max_version=Max("version"))["max_version"] or 0
        document = serializer.save(
            committee=committee,
            version=latest_version + 1,
            uploaded_by=request.user,
        )
        if report_stage:
            submission = StageSubmission.objects.create(
                stage=report_stage,
                committee=committee,
                submission_type=StageSubmission.Type.TEC_REPORT,
                submitted_by=request.user,
                title="TEC Final Report",
                file=document.file,
            )
            _create_submission(submission, request.user)
            Notification.objects.create(
                recipient=committee.project.created_by,
                project=committee.project,
                title="Final TEC report submitted",
                message=(
                    f"{committee.committee_name} submitted its final report "
                    "for HQ approval."
                ),
            )
        ProjectActivity.objects.create(
            project=committee.project,
            actor=request.user,
            activity_type="DOCUMENT_UPLOADED",
            message=(
                f"{committee.committee_name} uploaded its "
                f"{document.get_document_type_display().lower()} (version {document.version})."
            ),
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="tec_work_document",
            entity_id=str(document.id),
            operation="UPLOAD",
            new_values={
                "committee": str(committee.id),
                "document_type": document.document_type,
                "version": document.version,
                "file": document.file.name.rsplit("/", 1)[-1],
            },
        )
        return Response(
            self.get_serializer(document).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(document.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{document.file.name.rsplit("/", 1)[-1]}"'
        )
        return response


class VendorBidViewSet(viewsets.ModelViewSet):
    serializer_class = VendorBidSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = VendorBid.objects.select_related("tender__project", "vendor").prefetch_related("documents")
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(tender__project_id=project_id)
        user = self.request.user
        if _is_admin(user):
            return queryset
        tec_bid_ids = VendorBid.objects.filter(
            tender__project__committees__committee_type=Committee.Type.TEC,
            tender__project__committees__status="ACTIVE",
            tender__project__committees__members__user=user,
        ).values("id")
        shortlisted_bid_ids = TACVendorShortlist.objects.filter(
            committee__committee_type=Committee.Type.TAC,
            committee__status="ACTIVE",
            committee__members__user=user,
        ).values("financial_document__bid_id")
        return queryset.filter(
            models.Q(id__in=tec_bid_ids)
            | models.Q(id__in=shortlisted_bid_ids)
        ).distinct()

    def create(self, request, *args, **kwargs):
        raise ValidationError({
            "detail": "Upload the technical bid through POST /api/v1/workflow/bids/receive/."
        })

    @action(
        detail=False,
        methods=["post"],
        url_path="receive",
        parser_classes=[MultiPartParser, FormParser],
    )
    @transaction.atomic
    def receive(self, request):
        _require_admin(request.user)
        input_serializer = VendorBidReceiptSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        tender = Tender.objects.select_for_update().select_related("project").get(
            pk=input_serializer.validated_data["tender"].pk
        )
        vendor = input_serializer.validated_data["vendor"]
        latest_submission = _latest_tender_draft(tender.project)
        if not latest_submission or latest_submission.status != StageSubmission.Status.APPROVED:
            raise ValidationError({
                "tender": "The latest tender draft must be approved before recording bids."
            })
        if not Committee.objects.filter(
            project=tender.project,
            committee_type=Committee.Type.TEC,
            status="ACTIVE",
        ).exists():
            raise ValidationError({
                "tender": "The TEC must be approved before recording technical bids."
            })
        if tender.status != Tender.Status.DISTRIBUTED:
            raise ValidationError({"tender": "Record bids only after the tender is distributed."})
        if not tender.dispatches.filter(vendor=vendor).exists():
            raise ValidationError({"vendor": "Record an offline tender dispatch before adding its bid."})
        project_vendor = ProjectVendor.objects.select_for_update().filter(
            project=tender.project,
            vendor=vendor,
        ).first()
        if not project_vendor:
            raise ValidationError({"vendor": "Only selected project vendors can submit bids."})
        bid = VendorBid.objects.select_for_update().filter(
            tender=tender,
            vendor=vendor,
        ).first()
        if bid and bid.documents.filter(
            document_type=BidDocument.Type.TECHNICAL
        ).exists():
            raise ValidationError({"vendor": "A bid for this vendor has already been recorded."})

        if not bid:
            bid = VendorBid.objects.create(
                tender=tender,
                vendor=vendor,
                recorded_by=request.user,
                received_at=timezone.now(),
            )
        documents = [(BidDocument.Type.TECHNICAL, "technical_file")]
        if input_serializer.validated_data.get("financial_file"):
            documents.append((BidDocument.Type.FINANCIAL, "financial_file"))
        for document_type, field_name in documents:
            BidDocument.objects.create(
                bid=bid,
                document_type=document_type,
                version=(bid.documents.filter(
                    document_type=document_type
                ).aggregate(version=Max("version"))["version"] or 0) + 1,
                file=input_serializer.validated_data[field_name],
                uploaded_by=request.user,
            )
        project_vendor.participation_status = "BID_RECEIVED"
        project_vendor.save(update_fields=["participation_status"])
        ProjectActivity.objects.create(
            project=tender.project,
            actor=request.user,
            activity_type="DOCUMENT_UPLOADED",
            message=f"Technical bid recorded from {vendor.vendor_name}.",
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="vendor_bid",
            entity_id=str(bid.id),
            operation="RECORD_RECEIPT",
            new_values={
                "project_code": tender.project.project_code,
                "vendor": vendor.vendor_name,
                "received_at": bid.received_at.isoformat(),
                "documents": {
                    document.document_type: document.file.name.rsplit("/", 1)[-1]
                    for document in bid.documents.filter(
                        document_type__in=[document_type for document_type, _ in documents]
                    )
                },
            },
        )
        return Response(
            self.get_serializer(bid).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="documents",
        parser_classes=[MultiPartParser, FormParser],
    )
    @transaction.atomic
    def upload_document(self, request, pk=None):
        _require_admin(request.user)
        bid = self.get_object()
        document_serializer = BidDocumentSerializer(data=request.data)
        document_serializer.is_valid(raise_exception=True)
        document_type = document_serializer.validated_data["document_type"]
        latest_version = bid.documents.filter(document_type=document_type).aggregate(
            version=Max("version")
        )["version"] or 0
        document = document_serializer.save(
            bid=bid,
            version=latest_version + 1,
            uploaded_by=request.user,
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="bid_document",
            entity_id=str(document.id),
            operation="UPLOAD",
            new_values={"type": document_type, "version": document.version},
        )
        return Response(BidDocumentSerializer(document).data, status=201)

    @action(detail=True, methods=["get"], url_path=r"documents/(?P<document_id>[^/.]+)/download")
    def download_document(self, request, pk=None, document_id=None):
        bid = self.get_object()
        document = bid.documents.filter(id=document_id).first()
        if not document:
            raise NotFound("Bid document not found.")
        if (
            document.document_type == BidDocument.Type.FINANCIAL
            and not _is_admin(request.user)
            and not TACVendorShortlist.objects.filter(
                committee__project=bid.tender.project,
                committee__committee_type=Committee.Type.TAC,
                committee__status="ACTIVE",
                committee__members__user=request.user,
                vendor=bid.vendor,
                financial_document=document,
            ).exists()
        ):
            raise NotFound("Bid document not found.")
        response = FileResponse(document.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{document.file.name.rsplit("/", 1)[-1]}"'
        return response


class TACVendorShortlistViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TACVendorShortlistSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = TACVendorShortlist.objects.select_related(
            "committee__project",
            "vendor",
            "financial_document__bid",
            "selected_by",
        )
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(committee__project_id=project_id)
        if _is_admin(self.request.user):
            return queryset
        return queryset.filter(
            committee__committee_type=Committee.Type.TAC,
            committee__status="ACTIVE",
            committee__members__user=self.request.user,
        ).distinct()

    @action(detail=False, methods=["get", "post"], url_path="final-selection")
    @transaction.atomic
    def final_selection(self, request):
        project_id = request.query_params.get("project") or request.data.get("project")
        try:
            project_id = str(UUID(str(project_id)))
        except (AttributeError, TypeError, ValueError):
            raise ValidationError({"project": "Provide a valid project ID."})

        committee = Committee.objects.select_for_update().filter(
            project_id=project_id,
            committee_type=Committee.Type.TAC,
            status="ACTIVE",
        ).first()
        if not committee:
            raise ValidationError({"project": "An active, SS-approved TAC is required."})
        if not _is_admin(request.user) and not _is_committee_member(committee, request.user):
            raise PermissionDenied("Only Admin and active TAC members can view the final vendor selection.")

        selection = VendorSelection.objects.filter(
            committee=committee,
            status=VendorSelection.Status.SELECTED,
            vendor__isnull=False,
            selected_by__isnull=False,
        ).select_related("vendor").first()
        if request.method == "GET":
            return Response(
                VendorSelectionSerializer(selection).data if selection else None
            )

        _require_admin(request.user)
        if selection:
            raise ValidationError({
                "vendor": "The final vendor has already been selected."
            })
        report_is_complete = ProjectStage.objects.filter(
            project_id=project_id,
            stage_type=ProjectStage.Type.TAC_FINAL_REPORT,
            status=ProjectStage.Status.COMPLETED,
        ).exists() and TACWorkDocument.objects.filter(
            committee=committee,
        ).exists() and ProjectStage.objects.filter(
            project_id=project_id,
            stage_type=ProjectStage.Type.TAC_FINANCIAL_BIDS,
            status=ProjectStage.Status.COMPLETED,
        ).exists()
        if not report_is_complete:
            raise ValidationError({
                "project": "The TAC chair must submit the final TAC report before final vendor selection."
            })

        try:
            vendor_id = str(UUID(str(request.data.get("vendor"))))
        except (AttributeError, TypeError, ValueError):
            raise ValidationError({"vendor": "Select a vendor from the TAC shortlist."})
        shortlist_item = TACVendorShortlist.objects.filter(
            committee=committee,
            vendor_id=vendor_id,
            financial_document__document_type=BidDocument.Type.FINANCIAL,
            financial_document__bid__vendor_id=vendor_id,
            financial_document__bid__tender__project_id=project_id,
        ).select_related("vendor").first()
        if not shortlist_item:
            raise ValidationError({
                "vendor": "The final vendor must be selected from the TAC financial-bid shortlist."
            })

        selection_stage = ProjectStage.objects.filter(
            project_id=project_id,
            stage_type=ProjectStage.Type.VENDOR_SELECTION,
        ).first()
        if not selection_stage:
            selection_stage = _get_or_create_stage_after(
                committee.project,
                request.user,
                ProjectStage.Type.VENDOR_SELECTION,
                ProjectStage.Type.TAC_FINAL_REPORT,
            )
        selection_stage.status = ProjectStage.Status.COMPLETED
        selection_stage.actual_start = selection_stage.actual_start or timezone.now()
        selection_stage.completed_at = timezone.now()
        selection_stage.save(update_fields=[
            "status", "actual_start", "completed_at",
        ])
        selection = VendorSelection.objects.create(
            committee=committee,
            vendor=shortlist_item.vendor,
            selected_by=request.user,
            round_number=(committee.selections.aggregate(
                last_round=Max("round_number")
            )["last_round"] or 0) + 1,
            status=VendorSelection.Status.SELECTED,
        )
        ProjectActivity.objects.create(
            project=committee.project,
            actor=request.user,
            activity_type="STATUS_CHANGED",
            message=f"Admin selected {shortlist_item.vendor.vendor_name} as the final vendor.",
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="vendor_selection",
            entity_id=str(selection.id),
            operation="SELECT_FINAL_VENDOR",
            new_values={
                "project_id": project_id,
                "committee_id": str(committee.id),
                "vendor_id": str(shortlist_item.vendor_id),
                "vendor_name": shortlist_item.vendor.vendor_name,
            },
        )
        for member in committee.members.select_related("user"):
            Notification.objects.create(
                recipient=member.user,
                project=committee.project,
                title="Final vendor selected",
                message=f"Admin selected {shortlist_item.vendor.vendor_name} as the final vendor.",
            )
        return Response(
            VendorSelectionSerializer(selection).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["post"],
        url_path="select",
        parser_classes=[MultiPartParser, FormParser],
    )
    @transaction.atomic
    def select(self, request):
        _require_admin(request.user)
        try:
            project_id = str(UUID(str(request.data.get("project"))))
        except (AttributeError, TypeError, ValueError):
            raise ValidationError({"project": "Provide a valid project ID."})
        committee = Committee.objects.select_for_update().filter(
            project_id=project_id,
            committee_type=Committee.Type.TAC,
            status="ACTIVE",
        ).first()
        if not committee:
            raise ValidationError({"project": "An active, SS-approved TAC is required."})
        if committee.vendor_shortlist.exists():
            raise ValidationError({
                "vendor_ids": "The top-vendor selection and financial bids have already been submitted."
            })
        if committee.selections.exists():
            raise ValidationError({
                "vendor_ids": "The TAC has already started vendor selection."
            })
        report_is_complete = ProjectStage.objects.filter(
            project_id=project_id,
            stage_type=ProjectStage.Type.TEC_REPORT,
            status=ProjectStage.Status.COMPLETED,
        ).exists() and TECWorkDocument.objects.filter(
            committee__project_id=project_id,
            committee__committee_type=Committee.Type.TEC,
            committee__status="ACTIVE",
            document_type=TECWorkDocument.Type.FINAL,
        ).exists()
        if not report_is_complete:
            raise ValidationError({
                "project": "The TEC chair must submit the final TEC report before selecting vendors."
            })
        qualified_vendor_ids = {
            str(vendor_id) for vendor_id in ProjectVendor.objects.filter(
            project_id=project_id,
            qualification_status=ProjectVendor.QualificationStatus.QUALIFIED,
            ).values_list("vendor_id", flat=True)
        }
        technical_bid_vendor_ids = {
            str(vendor_id) for vendor_id in BidDocument.objects.filter(
            bid__tender__project_id=project_id,
            bid__status=VendorBid.Status.RECEIVED,
            document_type=BidDocument.Type.TECHNICAL,
            ).values_list("bid__vendor_id", flat=True)
        }
        eligible_vendor_ids = qualified_vendor_ids & technical_bid_vendor_ids
        if not eligible_vendor_ids:
            raise ValidationError({
                "vendor_ids": "No technically evaluated, qualified vendors are available."
            })
        raw_vendor_ids = (
            request.data.getlist("vendor_ids")
            if hasattr(request.data, "getlist")
            else request.data.get("vendor_ids")
        )
        if not isinstance(raw_vendor_ids, list) or not raw_vendor_ids:
            raise ValidationError({"vendor_ids": "Select vendors based on the TEC report."})
        vendor_ids = []
        for value in raw_vendor_ids:
            try:
                vendor_ids.append(str(UUID(str(value))))
            except (AttributeError, TypeError, ValueError):
                raise ValidationError({"vendor_ids": "One or more vendor IDs are invalid."})
        if len(vendor_ids) != len(set(vendor_ids)):
            raise ValidationError({"vendor_ids": "A vendor can only be selected once."})
        required_count = min(3, len(eligible_vendor_ids))
        if len(vendor_ids) != required_count:
            raise ValidationError({
                "vendor_ids": f"Select exactly {required_count} vendor(s), based on the TEC report."
            })
        if not set(vendor_ids).issubset(eligible_vendor_ids):
            raise ValidationError({
                "vendor_ids": "Only technically evaluated, qualified vendors can be selected."
            })
        vendors_by_id = {
            str(vendor.id): vendor
            for vendor in Vendor.objects.filter(id__in=vendor_ids)
        }
        prepared_bids = []
        for vendor_id in vendor_ids:
            uploaded_file = request.FILES.get(f"financial_file_{vendor_id}")
            if not uploaded_file:
                raise ValidationError({
                    f"financial_file_{vendor_id}": "Upload this vendor's financial bid PDF."
                })
            document_serializer = BidDocumentSerializer(
                data={
                    "document_type": BidDocument.Type.FINANCIAL,
                    "file": uploaded_file,
                },
                context={"request": request},
            )
            document_serializer.is_valid(raise_exception=True)
            bid = VendorBid.objects.select_for_update().get(
                tender__project_id=project_id,
                vendor_id=vendor_id,
                status=VendorBid.Status.RECEIVED,
            )
            prepared_bids.append((vendor_id, bid, document_serializer.validated_data["file"]))

        shortlist_stage = _get_or_create_stage_after(
            committee.project,
            request.user,
            ProjectStage.Type.TAC_FINANCIAL_BIDS,
            ProjectStage.Type.TAC_FORMATION,
        )
        _validate_stage_is_ready(shortlist_stage)
        shortlist = []
        for vendor_id, bid, financial_file in prepared_bids:
            latest_version = bid.documents.filter(
                document_type=BidDocument.Type.FINANCIAL,
            ).aggregate(version=Max("version"))["version"] or 0
            document = BidDocument.objects.create(
                bid=bid,
                document_type=BidDocument.Type.FINANCIAL,
                version=latest_version + 1,
                file=financial_file,
                uploaded_by=request.user,
            )
            shortlist.append(TACVendorShortlist.objects.create(
                committee=committee,
                vendor=vendors_by_id[vendor_id],
                financial_document=document,
                selected_by=request.user,
            ))

        shortlist_stage.status = ProjectStage.Status.COMPLETED
        shortlist_stage.completed_at = timezone.now()
        if not shortlist_stage.actual_start:
            shortlist_stage.actual_start = shortlist_stage.completed_at
        shortlist_stage.save(update_fields=[
            "status", "actual_start", "completed_at",
        ])
        selected_names = [item.vendor.vendor_name for item in shortlist]
        ProjectActivity.objects.create(
            project=committee.project,
            actor=request.user,
            activity_type="DOCUMENT_UPLOADED",
            message=(
                "Admin selected the TAC financial-bid shortlist based on the TEC report: "
                + ", ".join(selected_names)
            ),
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="tac_vendor_shortlist",
            entity_id=str(committee.id),
            operation="SELECT_TOP_VENDORS",
            new_values={
                "project_id": project_id,
                "committee_id": str(committee.id),
                "vendors": [
                    {
                        "vendor_id": str(item.vendor_id),
                        "vendor_name": item.vendor.vendor_name,
                        "financial_document_id": str(item.financial_document_id),
                    }
                    for item in shortlist
                ],
            },
        )
        for member in committee.members.select_related("user"):
            Notification.objects.create(
                recipient=member.user,
                project=committee.project,
                title="TAC financial bids are available",
                message=(
                    "Admin selected vendors based on the TEC report and uploaded their "
                    "financial bids for TAC review."
                ),
            )
        return Response(
            self.get_serializer(shortlist, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class TACWorkDocumentViewSet(viewsets.ModelViewSet):
    serializer_class = TACWorkDocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = TACWorkDocument.objects.select_related(
            "committee__project", "uploaded_by"
        ).filter(
            committee__committee_type=Committee.Type.TAC,
            committee__status="ACTIVE",
        )
        if not _is_admin(self.request.user):
            queryset = queryset.filter(committee__members__user=self.request.user)
        committee_id = self.request.query_params.get("committee")
        if committee_id:
            queryset = queryset.filter(committee_id=committee_id)
        project_id = self.request.query_params.get("project")
        if project_id:
            queryset = queryset.filter(committee__project_id=project_id)
        return queryset.distinct()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        committee = Committee.objects.select_for_update().select_related(
            "project",
        ).get(pk=serializer.validated_data["committee"].pk)
        if committee.committee_type != Committee.Type.TAC:
            raise ValidationError({"committee": "Choose a TAC committee."})
        if committee.status != "ACTIVE":
            raise ValidationError({
                "committee": "The TAC must be approved before submitting its final report."
            })
        if not _is_committee_member(committee, request.user):
            raise PermissionDenied("Only TAC members can upload committee documents.")
        if committee.chair_id != request.user.id:
            raise PermissionDenied("Only the TAC chair can upload the final TAC report.")
        financial_bids_stage = ProjectStage.objects.filter(
            project=committee.project,
            stage_type=ProjectStage.Type.TAC_FINANCIAL_BIDS,
            status=ProjectStage.Status.COMPLETED,
        ).first()
        if not financial_bids_stage:
            raise ValidationError({
                "committee": "Admin must submit the financial bids before the TAC final report."
            })
        report_stage = _get_or_create_stage_after(
            committee.project,
            request.user,
            ProjectStage.Type.TAC_FINAL_REPORT,
            ProjectStage.Type.TAC_FINANCIAL_BIDS,
        )
        latest_version = TACWorkDocument.objects.filter(
            committee=committee,
        ).aggregate(max_version=Max("version"))["max_version"] or 0
        document = serializer.save(
            committee=committee,
            version=latest_version + 1,
            uploaded_by=request.user,
        )
        report_stage.status = ProjectStage.Status.COMPLETED
        report_stage.completed_at = timezone.now()
        if not report_stage.actual_start:
            report_stage.actual_start = report_stage.completed_at
        report_stage.save(update_fields=["status", "actual_start", "completed_at"])
        ProjectActivity.objects.create(
            project=committee.project,
            actor=request.user,
            activity_type="DOCUMENT_UPLOADED",
            message=(
                f"{committee.committee_name} submitted its final report "
                f"(version {document.version})."
            ),
        )
        AuditLog.objects.create(
            user=request.user,
            entity_type="tac_work_document",
            entity_id=str(document.id),
            operation="UPLOAD",
            new_values={
                "committee": str(committee.id),
                "version": document.version,
                "file": document.file.name.rsplit("/", 1)[-1],
            },
        )
        Notification.objects.create(
            recipient=committee.project.created_by,
            project=committee.project,
            title="Final TAC report submitted",
            message=(
                f"{committee.committee_name} submitted its final report. "
                "It is available to download in the project workflow."
            ),
        )
        return Response(
            self.get_serializer(document).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        document = self.get_object()
        response = FileResponse(document.file.open("rb"), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{document.file.name.rsplit("/", 1)[-1]}"'
        )
        return response


class NegotiationMessageViewSet(viewsets.ModelViewSet):
    serializer_class = NegotiationMessageSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = NegotiationMessage.objects.select_related("project", "vendor", "recorded_by")
        user = self.request.user
        if _is_admin(user):
            return queryset
        return queryset.filter(
            models.Q(project__created_by=user)
            | models.Q(project__members__user=user)
            | models.Q(
                project__committees__status="ACTIVE",
                project__committees__members__user=user,
            )
        ).distinct()

    def perform_create(self, serializer):
        _require_admin(self.request.user)
        project = serializer.validated_data["project"]
        vendor = serializer.validated_data["vendor"]
        if not VendorSelection.objects.filter(
            committee__project=project,
            status=VendorSelection.Status.SELECTED,
            vendor=vendor,
        ).exists():
            raise ValidationError({"vendor": "Negotiation can only be recorded with the selected vendor."})
        message = serializer.save(recorded_by=self.request.user)
        ProjectActivity.objects.create(
            project=project,
            actor=self.request.user,
            activity_type="MESSAGE",
            message=f"Negotiation {message.direction.lower()}: {message.message}",
        )
        AuditLog.objects.create(
            user=self.request.user,
            entity_type="negotiation",
            entity_id=str(message.id),
            operation=message.direction,
        )


class WorkflowDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        visible_projects = ProcurementProject.objects.all()
        if not _is_admin(user):
            visible_projects = visible_projects.filter(
                models.Q(created_by=user)
                | models.Q(members__user=user)
                | models.Q(committees__status="ACTIVE", committees__members__user=user)
                | models.Q(id__in=_projects_visible_to_approver(user))
            ).distinct()
        stages = ProjectStage.objects.filter(project__in=visible_projects).select_related(
            "project"
        ).order_by("due_date", "sequence")
        pending_steps = ApprovalStep.objects.filter(
            status__in=[ApprovalStep.Status.PENDING, ApprovalStep.Status.QUERY]
        ).filter(
            models.Q(assigned_user=user)
            | models.Q(approver_role__in=user.roles.values_list("name", flat=True))
        )
        review_types = []
        if has_any_role(user, "SS"):
            review_types.extend([
                StageSubmission.Type.TSC_FORMATION,
                StageSubmission.Type.TEC_FORMATION,
                StageSubmission.Type.TAC_FORMATION,
            ])
        if has_any_role(user, "AS"):
            review_types.append(StageSubmission.Type.TSC_REPORT)
        if has_any_role(user, "HQ"):
            review_types.extend([
                StageSubmission.Type.TSC_REPORT,
                StageSubmission.Type.TEC_REPORT,
            ])
        if has_any_role(user, "DGS"):
            review_types.append(StageSubmission.Type.TSC_REPORT_LEVEL3)
        if has_any_role(user, "IA_WING"):
            review_types.append(StageSubmission.Type.TENDER_DRAFT)
        if review_types:
            review_filter = models.Q(
                request__submission__submission_type__in=review_types,
                status=ApprovalStep.Status.PENDING,
            )
            if has_any_role(user, "SS"):
                review_filter |= models.Q(
                    request__submission__submission_type__in=[
                        StageSubmission.Type.TSC_FORMATION,
                        StageSubmission.Type.TEC_FORMATION,
                        StageSubmission.Type.TAC_FORMATION,
                    ],
                    status=ApprovalStep.Status.QUERY,
                )
            pending_steps = pending_steps.filter(review_filter)
        else:
            pending_steps = pending_steps.exclude(
                request__submission__submission_type__in=[
                    StageSubmission.Type.TSC_FORMATION,
                    StageSubmission.Type.TEC_FORMATION,
                    StageSubmission.Type.TAC_FORMATION,
                    StageSubmission.Type.TSC_REPORT,
                    StageSubmission.Type.TSC_REPORT_LEVEL3,
                    StageSubmission.Type.TEC_REPORT,
                ]
            )
        pending_steps = pending_steps.select_related(
            "request__submission__stage__project__department",
            "request__submission__stage__project__created_by",
            "request__submission__committee__chair",
            "assigned_user",
        ).prefetch_related("request__submission__committee__members__user")
        now = timezone.localdate()
        pending_approvals = []
        for step in pending_steps:
            submission = step.request.submission
            project = submission.stage.project
            committee = submission.committee
            committee_details = None
            if committee:
                committee_details = {
                    "id": str(committee.id),
                    "name": committee.committee_name,
                    "type": committee.committee_type,
                    "chair": {
                        "name": committee.chair.name,
                        "email": committee.chair.email,
                    } if committee.chair_id else None,
                    "members": [{
                        "name": member.user.name,
                        "email": member.user.email,
                        "designation": member.designation,
                    } for member in committee.members.all()],
                }
            pending_approvals.append({
                "id": step.id,
                "request_id": step.request_id,
                "submission_id": str(submission.id),
                "submission_type": submission.submission_type,
                "title": submission.title,
                "comments": submission.comments,
                "expected_vendor_dispatch_date": submission.expected_vendor_dispatch_date,
                "expected_bid_receipt_date": submission.expected_bid_receipt_date,
                "expected_product_arrival_date": submission.expected_product_arrival_date,
                "submitted_by": submission.submitted_by.name,
                "submitted_at": submission.created_at,
                "file_url": (
                    f"/api/v1/workflow/submissions/{submission.id}/download/"
                    if submission.file else None
                ),
                "project_id": str(project.id),
                "project_code": project.project_code,
                "project": {
                    "title": project.title,
                    "description": project.description,
                    "department": project.department.department_name,
                    "estimated_amount": str(project.estimated_amount),
                    "status": project.current_status,
                    "created_by": project.created_by.name,
                    "created_at": project.created_at,
                    "updated_at": project.updated_at,
                },
                "committee": committee_details,
                "sequence": step.sequence,
                "approver_role": step.approver_role,
                "step_status": step.status,
                "due_date": submission.stage.due_date,
                "overdue": bool(
                    submission.stage.due_date
                    and submission.stage.due_date < now
                ),
            })
        data = {
            "stages": ProjectStageSerializer(stages, many=True).data,
            "pending_approvals": pending_approvals,
            "committee_assignments": [
                {
                    "project_id": str(committee.project_id),
                    "project_code": committee.project.project_code,
                    "project_title": committee.project.title,
                    "committee_id": str(committee.id),
                    "committee_name": committee.committee_name,
                    "committee_type": committee.committee_type,
                    "is_chair": committee.chair_id == user.id,
                }
                for committee in Committee.objects.filter(
                    status="ACTIVE",
                    members__user=user,
                ).select_related("project").distinct().order_by(
                    "project__project_code", "committee_type"
                )
            ],
            "overdue_stages": sum(
                1 for stage in stages
                if stage.due_date and stage.due_date < now
                and stage.status not in {ProjectStage.Status.COMPLETED, ProjectStage.Status.CANCELLED}
            ),
        }
        return Response(data)
