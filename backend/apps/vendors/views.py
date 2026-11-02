from django.core.files.storage import default_storage
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound,ValidationError
from rest_framework.parsers import MultiPartParser,FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.audit.models import AuditLog
from .models import Vendor,VendorVerification,VendorCategory,VendorDocument
from .serializers import VendorSerializer,VendorCategorySerializer

class VendorViewSet(viewsets.ModelViewSet):
    http_method_names=["get","post","patch","head","options"]
    queryset=Vendor.objects.all().prefetch_related("categories")
    serializer_class=VendorSerializer
    permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin]
    search_fields=["vendor_name","registration_number","gstin","email"]
    filterset_fields=["verification_status","is_active","categories"]
    @transaction.atomic
    def perform_create(self,serializer):
        vendor=serializer.save()
        AuditLog.objects.create(user=self.request.user,entity_type="vendor",entity_id=str(vendor.id),operation="CREATE",new_values={"vendor_name":vendor.vendor_name})
    @transaction.atomic
    def perform_update(self,serializer):
        instance=serializer.instance; old={"vendor_name":instance.vendor_name,"verification_status":instance.verification_status,"is_active":instance.is_active}
        vendor=serializer.save()
        AuditLog.objects.create(user=self.request.user,entity_type="vendor",entity_id=str(vendor.id),operation="UPDATE",old_values=old,new_values={"vendor_name":vendor.vendor_name,"verification_status":vendor.verification_status,"is_active":vendor.is_active})
    @action(detail=True,methods=["post"])
    @transaction.atomic
    def verify(self,request,pk=None): return self._decide(request,"VERIFIED")
    @action(detail=True,methods=["post"])
    @transaction.atomic
    def reject(self,request,pk=None): return self._decide(request,"REJECTED")
    @action(detail=True,methods=["post"])
    @transaction.atomic
    def suspend(self,request,pk=None): return self._decide(request,"SUSPENDED")
    def _decide(self,request,decision):
        vendor=self.get_object(); vendor.verification_status=decision; vendor.is_active=decision!="SUSPENDED"; vendor.verified_by=request.user; vendor.verified_at=timezone.now(); vendor.save()
        VendorVerification.objects.create(vendor=vendor,verified_by=request.user,decision=decision,remarks=request.data.get("remarks",""))
        AuditLog.objects.create(user=request.user,entity_type="vendor",entity_id=str(vendor.id),operation=decision,new_values={"status":decision})
        return Response(VendorSerializer(vendor).data)
    @action(detail=True,methods=["get","post"],parser_classes=[MultiPartParser,FormParser])
    def documents(self,request,pk=None):
        vendor=self.get_object()
        if request.method=="GET":
            return Response([{"id":str(d.id),"document_name":d.document_name,"document_type":d.document_type,"uploaded_at":d.uploaded_at,"download_url":f"/api/v1/vendors/{vendor.id}/documents/{d.id}/download/"} for d in vendor.documents.all()])
        uploaded=request.FILES.get("file")
        if not uploaded: raise ValidationError({"file":"A PDF file is required."})
        if uploaded.size>10*1024*1024 or uploaded.content_type!="application/pdf" or not uploaded.name.lower().endswith(".pdf"):
            raise ValidationError({"file":"Upload a PDF no larger than 10 MB."})
        if uploaded.read(5)!=b"%PDF-": raise ValidationError({"file":"The uploaded file is not a valid PDF."})
        uploaded.seek(0)
        path=default_storage.save(f"vendor_documents/{vendor.id}/{uploaded.name}",uploaded)
        document=VendorDocument.objects.create(vendor=vendor,document_name=uploaded.name,document_type="PDF",storage_path=path,uploaded_by=request.user)
        AuditLog.objects.create(user=request.user,entity_type="vendor_document",entity_id=str(document.id),operation="UPLOAD")
        return Response({"id":str(document.id),"document_name":document.document_name},status=201)
    @action(detail=True,methods=["get"],url_path=r"documents/(?P<document_id>[^/.]+)/download")
    def download_document(self,request,pk=None,document_id=None):
        vendor=self.get_object(); document=vendor.documents.filter(id=document_id).first()
        if not document: raise NotFound("Document not found")
        response=FileResponse(default_storage.open(document.storage_path,"rb"),content_type="application/pdf")
        response["Content-Disposition"]=f'attachment; filename="{document.document_name}"'
        return response
class VendorCategoryViewSet(viewsets.ModelViewSet):
    queryset=VendorCategory.objects.all().order_by("name"); serializer_class=VendorCategorySerializer; permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin]; search_fields=["name"]
