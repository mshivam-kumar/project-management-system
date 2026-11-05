from django.db import models, transaction
import re
from django.http import FileResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrSuperAdmin, has_any_role
from apps.audit.models import AuditLog
from apps.documents.models import Document, DocumentVersion
from apps.vendors.models import Vendor, ProjectVendor
from apps.notifications.models import Notification
from .models import ProcurementProject, ProjectActivity, ProjectMessage, ProjectMember, ProjectQuery, ProjectQueryReply
from .serializers import ProjectSerializer, ActivitySerializer, MessageSerializer, ProjectMemberSerializer

STAGE_DESIGNATIONS={"TSC_REPORT_AS_IA":("TSC",),"AS_IA_APPROVAL":("AS","IA"),"DG_SS_APPROVAL":("DG","SS"),"HQ_REVIEW":("HQ",),"CS_SR_REVIEW":("CS","SR"),"DRAFT_TENDER_IA":("IA",),"TENDER_ISSUED":("IA",),"VENDOR_RESPONSE":("PROCUREMENT","TENDER","VENDOR"),"TECH_BID_BOARD":("TECHNICAL","BOARD"),"TEC_REPORT":("TEC",),"TAC_REVIEW":("TAC","USER"),"IFD_CFA_APPROVAL":("IFD","CFA")}
STAGE_COMMITTEES={"TSC_REPORT_AS_IA":("TSC",),"AS_IA_APPROVAL":("AS","IA"),"DG_SS_APPROVAL":("DG","SS"),"HQ_REVIEW":("HQ",),"CS_SR_REVIEW":("CS","SR"),"DRAFT_TENDER_IA":("IA",),"TENDER_ISSUED":("IA",),"VENDOR_RESPONSE":("PROCUREMENT","TENDER","VENDOR"),"TECH_BID_BOARD":("TECHNICAL","BOARD"),"TEC_REPORT":("TEC",),"TAC_REVIEW":("TAC",),"IFD_CFA_APPROVAL":("IFD","CFA")}

def can_act_on_stage(user,project):
    if project.current_status in {"APPROVED","REJECTED","CANCELLED"}: return False
    if has_any_role(user,"ADMIN","SUPER_ADMIN"): return True
    required=STAGE_DESIGNATIONS.get(project.current_status,())
    designation_tokens=set(re.findall(r"[A-Z0-9]+",(user.designation or "").upper()))
    allowed=any(token in designation_tokens for token in required if token!="USER")
    if not allowed:
        for keyword in STAGE_COMMITTEES.get(project.current_status,()):
            if project.committees.filter(committee_name__icontains=keyword,members__user=user).exists():
                allowed=True; break
    return allowed

def can_reply_to_query(user,project,query):
    if has_any_role(user,"ADMIN","SUPER_ADMIN"): return True
    designation_tokens=set(re.findall(r"[A-Z0-9]+",(user.designation or "").upper()))
    target_tokens=set(re.findall(r"[A-Z0-9]+",(query.target_designation or "").upper()))
    internal_committee=project.committees.filter(members__user=user).exists()
    if query.target_vendor_id:
        return bool(internal_committee or (target_tokens and target_tokens.issubset(designation_tokens)))
    return bool((target_tokens and target_tokens.issubset(designation_tokens)) or project.created_by_id==user.id or project.members.filter(user=user).exists() or internal_committee)

def notify_project_stakeholders(project,actor,title,message):
    recipient_ids=set(project.members.values_list("user_id",flat=True))
    recipient_ids.update(user_id for user_id in project.committees.values_list("members__user_id",flat=True) if user_id)
    recipient_ids.add(project.created_by_id)
    recipient_ids.discard(actor.id)
    Notification.objects.bulk_create([Notification(recipient_id=user_id,project=project,title=title,message=message) for user_id in recipient_ids])

