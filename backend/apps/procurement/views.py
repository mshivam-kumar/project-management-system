from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.permissions import has_any_role
from apps.audit.models import AuditLog
from .models import ProcurementProject, ProjectActivity, ProjectMessage
from .serializers import ProjectSerializer, ActivitySerializer, MessageSerializer
class ProjectViewSet(viewsets.ModelViewSet):
 serializer_class=ProjectSerializer; permission_classes=[IsAuthenticated]; search_fields=["project_code","title","description"]; filterset_fields=["current_status","department"]; ordering_fields=["created_at","updated_at","estimated_amount","title"]
 def get_queryset(self):
  qs=ProcurementProject.objects.select_related("department","created_by")
  user=self.request.user
  if has_any_role(user,"ADMIN","SUPER_ADMIN"): return qs
  return qs.filter(created_by=user)
 @transaction.atomic
 def perform_create(self,serializer):
  project=serializer.save(created_by=self.request.user)
  ProjectActivity.objects.create(project=project,actor=self.request.user,activity_type="PROJECT_CREATED",message="Project created")
  AuditLog.objects.create(user=self.request.user,entity_type="project",entity_id=str(project.id),operation="CREATE",new_values={"project_code":project.project_code,"title":project.title})
 @action(detail=True,methods=["get"])
 def activities(self,request,pk=None):
  project=self.get_object(); return Response(ActivitySerializer(project.activities.select_related("actor").all(),many=True).data)
 @action(detail=True,methods=["post"])
 @transaction.atomic
 def messages(self,request,pk=None):
  project=self.get_object(); serializer=MessageSerializer(data=request.data); serializer.is_valid(raise_exception=True); message=serializer.save(project=project,sender=request.user)
  ProjectActivity.objects.create(project=project,actor=request.user,activity_type="MESSAGE",message=message.message)
  return Response(MessageSerializer(message).data,status=201)
 @action(detail=True,methods=["get","post"],parser_classes=[MultiPartParser,FormParser])
 @transaction.atomic
 def documents(self,request,pk=None):
  from apps.documents.models import Document,DocumentVersion
  project=self.get_object()
  if request.method == "GET":
   return Response([{"id":str(d.id),"document_name":d.document_name,"file_size":d.file_size,"uploaded_by":d.uploaded_by.name,"created_at":d.created_at,"download_url":f"/api/v1/projects/{project.id}/documents/{d.id}/download/"} for d in project.documents.select_related("uploaded_by").all()])
  uploaded=request.FILES.get("file")
  if not uploaded: return Response({"detail":"PDF file is required."},status=400)
  if uploaded.content_type!="application/pdf" or not uploaded.name.lower().endswith(".pdf"): return Response({"detail":"Only PDF files are accepted."},status=400)
  if uploaded.size>10*1024*1024: return Response({"detail":"Maximum file size is 10 MB."},status=400)
  doc=Document.objects.create(project=project,uploaded_by=request.user,document_name=uploaded.name,document_type="PDF",mime_type=uploaded.content_type,file_size=uploaded.size)
  version=DocumentVersion.objects.create(document=doc,version_number=1,uploaded_by=request.user,storage_path=uploaded)
  activity=ProjectActivity.objects.create(project=project,actor=request.user,activity_type="DOCUMENT_UPLOADED",message=f"Uploaded {doc.document_name}")
  doc.activity=activity; doc.save(update_fields=["activity"])
  return Response({"id":str(doc.id),"name":doc.document_name,"version":version.version_number},status=201)

 @action(detail=True,methods=["get"],url_path=r"documents/(?P<document_id>[^/.]+)/download")
 def download_document(self,request,pk=None,document_id=None):
  from django.http import FileResponse
  from rest_framework.exceptions import NotFound
  project=self.get_object()
  document=project.documents.filter(id=document_id).first()
  if not document: raise NotFound("Document not found")
  version=document.versions.order_by("-version_number").first()
  if not version: raise NotFound("Document file not found")
  response=FileResponse(version.storage_path.open("rb"),content_type="application/pdf")
  response["Content-Disposition"]=f'attachment; filename="{document.document_name}"'
  return response
