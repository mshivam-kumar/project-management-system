from django.db import models, transaction
from django.utils import timezone
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrSuperAdmin, has_any_role
from apps.committees.models import Committee, CommitteeMember
from apps.audit.models import AuditLog
from apps.documents.models import Document, DocumentVersion
from apps.notifications.models import Notification
from apps.workflow.models import (
    ApprovalEvent,
    ApprovalRequest,
    ApprovalStep,
    BidDocument,
    ProjectStage,
    StageSubmission,
    TECWorkDocument,
    VendorBid,
)
from .models import ProcurementProject, ProjectActivity, ProjectMessage, ProjectMember
from .serializers import (
    ActivitySerializer,
    MessageSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
    ProjectVendorRemovalSerializer,
    ProjectVendorSelectionSerializer,
)
from apps.vendors.models import ProjectVendor, Vendor


def _selected_project_vendors(project):
    return [
        {
            "vendor_id": str(item.vendor_id),
            "vendor_name": item.vendor.vendor_name,
            "products_services": item.vendor.products_services,
            "category_names": list(
                item.vendor.categories.order_by("name").values_list("name", flat=True)
            ),
            "participation_status": item.participation_status,
            "selected_at": item.created_at,
        }
        for item in ProjectVendor.objects.filter(
            project=project,
            participation_status__in=["SELECTED", "TENDER_SENT", "BID_RECEIVED"],
        )
        .select_related("vendor").prefetch_related("vendor__categories")
        .order_by("created_at")
    ]


