import re
from difflib import SequenceMatcher

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
from .serializers import VendorMatchSerializer,VendorSerializer,VendorCategorySerializer


_MATCH_STOP_WORDS = {
    "a", "an", "and", "for", "in", "of", "or", "the", "to", "want",
    "need", "buy", "purchase", "require", "requirements", "product",
    "products", "service", "services",
}


def _search_tokens(value):
    return {
        token for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 1 and token not in _MATCH_STOP_WORDS
    }


def _vendor_match(vendor, query_tokens):
    searchable_text = " ".join([
        vendor.vendor_name,
        vendor.products_services,
        " ".join(
            f"{category.name} {category.description}"
            for category in vendor.categories.all()
        ),
    ])
    vendor_tokens = _search_tokens(searchable_text)
    matched_terms = []
    for query_token in sorted(query_tokens):
        best_match = max(
            (
                SequenceMatcher(None, query_token, token).ratio()
                for token in vendor_tokens
            ),
            default=0,
        )
        if best_match >= 0.78:
            matched_terms.append(query_token)
    if not matched_terms:
        return None
    return round(len(matched_terms) * 100 / len(query_tokens), 1), matched_terms

class VendorViewSet(viewsets.ModelViewSet):
    queryset=Vendor.objects.all().prefetch_related("categories")
    serializer_class=VendorSerializer
    permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin]
    search_fields=["vendor_name","registration_number","gstin","email"]
    filterset_fields=["verification_status","is_active","categories"]
    @action(detail=False,methods=["post"],url_path="match")
    def match(self,request):
        serializer=VendorMatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query_tokens=_search_tokens(serializer.validated_data["query"])
        if not query_tokens:
            raise ValidationError({"query":"Enter at least one searchable product or service term."})
        results=[]
        vendors=Vendor.objects.filter(
            is_active=True,
            verification_status=Vendor.Status.VERIFIED,
        ).prefetch_related("categories")
        for vendor in vendors:
            match=_vendor_match(vendor,query_tokens)
            if match:
                score,matched_terms=match
                results.append({
                    "id":str(vendor.id),
                    "vendor_name":vendor.vendor_name,
                    "email":vendor.email,
                    "phone":vendor.phone,
                    "products_services":vendor.products_services,
                    "category_names":sorted(category.name for category in vendor.categories.all()),
                    "similarity_score":score,
                    "matched_terms":matched_terms,
                })
        results.sort(key=lambda result:(-result["similarity_score"],result["vendor_name"].casefold()))
        return Response(results[:50])
    def perform_create(self,serializer):
        vendor=serializer.save()
        AuditLog.objects.create(user=self.request.user,entity_type="vendor",entity_id=str(vendor.id),operation="CREATE",new_values={"vendor_name":vendor.vendor_name})
    def perform_update(self,serializer):
        vendor=serializer.save()
        AuditLog.objects.create(user=self.request.user,entity_type="vendor",entity_id=str(vendor.id),operation="UPDATE",new_values={"vendor_name":vendor.vendor_name})
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
