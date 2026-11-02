from django.db import models, transaction
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrSuperAdmin, has_any_role
from apps.audit.models import AuditLog
from apps.documents.models import Document, DocumentVersion
from apps.vendors.models import Vendor, ProjectVendor
from apps.notifications.models import Notification
from .models import ProcurementProject, ProjectActivity, ProjectMessage, ProjectMember
from .serializers import ProjectSerializer, ActivitySerializer, MessageSerializer, ProjectMemberSerializer

class ProjectViewSet(viewsets.ModelViewSet):
    http_method_names=["get","post","patch","head","options"]
    serializer_class=ProjectSerializer
    permission_classes=[IsAuthenticated]
    search_fields=["project_code","title","description"]
    filterset_fields=["current_status","department"]
    ordering_fields=["created_at","updated_at","estimated_amount","title"]

    def get_queryset(self):
        qs=ProcurementProject.objects.select_related("department","created_by").prefetch_related("members__user")
        user=self.request.user
        if has_any_role(user,"ADMIN","SUPER_ADMIN"): return qs
        return qs.filter(models.Q(created_by=user)|models.Q(members__user=user)).distinct()

    @transaction.atomic
    def perform_create(self,serializer):
        project=serializer.save(created_by=self.request.user)
        ProjectActivity.objects.create(project=project,actor=self.request.user,activity_type="PROJECT_CREATED",message="Project created")
        AuditLog.objects.create(user=self.request.user,entity_type="project",entity_id=str(project.id),operation="CREATE",new_values={"project_code":project.project_code,"title":project.title})

    @transaction.atomic
    def perform_update(self,serializer):
        instance=serializer.instance; old={"title":instance.title,"description":instance.description,"department":str(instance.department_id),"estimated_amount":str(instance.estimated_amount)}
        project=serializer.save()
        ProjectActivity.objects.create(project=project,actor=self.request.user,activity_type="PROJECT_UPDATED",message="Project details updated")
        AuditLog.objects.create(user=self.request.user,entity_type="project",entity_id=str(project.id),operation="UPDATE",old_values=old,new_values={"title":project.title,"description":project.description,"department":str(project.department_id),"estimated_amount":str(project.estimated_amount)})

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
        ProjectActivity.objects.create(project=project,actor=request.user,project_message=message,activity_type="MESSAGE")
        AuditLog.objects.create(user=request.user,entity_type="project",entity_id=str(project.id),operation="MESSAGE",new_values={"message_id":str(message.id)})
        return Response(MessageSerializer(message).data,status=201)

    @action(detail=True,methods=["get","post"],parser_classes=[MultiPartParser,FormParser])
    @transaction.atomic
    def documents(self,request,pk=None):
        project=self.get_object()
        if request.method=="GET":
            rows=project.documents.select_related("uploaded_by").prefetch_related("versions").all()
            return Response([{"id":str(d.id),"document_name":d.document_name,"file_size":d.file_size,"uploaded_by":d.uploaded_by.name,"created_at":d.created_at,"current_version":max([v.version_number for v in d.versions.all()] or [0]),"download_url":f"/api/v1/projects/{project.id}/documents/{d.id}/download/"} for d in rows])
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
        document.activity=activity; document.file_size=uploaded.size; document.uploaded_by=request.user
        document.save(update_fields=["activity","file_size","uploaded_by"])
        AuditLog.objects.create(user=request.user,entity_type="document",entity_id=str(document.id),operation=activity_type,new_values={"version":version_number,"name":document.document_name})
        recipients=set(project.members.exclude(user=request.user).values_list("user_id",flat=True))
        if project.created_by_id!=request.user.id: recipients.add(project.created_by_id)
        for recipient_id in recipients:
            Notification.objects.create(recipient_id=recipient_id,project=project,title="Project document updated",message=f"{document.document_name} was added to {project.project_code}.")
        return Response({"id":str(document.id),"name":document.document_name,"version":version.version_number},status=201)

    @action(detail=True,methods=["get"],url_path=r"documents/(?P<document_id>[^/.]+)/download")
    def download_document(self,request,pk=None,document_id=None):
        project=self.get_object(); document=project.documents.filter(id=document_id).first()
        if not document: raise NotFound("Document not found")
        version=document.versions.order_by("-version_number").first()
        if not version: raise NotFound("Document file not found")
        response=FileResponse(version.storage_path.open("rb"),content_type="application/pdf")
        response["Content-Disposition"]=f'inline; filename="{document.document_name}"'
        return response

    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin],url_path="workflow-action")
    @transaction.atomic
    def workflow_action(self,request,pk=None):
        project=self.get_object()
        action_name=(request.data.get("action") or "").upper()
        remarks=(request.data.get("remarks") or "").strip()
        transitions={
            ("DRAFT","SUBMIT"):"SUBMITTED",
            ("RETURNED","SUBMIT"):"SUBMITTED",
            ("SUBMITTED","FORWARD"):"UNDER_REVIEW",
            ("UNDER_REVIEW","FORWARD"):"COMMITTEE_FORMATION",
            ("COMMITTEE_FORMATION","FORWARD"):"COMMITTEE_REVIEW",
            ("COMMITTEE_REVIEW","FORWARD"):"PENDING_APPROVAL",
            ("PENDING_APPROVAL","APPROVE"):"APPROVED",
            ("SUBMITTED","RETURN"):"RETURNED",
            ("UNDER_REVIEW","RETURN"):"RETURNED",
            ("COMMITTEE_FORMATION","RETURN"):"RETURNED",
            ("COMMITTEE_REVIEW","RETURN"):"RETURNED",
            ("PENDING_APPROVAL","RETURN"):"RETURNED",
            ("SUBMITTED","REJECT"):"REJECTED",
            ("UNDER_REVIEW","REJECT"):"REJECTED",
            ("COMMITTEE_FORMATION","REJECT"):"REJECTED",
            ("COMMITTEE_REVIEW","REJECT"):"REJECTED",
            ("PENDING_APPROVAL","REJECT"):"REJECTED",
        }
        next_status=transitions.get((project.current_status,action_name))
        if not next_status:
            raise ValidationError({"action":f"{action_name or 'Choose an action'} is not available while project is {project.current_status}."})
        previous=project.current_status
        project.current_status=next_status
        project.save(update_fields=["current_status","updated_at"])
        activity_type={"SUBMIT":"PROJECT_SUBMITTED","FORWARD":"FORWARDED","APPROVE":"APPROVED","RETURN":"RETURNED","REJECT":"REJECTED"}[action_name]
        note=f"{previous.replace('_',' ').title()} → {next_status.replace('_',' ').title()}"
        if remarks: note=f"{note}. {remarks}"
        ProjectActivity.objects.create(project=project,actor=request.user,activity_type=activity_type,message=note)
        AuditLog.objects.create(user=request.user,entity_type="project",entity_id=str(project.id),operation=action_name,new_values={"status":next_status,"remarks":remarks})
        return Response({"current_status":next_status})

    @action(detail=True,methods=["get","post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin])
    @transaction.atomic
    def members(self,request,pk=None):
        project=self.get_object()
        if request.method=="GET": return Response(ProjectMemberSerializer(project.members.select_related("user").all(),many=True).data)
        try: user=User.objects.get(id=request.data.get("user"),is_active=True,verification_status="VERIFIED")
        except User.DoesNotExist: raise ValidationError({"user":"Choose an active, verified user."})
        membership,created=ProjectMember.objects.get_or_create(project=project,user=user,defaults={"assigned_by":request.user})
        if created:
            AuditLog.objects.create(user=request.user,entity_type="project",entity_id=str(project.id),operation="ASSIGN_MEMBER",new_values={"user":str(user.id)})
            ProjectActivity.objects.create(project=project,actor=request.user,activity_type="USER_ASSIGNED",message=f"{user.name} was assigned to the project")
            Notification.objects.create(recipient=user,project=project,title="Project assigned",message=f"You were assigned to {project.project_code}: {project.title}.")
        return Response(ProjectMemberSerializer(membership).data,status=201 if created else 200)

    @action(detail=True,methods=["get","post"])
    @transaction.atomic
    def vendors(self,request,pk=None):
        project=self.get_object()
        if request.method=="GET":
            eligible=Vendor.objects.filter(is_active=True,verification_status="VERIFIED").values("id","vendor_name","registration_number")
            associated=ProjectVendor.objects.filter(project=project).select_related("vendor")
            return Response({"eligible_vendors":list(eligible),"associated_vendors":[{"id":str(x.id),"vendor_id":str(x.vendor_id),"vendor_name":x.vendor.vendor_name,"participation_status":x.participation_status} for x in associated]})
        try: vendor=Vendor.objects.get(id=request.data.get("vendor"),is_active=True,verification_status="VERIFIED")
        except Vendor.DoesNotExist: raise ValidationError({"vendor":"Choose an active, verified vendor."})
        link,created=ProjectVendor.objects.get_or_create(project=project,vendor=vendor)
        if created:
            AuditLog.objects.create(user=request.user,entity_type="project_vendor",entity_id=str(link.id),operation="ASSOCIATE",new_values={"project":str(project.id),"vendor":str(vendor.id)})
            ProjectActivity.objects.create(project=project,actor=request.user,activity_type="VENDOR_ASSOCIATED",message=f"Vendor associated: {vendor.vendor_name}")
        return Response({"id":str(link.id),"vendor_id":str(vendor.id),"vendor_name":vendor.vendor_name,"participation_status":link.participation_status},status=201 if created else 200)

from rest_framework.views import APIView
from django.db.models import Count, Q
from apps.accounts.models import User
from apps.departments.models import Department
from apps.vendors.models import Vendor
from apps.audit.models import AuditLog

class DashboardSummaryView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        admin=has_any_role(request.user,"ADMIN","SUPER_ADMIN")
        projects=ProcurementProject.objects.all() if admin else ProcurementProject.objects.filter(Q(created_by=request.user)|Q(members__user=request.user)).distinct()
        result={
            "total_projects":projects.count(),
            "active_projects":projects.exclude(current_status__in=["APPROVED","REJECTED","CANCELLED"]).count(),
            "approved_projects":projects.filter(current_status="APPROVED").count(),
            "pending_actions":projects.filter(current_status__in=["SUBMITTED","UNDER_REVIEW","PENDING_APPROVAL"]).count(),
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