def _project_vendor_workflow_status(project):
    latest_level3_report = StageSubmission.objects.filter(
        stage__project=project,
        submission_type=StageSubmission.Type.TSC_REPORT_LEVEL3,
    ).order_by("-revision").first()
    latest_tender_draft = StageSubmission.objects.filter(
        stage__project=project,
        submission_type=StageSubmission.Type.TENDER_DRAFT,
    ).order_by("-revision").first()
    level3_approved = bool(
        latest_level3_report
        and latest_level3_report.status == StageSubmission.Status.APPROVED
    )
    return {
        "level3_report_approved": level3_approved,
        "tender_draft_approved": bool(
            level3_approved
            and latest_tender_draft
            and latest_tender_draft.status == StageSubmission.Status.APPROVED
        ),
    }


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class=ProjectSerializer
    permission_classes=[IsAuthenticated]
    search_fields=["project_code","title","description"]
    filterset_fields=["current_status","department"]
    ordering_fields=["created_at","updated_at","estimated_amount","title"]

    def get_queryset(self):
        qs=ProcurementProject.objects.select_related("department","created_by").prefetch_related("members__user")
        user=self.request.user
        if has_any_role(user,"ADMIN","SUPER_ADMIN"): return qs
        review_types = []
        if has_any_role(user, "AS"):
            review_types.append(StageSubmission.Type.TSC_REPORT)
        if has_any_role(user, "SS"):
            review_types.extend([
                StageSubmission.Type.TSC_FORMATION,
                StageSubmission.Type.TEC_FORMATION,
                StageSubmission.Type.TAC_FORMATION,
            ])
        if has_any_role(user, "DGS"):
            review_types.append(StageSubmission.Type.TSC_REPORT_LEVEL3)
        if has_any_role(user, "IA_WING"):
            review_types.append(StageSubmission.Type.TENDER_DRAFT)
        approval_filters = {
            "workflow_stages__submissions__approval_requests__steps__status":
                ApprovalStep.Status.PENDING,
        } if review_types else {
            "workflow_stages__submissions__approval_requests__steps__status__in": [
                ApprovalStep.Status.PENDING,
                ApprovalStep.Status.QUERY,
            ],
        }
        if review_types:
            approval_filters["workflow_stages__submissions__submission_type__in"] = review_types
        approval_projects=ProcurementProject.objects.filter(**approval_filters).filter(
            models.Q(
                workflow_stages__submissions__approval_requests__steps__assigned_user=user
            )
            | models.Q(
                workflow_stages__submissions__approval_requests__steps__approver_role__in=
                user.roles.values_list("name",flat=True)
            )
        ).values("id")
        reviewed_projects=ProcurementProject.objects.filter(
            workflow_stages__submissions__approval_requests__events__actor=user,
            workflow_stages__submissions__approval_requests__status__in=[
                ApprovalRequest.Status.APPROVED,
                ApprovalRequest.Status.REJECTED,
            ],
        )
        if review_types:
            reviewed_projects=reviewed_projects.filter(
                workflow_stages__submissions__submission_type__in=review_types
            )
        reviewed_projects=reviewed_projects.values("id")
        visible_to_user = (
            models.Q(created_by=user)
            | models.Q(members__user=user)
            | models.Q(committees__status="ACTIVE", committees__members__user=user)
        )
        if self.request.method in {"GET", "HEAD", "OPTIONS"}:
            visible_to_user |= (
                models.Q(id__in=approval_projects)
                | models.Q(id__in=reviewed_projects)
            )
        return qs.filter(visible_to_user).distinct()

    @transaction.atomic
    def perform_create(self,serializer):
        project=serializer.save(created_by=self.request.user)
        ProjectStage.objects.create(
            project=project,
            stage_type=ProjectStage.Type.TSC_FORMATION,
            sequence=1,
            created_by=self.request.user,
        )
        ProjectActivity.objects.create(project=project,actor=self.request.user,activity_type="PROJECT_CREATED",message="Project created")
        AuditLog.objects.create(user=self.request.user,entity_type="project",entity_id=str(project.id),operation="CREATE",new_values={"project_code":project.project_code,"title":project.title})

    @transaction.atomic
    def perform_update(self,serializer):
        project=serializer.save()
        ProjectActivity.objects.create(project=project,actor=self.request.user,activity_type="PROJECT_UPDATED",message="Project details updated")
        AuditLog.objects.create(user=self.request.user,entity_type="project",entity_id=str(project.id),operation="UPDATE",new_values={"title":project.title,"description":project.description})

    @action(detail=True, methods=["get", "post", "delete"], url_path="vendors")
    @transaction.atomic
    def vendors(self, request, pk=None):
        project = self.get_object()
        if request.method == "GET":
            is_tec_member = CommitteeMember.objects.filter(
                committee__project=project,
                committee__committee_type=Committee.Type.TEC,
                committee__status="ACTIVE",
                user=request.user,
            ).exists()
            if not has_any_role(request.user, "ADMIN", "SUPER_ADMIN") and not is_tec_member:
                raise PermissionDenied("Only project administrators and active TEC members can view selected vendors.")
            return Response({
                **_project_vendor_workflow_status(project),
                "vendors": _selected_project_vendors(project),
            })

        if not has_any_role(request.user, "ADMIN", "SUPER_ADMIN"):
            raise PermissionDenied("Administrator access is required.")

        if request.method == "POST":
            workflow_status = _project_vendor_workflow_status(project)
            if not workflow_status["level3_report_approved"]:
                raise ValidationError({
                    "tsc_report_level3": "DGS must approve the TSC report before vendor selection."
                })
            if not workflow_status["tender_draft_approved"]:
                raise ValidationError({
                    "tender_draft": "Vendors can be selected after the latest tender draft is approved."
                })
            input_serializer = ProjectVendorSelectionSerializer(data=request.data)
            input_serializer.is_valid(raise_exception=True)
            vendor_ids = input_serializer.validated_data["vendor_ids"]
            vendors = Vendor.objects.filter(
                id__in=vendor_ids,
                is_active=True,
                verification_status=Vendor.Status.VERIFIED,
            )
            if vendors.count() != len(vendor_ids):
                raise ValidationError({
                    "vendor_ids": "All selected vendors must be active and verified."
                })

            for vendor in vendors:
                selection, created = ProjectVendor.objects.get_or_create(
                    project=project,
                    vendor=vendor,
                    defaults={"participation_status": "SELECTED"},
                )
                previous_status = selection.participation_status
                status_changed = (
                    not created
                    and previous_status not in {
                        "SELECTED",
                        "TENDER_SENT",
                        "BID_RECEIVED",
                    }
                )
                if status_changed:
                    selection.participation_status = "SELECTED"
                    selection.save(update_fields=["participation_status"])
                if created or status_changed:
                    AuditLog.objects.create(
                        user=request.user,
                        entity_type="project_vendor",
                        entity_id=str(selection.id),
                        operation="SELECT",
                        old_values=(
                            {"participation_status": previous_status}
                            if status_changed else {}
                        ),
                        new_values={
                            "project_code": project.project_code,
                            "vendor_name": vendor.vendor_name,
                        },
                    )
            return Response({
                **workflow_status,
                "vendors": _selected_project_vendors(project),
            })

        input_serializer = ProjectVendorRemovalSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        vendor_id = input_serializer.validated_data["vendor_id"]
        selection = ProjectVendor.objects.filter(
            project=project,
            vendor_id=vendor_id,
            participation_status="SELECTED",
        ).select_related("vendor").first()
        if not selection:
            raise NotFound("Selected vendor not found.")
        AuditLog.objects.create(
            user=request.user,
            entity_type="project_vendor",
            entity_id=str(selection.id),
            operation="DESELECT",
            old_values={
                "project_code": project.project_code,
                "vendor_name": selection.vendor.vendor_name,
            },
        )
        selection.delete()
        return Response({
            **_project_vendor_workflow_status(project),
            "vendors": _selected_project_vendors(project),
        })

    @action(detail=True, methods=["get", "post"], url_path="qualified-vendors")
    @transaction.atomic
    def qualified_vendors(self, request, pk=None):
        project = self.get_object()
        if not has_any_role(request.user, "ADMIN", "SUPER_ADMIN"):
            raise PermissionDenied("Administrator access is required.")

        selected = list(
            ProjectVendor.objects.filter(
                project=project,
                participation_status__in=["SELECTED", "TENDER_SENT", "BID_RECEIVED"],
            ).select_related("vendor", "qualification_decided_by").order_by("created_at")
        )
        technical_vendor_ids = set(
            VendorBid.objects.filter(
                tender__project=project,
                status=VendorBid.Status.RECEIVED,
                documents__document_type=BidDocument.Type.TECHNICAL,
            ).values_list("vendor_id", flat=True).distinct()
        )
        final_report = TECWorkDocument.objects.filter(
            committee__project=project,
            committee__committee_type=Committee.Type.TEC,
            committee__status="ACTIVE",
            document_type=TECWorkDocument.Type.FINAL,
        ).order_by("-version").first()
        report_stage = ProjectStage.objects.filter(
            project=project,
            stage_type=ProjectStage.Type.TEC_REPORT,
            status=ProjectStage.Status.COMPLETED,
        ).first()
        every_vendor_has_bid = bool(selected) and all(
            item.vendor_id in technical_vendor_ids for item in selected
        )
        can_qualify = bool(final_report and report_stage and every_vendor_has_bid)
        qualification_stage = ProjectStage.objects.filter(
            project=project,
            stage_type=ProjectStage.Type.VENDOR_QUALIFICATION,
        ).first()

        if request.method == "GET":
            return Response({
                "can_qualify": can_qualify,
                "qualification_complete": bool(
                    qualification_stage
                    and qualification_stage.status == ProjectStage.Status.COMPLETED
                ),
                "final_report_received": bool(final_report and report_stage),
                "vendors": [
                    {
                        "vendor_id": str(item.vendor_id),
                        "vendor_name": item.vendor.vendor_name,
                        "technical_bid_received": item.vendor_id in technical_vendor_ids,
                        "qualification_status": item.qualification_status,
                        "qualification_decided_at": item.qualification_decided_at,
                        "qualification_decided_by": (
                            item.qualification_decided_by.name
                            if item.qualification_decided_by else None
                        ),
                    }
                    for item in selected
                ],
            })

        if qualification_stage and qualification_stage.status == ProjectStage.Status.COMPLETED:
            raise ValidationError({
                "qualification": "Vendor qualification is complete and can no longer be changed."
            })
        if not final_report or not report_stage:
            raise ValidationError({
                "tec_report": "The TEC chair must submit the final report before vendor qualification."
            })
        if not every_vendor_has_bid:
            raise ValidationError({
                "technical_bids": "A technical bid is required for every selected vendor before qualification."
            })

        from apps.workflow.views import _get_or_create_stage_after

        input_serializer = ProjectVendorSelectionSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        qualified_vendor_ids = set(input_serializer.validated_data["vendor_ids"])
        eligible_vendor_ids = {item.vendor_id for item in selected} & technical_vendor_ids
        if not qualified_vendor_ids.issubset(eligible_vendor_ids):
            raise ValidationError({
                "vendor_ids": "Only selected vendors with a received technical bid can be qualified."
            })

        previous_qualified = [
            item.vendor.vendor_name
            for item in selected
            if item.qualification_status == ProjectVendor.QualificationStatus.QUALIFIED
        ]
        decided_at = timezone.now()
        for item in selected:
            item.qualification_status = (
                ProjectVendor.QualificationStatus.QUALIFIED
                if item.vendor_id in qualified_vendor_ids
                else ProjectVendor.QualificationStatus.NOT_QUALIFIED
            )
            item.qualification_decided_by = request.user
            item.qualification_decided_at = decided_at
            item.save(update_fields=[
                "qualification_status",
                "qualification_decided_by",
                "qualification_decided_at",
            ])

        stage = _get_or_create_stage_after(
            project,
            request.user,
            ProjectStage.Type.VENDOR_QUALIFICATION,
            ProjectStage.Type.TEC_REPORT,
        )
        stage.status = ProjectStage.Status.COMPLETED
        stage.actual_start = stage.actual_start or decided_at
        stage.completed_at = decided_at
        stage.save(update_fields=["status", "actual_start", "completed_at"])
        _get_or_create_stage_after(
            project,
            request.user,
            ProjectStage.Type.TAC_FORMATION,
            ProjectStage.Type.VENDOR_QUALIFICATION,
        )
        qualified_names = [
            item.vendor.vendor_name
            for item in selected
            if item.vendor_id in qualified_vendor_ids
        ]
        AuditLog.objects.create(
            user=request.user,
            entity_type="vendor_qualification",
            entity_id=str(project.id),
            operation="UPDATE",
            old_values={"qualified_vendors": previous_qualified},
            new_values={
                "qualified_vendors": qualified_names,
                "decided_at": decided_at.isoformat(),
            },
        )
        ProjectActivity.objects.create(
            project=project,
            actor=request.user,
            activity_type=ProjectActivity.Type.STATUS_CHANGED,
            message=f"Qualified vendors: {', '.join(qualified_names)}",
        )
        return Response({
            "can_qualify": True,
            "qualification_complete": True,
            "final_report_received": True,
            "vendors": [
                {
                    "vendor_id": str(item.vendor_id),
                    "vendor_name": item.vendor.vendor_name,
                    "technical_bid_received": item.vendor_id in technical_vendor_ids,
                    "qualification_status": item.qualification_status,
                    "qualification_decided_at": item.qualification_decided_at,
                    "qualification_decided_by": request.user.name,
                }
                for item in selected
            ],
        })

    @action(detail=True,methods=["get"])
    def activities(self,request,pk=None):
        project=self.get_object()
        qs=project.activities.select_related("actor").prefetch_related("document_set").all()
        return Response(ActivitySerializer(qs,many=True).data)

    @action(detail=True,methods=["post"])
    @transaction.atomic
    def messages(self,request,pk=None):
        project=self.get_object(); serializer=MessageSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        message=serializer.save(project=project,sender=request.user)
        ProjectActivity.objects.create(project=project,actor=request.user,activity_type="MESSAGE",message=message.message)
        AuditLog.objects.create(user=request.user,entity_type="project",entity_id=str(project.id),operation="MESSAGE",new_values={"message_id":str(message.id)})
        return Response(MessageSerializer(message).data,status=201)

    @action(detail=True,methods=["get","post"],parser_classes=[MultiPartParser,FormParser])
    @transaction.atomic
    def documents(self,request,pk=None):
        project=self.get_object()
        if request.method=="GET":
            rows=project.documents.select_related("uploaded_by").all()
            return Response([{"id":str(d.id),"document_name":d.document_name,"file_size":d.file_size,"uploaded_by":d.uploaded_by.name,"created_at":d.created_at,"download_url":f"/api/v1/projects/{project.id}/documents/{d.id}/download/"} for d in rows])
        uploaded=request.FILES.get("file")
        if not uploaded: raise ValidationError({"file":"PDF file is required."})
        if uploaded.size>10*1024*1024: raise ValidationError({"file":"Maximum file size is 10 MB."})
        if uploaded.content_type!="application/pdf" or not uploaded.name.lower().endswith(".pdf"):
            raise ValidationError({"file":"Only PDF files are accepted."})
        if uploaded.read(5)!=b"%PDF-": raise ValidationError({"file":"The uploaded file is not a valid PDF."})
        uploaded.seek(0)
        document_id=request.data.get("document_id")
        if document_id:
            document=project.documents.filter(id=document_id).first()
            if not document: raise NotFound("Document not found")
            version_number=(document.versions.order_by("-version_number").values_list("version_number",flat=True).first() or 0)+1
            activity_type="DOCUMENT_UPDATED"
        else:
            document=Document.objects.create(project=project,uploaded_by=request.user,document_name=uploaded.name,document_type="PDF",mime_type="application/pdf",file_size=uploaded.size)
            version_number=1; activity_type="DOCUMENT_UPLOADED"
        version=DocumentVersion.objects.create(document=document,version_number=version_number,uploaded_by=request.user,storage_path=uploaded)
        activity=ProjectActivity.objects.create(project=project,actor=request.user,activity_type=activity_type,message=f"{('Updated' if version_number>1 else 'Uploaded')} {document.document_name}")
        document.activity=activity; document.save(update_fields=["activity"])
        AuditLog.objects.create(user=request.user,entity_type="document",entity_id=str(document.id),operation=activity_type,new_values={"version":version_number,"name":document.document_name})
        for recipient_id in project.members.exclude(user=request.user).values_list("user_id",flat=True):
            Notification.objects.create(recipient_id=recipient_id,project=project,title="Project document updated",message=f"{document.document_name} was added to {project.project_code}.")
        return Response({"id":str(document.id),"name":document.document_name,"version":version.version_number},status=201)

    @action(detail=True,methods=["get"],url_path=r"documents/(?P<document_id>[^/.]+)/download")
    def download_document(self,request,pk=None,document_id=None):
        project=self.get_object(); document=project.documents.filter(id=document_id).first()
        if not document: raise NotFound("Document not found")
        version=document.versions.order_by("-version_number").first()
        if not version: raise NotFound("Document file not found")
        response=FileResponse(version.storage_path.open("rb"),content_type="application/pdf")
        response["Content-Disposition"]=f'attachment; filename="{document.document_name}"'
        return response

    @action(detail=True,methods=["get","post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin])
    @transaction.atomic
    def members(self,request,pk=None):
        project=self.get_object()
        if request.method=="GET": return Response(ProjectMemberSerializer(project.members.select_related("user").all(),many=True).data)
        try: user=User.objects.get(id=request.data.get("user"),is_active=True,verification_status="VERIFIED")
        except User.DoesNotExist: raise ValidationError({"user":"Choose an active, verified user."})
        membership,_=ProjectMember.objects.get_or_create(project=project,user=user,defaults={"assigned_by":request.user})
        AuditLog.objects.create(user=request.user,entity_type="project",entity_id=str(project.id),operation="ASSIGN_MEMBER",new_values={"user":str(user.id)})
        Notification.objects.create(recipient=user,project=project,title="Project assigned",message=f"You were assigned to {project.project_code}: {project.title}.")
        return Response(ProjectMemberSerializer(membership).data,status=201)

from rest_framework.views import APIView
from django.db.models import Count, Q
from apps.accounts.models import User
from apps.departments.models import Department
from apps.vendors.models import ProjectVendor, Vendor
from apps.audit.models import AuditLog

class DashboardSummaryView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        admin=has_any_role(request.user,"ADMIN","SUPER_ADMIN")
        if admin:
            projects=ProcurementProject.objects.all()
        elif has_any_role(request.user, "SS", "AS", "DGS", "IA_WING"):
            review_types = []
            if has_any_role(request.user, "SS"):
                review_types.append(StageSubmission.Type.TSC_FORMATION)
            if has_any_role(request.user, "AS"):
                review_types.append(StageSubmission.Type.TSC_REPORT)
            if has_any_role(request.user, "DGS"):
                review_types.append(StageSubmission.Type.TSC_REPORT_LEVEL3)
            if has_any_role(request.user, "IA_WING"):
                review_types.append(StageSubmission.Type.TENDER_DRAFT)
            projects=ProcurementProject.objects.filter(
                workflow_stages__submissions__submission_type__in=review_types,
                workflow_stages__submissions__approval_requests__steps__status=ApprovalStep.Status.PENDING,
            ).filter(
                Q(
                    workflow_stages__submissions__approval_requests__steps__assigned_user=request.user
                )
                | Q(
                    workflow_stages__submissions__approval_requests__steps__approver_role__in=
                    request.user.roles.values_list("name", flat=True)
                )
            ).distinct()
        else:
            projects=ProcurementProject.objects.filter(
                Q(created_by=request.user)|Q(members__user=request.user)
            ).distinct()
        result={
            "total_projects":projects.count(),
            "active_projects":projects.exclude(current_status__in=["APPROVED","REJECTED","CANCELLED"]).count(),
            "approved_projects":projects.filter(current_status="APPROVED").count(),
            "pending_actions":(
                projects.count()
                if has_any_role(request.user, "SS", "AS", "DGS", "IA_WING")
                else projects.filter(
                    current_status__in=["SUBMITTED","UNDER_REVIEW","PENDING_APPROVAL"]
                ).count()
            ),
        }
        if admin:
            result.update({
                "total_users":User.objects.count(),
                "pending_user_verifications":User.objects.filter(verification_status="PENDING").count(),
                "total_vendors":Vendor.objects.count(),
                "pending_vendor_verifications":Vendor.objects.filter(verification_status="PENDING").count(),
                "total_departments":Department.objects.count(),
                "total_admins":User.objects.filter(roles__name="ADMIN").distinct().count(),
                "recent_admin_activities":[{"operation":x.operation,"entity_type":x.entity_type,"created_at":x.created_at,"actor":x.user.name if x.user else "System"} for x in AuditLog.objects.select_related("user").order_by("-created_at")[:8]],
            })
        return Response(result)