class ProjectViewSet(viewsets.ModelViewSet):
    http_method_names=["get","post","patch","head","options"]
    serializer_class=ProjectSerializer
    permission_classes=[IsAuthenticated]
    search_fields=["project_code","title","description"]
    filterset_fields=["current_status","department"]
    ordering_fields=["created_at","updated_at","estimated_amount","title"]

    @action(detail=False,methods=["get"],url_path="my-tasks")
    def my_tasks(self,request):
        tasks=[]
        projects=self.get_queryset().select_related("department","created_by").prefetch_related("members__user","committees__members__user","queries__raised_by")
        for project in projects:
            if can_act_on_stage(request.user,project):
                tasks.append({"id":f"stage-{project.id}","task_type":"WORKFLOW_ACTION","project_id":str(project.id),"project_code":project.project_code,"project_title":project.title,"current_status":project.current_status,"title":"Review current workflow stage","created_at":project.updated_at})
            for query in project.queries.filter(status="OPEN").select_related("raised_by","target_vendor"):
                if can_reply_to_query(request.user,project,query):
                    tasks.append({"id":f"query-{query.id}","task_type":"QUERY_REPLY","project_id":str(project.id),"project_code":project.project_code,"project_title":project.title,"current_status":project.current_status,"title":query.subject,"detail":query.body,"created_at":query.created_at})
        tasks.sort(key=lambda task:task["created_at"],reverse=True)
        return Response(tasks)

    def get_queryset(self):
        qs=ProcurementProject.objects.select_related("department","created_by").prefetch_related("members__user")
        user=self.request.user
        if has_any_role(user,"ADMIN","SUPER_ADMIN"): return qs
        return qs.filter(
            models.Q(created_by=user)
            | models.Q(members__user=user)
            | models.Q(committees__members__user=user)
        ).distinct()

    @transaction.atomic
    def perform_create(self,serializer):
        if not has_any_role(self.request.user,"ADMIN","SUPER_ADMIN"):
            raise PermissionDenied("Only an administrator can create procurement projects.")
        project=serializer.save(created_by=self.request.user)
        ProjectActivity.objects.create(project=project,actor=self.request.user,activity_type="PROJECT_CREATED",message="Project created")
        AuditLog.objects.create(user=self.request.user,entity_type="project",entity_id=str(project.id),operation="CREATE",new_values={"project_code":project.project_code,"title":project.title})

    @transaction.atomic
    def perform_update(self,serializer):
        if not has_any_role(self.request.user,"ADMIN","SUPER_ADMIN"):
            raise PermissionDenied("Only an administrator can change project details.")
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
        notify_project_stakeholders(project,request.user,"Project message added",f"{request.user.name} added a message to {project.project_code}.")
        return Response(MessageSerializer(message).data,status=201)

    @action(detail=True,methods=["get","post"],parser_classes=[MultiPartParser,FormParser])
    @transaction.atomic
    def documents(self,request,pk=None):
        project=self.get_object()
        if request.method=="GET":
            rows=project.documents.select_related("uploaded_by").prefetch_related("versions").all()
            return Response([{"id":str(d.id),"document_name":d.document_name,"file_size":d.file_size,"uploaded_by":d.uploaded_by.name,"created_at":d.created_at,"current_version":max([v.version_number for v in d.versions.all()] or [0]),"download_url":f"/projects/{project.id}/documents/{d.id}/download/"} for d in rows])
        uploaded=request.FILES.get("file")
        if not uploaded: raise ValidationError({"file":"PDF file is required."})
        if uploaded.size>10*1024*1024: raise ValidationError({"file":"Maximum file size is 10 MB."})
        if not uploaded.name.lower().endswith(".pdf"):
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
        recipients.update(user_id for user_id in project.committees.values_list("members__user_id",flat=True) if user_id and user_id!=request.user.id)
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

    @action(detail=True,methods=["post"],url_path="workflow-action")
    @transaction.atomic
    def workflow_action(self,request,pk=None):
        project=self.get_object()
        action_name=(request.data.get("action") or "").upper()
        remarks=(request.data.get("remarks") or "").strip()
        transitions={
            ("DRAFT","SUBMIT"):"TSC_APPROVAL",("RETURNED","RESUBMIT"):"TSC_APPROVAL",
            ("TSC_APPROVAL","APPROVE"):"BOARD_FORMATION",("BOARD_FORMATION","FORM_BOARD"):"TSC_REPORT_AS_IA",
            ("TSC_REPORT_AS_IA","FORWARD"):"AS_IA_APPROVAL",("AS_IA_APPROVAL","APPROVE"):"DG_SS_APPROVAL",
            ("DG_SS_APPROVAL","APPROVE"):"HQ_REVIEW",("HQ_REVIEW","FORWARD"):"CS_SR_REVIEW",
            ("CS_SR_REVIEW","FORWARD"):"DRAFT_TENDER_IA",("DRAFT_TENDER_IA","ACKNOWLEDGE"):"TENDER_ISSUED",
            ("TENDER_ISSUED","OPEN_RESPONSES"):"VENDOR_RESPONSE",("VENDOR_RESPONSE","CLOSE_TENDER"):"TECH_BID_BOARD",
            ("TECH_BID_BOARD","FORM_BOARD"):"TEC_FORMATION",("TEC_FORMATION","APPROVE"):"TEC_REPORT",
            ("TEC_REPORT","FORWARD"):"PRICE_BID_OPEN",("PRICE_BID_OPEN","OPEN_PRICE_BID"):"TAC_REVIEW",
            ("TAC_REVIEW","ACCEPT_TENDER"):"IFD_CFA_APPROVAL",("IFD_CFA_APPROVAL","APPROVE"):"APPROVED",
        }
        next_status=transitions.get((project.current_status,action_name))
        if not next_status:
            raise ValidationError({"action":f"{action_name or 'Choose an action'} is not available while project is {project.current_status}."})
        if (project.current_status,action_name)==("TSC_APPROVAL","APPROVE") and not project.committees.filter(committee_name__icontains="TSC").exists():
            raise ValidationError({"committee":"Form the TSC committee before recording its approval."})
        if (project.current_status,action_name) in {("BOARD_FORMATION","FORM_BOARD"),("TECH_BID_BOARD","FORM_BOARD")} and not project.committees.filter(models.Q(committee_name__icontains="BOARD")|models.Q(committee_name__icontains="TECHNICAL")).exists():
            raise ValidationError({"committee":"Form the required board in Committees before advancing."})
        if (project.current_status,action_name)==("TEC_FORMATION","APPROVE") and not project.committees.filter(committee_name__icontains="TEC").exists():
            raise ValidationError({"committee":"Form the TEC committee before approving its formation."})
        if (project.current_status,action_name)==("TAC_REVIEW","ACCEPT_TENDER"):
            tac=project.committees.filter(committee_name__icontains="TAC")
            if not tac.exists(): raise ValidationError({"committee":"Form the TAC committee before accepting the tender."})
            if not tac.filter(models.Q(members__designation__iregex=r"user([ _-]+representative)?")|models.Q(members__user__designation__iregex=r"user([ _-]+representative)?")).exists():
                raise ValidationError({"committee":"Assign a user representative to the TAC before accepting the tender."})
        if ProjectQuery.objects.filter(project=project,status="OPEN").exists():
            raise ValidationError({"queries":"Answer all open queries before advancing this stage."})
        if not can_act_on_stage(request.user,project): raise PermissionDenied("Your account designation is not authorized to advance this stage.")
        previous=project.current_status
        project.current_status=next_status
        project.save(update_fields=["current_status","updated_at"])
        activity_type={"SUBMIT":"PROJECT_SUBMITTED","RESUBMIT":"PROJECT_SUBMITTED","FORWARD":"FORWARDED","APPROVE":"APPROVED","ACKNOWLEDGE":"APPROVED","RETURN":"RETURNED","REJECT":"REJECTED"}.get(action_name,"STATUS_CHANGED")
        note=f"{previous.replace('_',' ').title()} → {next_status.replace('_',' ').title()}"
        if remarks: note=f"{note}. {remarks}"
        ProjectActivity.objects.create(project=project,actor=request.user,activity_type=activity_type,message=note)
        AuditLog.objects.create(user=request.user,entity_type="project",entity_id=str(project.id),operation=action_name,new_values={"status":next_status,"remarks":remarks})
        notify_project_stakeholders(project,request.user,"Project stage updated",f"{project.project_code} moved to {next_status.replace('_',' ').title()}. {request.user.name} recorded: {action_name.replace('_',' ').title()}.")
        return Response({"current_status":next_status})

    @action(detail=True,methods=["get","post"],url_path="queries")
    @transaction.atomic
    def queries(self,request,pk=None):
        project=self.get_object()
        if request.method=="POST":
            subject=(request.data.get("subject") or "").strip(); body=(request.data.get("body") or "").strip()
            if not subject or not body: raise ValidationError({"detail":"Subject and question are required."})
            target_vendor=None
            if request.data.get("target_vendor"):
                if not has_any_role(request.user,"ADMIN","SUPER_ADMIN") and not project.committees.filter(members__user=request.user).exists():
                    raise PermissionDenied("Only the project committee can record vendor correspondence.")
                target_vendor=Vendor.objects.filter(id=request.data["target_vendor"],projectvendor__project=project,is_active=True,verification_status="VERIFIED").first()
                if not target_vendor: raise ValidationError({"target_vendor":"Vendor is not associated with this project."})
            query=ProjectQuery.objects.create(project=project,stage=project.current_status,subject=subject,body=body,raised_by=request.user,target_designation=(request.data.get("target_designation") or "").strip(),target_vendor=target_vendor)
            ProjectActivity.objects.create(project=project,actor=request.user,activity_type="STATUS_CHANGED",message=f"Query raised at {project.current_status.replace('_',' ')}: {subject}")
            AuditLog.objects.create(user=request.user,entity_type="project_query",entity_id=str(query.id),operation="CREATE",new_values={"project":str(project.id),"stage":query.stage,"subject":subject,"target_designation":query.target_designation,"target_vendor":str(target_vendor.id) if target_vendor else None})
            notify_project_stakeholders(project,request.user,"Project query raised",f"{request.user.name} raised a query on {project.project_code}: {subject}.")
            return Response(self._query_data(query,request.user),status=201)
        qs=project.queries.select_related("raised_by","target_vendor").prefetch_related("replies__actor")
        return Response([self._query_data(q,request.user) for q in qs])

    @staticmethod
    def _query_data(query,user):
        return {"id":str(query.id),"stage":query.stage,"subject":query.subject,"body":query.body,"status":query.status,"target_designation":query.target_designation,"target_vendor":str(query.target_vendor_id) if query.target_vendor_id else None,"raised_by":query.raised_by.name,"created_at":query.created_at,"replies":[{"id":str(r.id),"actor":r.actor.name,"body":r.body,"created_at":r.created_at} for r in query.replies.all()]}

    @action(detail=True,methods=["post"],url_path=r"queries/(?P<query_id>[^/.]+)/reply")
    @transaction.atomic
    def reply_query(self,request,pk=None,query_id=None):
        project=self.get_object(); query=project.queries.filter(id=query_id).select_related("target_vendor").first()
        if not query: raise NotFound("Query not found")
        if not can_reply_to_query(request.user,project,query): raise PermissionDenied("This query is assigned to another stakeholder.")
        body=(request.data.get("body") or "").strip()
        if not body: raise ValidationError({"body":"Reply is required."})
        reply=ProjectQueryReply.objects.create(query=query,actor=request.user,body=body)
        query.status="ANSWERED"; query.save(update_fields=["status"])
        ProjectActivity.objects.create(project=project,actor=request.user,activity_type="STATUS_CHANGED",message=f"Reply added to query: {query.subject}")
        AuditLog.objects.create(user=request.user,entity_type="project_query",entity_id=str(query.id),operation="REPLY",new_values={"reply_id":str(reply.id)})
        if query.raised_by_id!=request.user.id:
            Notification.objects.create(recipient=query.raised_by,project=project,title="Project query answered",message=f"{request.user.name} replied to your query on {project.project_code}: {query.subject}.")
        return Response({"id":str(reply.id),"actor":request.user.name,"body":reply.body,"created_at":reply.created_at},status=201)

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
            eligible=Vendor.objects.filter(is_active=True,verification_status="VERIFIED").values("id","vendor_name","registration_number") if has_any_role(request.user,"ADMIN","SUPER_ADMIN") else Vendor.objects.none().values("id","vendor_name","registration_number")
            associated=ProjectVendor.objects.filter(project=project,vendor__is_active=True,vendor__verification_status="VERIFIED").select_related("vendor")
            return Response({"eligible_vendors":list(eligible),"associated_vendors":[{"id":str(x.id),"vendor_id":str(x.vendor_id),"vendor_name":x.vendor.vendor_name,"participation_status":x.participation_status} for x in associated]})
        if not has_any_role(request.user,"ADMIN","SUPER_ADMIN"): raise PermissionDenied("Only administrators may add vendors to a project.")
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
        projects=ProcurementProject.objects.all() if admin else ProcurementProject.objects.filter(
            Q(created_by=request.user)
            | Q(members__user=request.user)
            | Q(committees__members__user=request.user)
        ).distinct()
        result={
            "total_projects":projects.count(),
            "active_projects":projects.exclude(current_status__in=["APPROVED","REJECTED","CANCELLED"]).count(),
            "approved_projects":projects.filter(current_status="APPROVED").count(),
            "pending_actions":projects.exclude(current_status__in=["DRAFT","APPROVED","REJECTED","CANCELLED"]).count(),
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
