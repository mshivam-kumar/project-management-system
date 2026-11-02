from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.audit.models import AuditLog
from .models import Vendor,VendorVerification
from .serializers import VendorSerializer
class VendorViewSet(viewsets.ModelViewSet):
 queryset=Vendor.objects.all().prefetch_related("categories"); serializer_class=VendorSerializer; permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin]; search_fields=["vendor_name","registration_number"]; filterset_fields=["verification_status","is_active"]
 @action(detail=True,methods=["post"])
 @transaction.atomic
 def verify(self,request,pk=None): return self._decide(request,"VERIFIED")
 @action(detail=True,methods=["post"])
 @transaction.atomic
 def reject(self,request,pk=None): return self._decide(request,"REJECTED")
 def _decide(self,request,status):
  vendor=self.get_object(); vendor.verification_status=status; vendor.verified_by=request.user; vendor.verified_at=timezone.now(); vendor.save()
  VendorVerification.objects.create(vendor=vendor,verified_by=request.user,decision=status,remarks=request.data.get("remarks",""))
  AuditLog.objects.create(user=request.user,entity_type="vendor",entity_id=str(vendor.id),operation=status,new_values={"status":status})
  return Response(VendorSerializer(vendor).data)
