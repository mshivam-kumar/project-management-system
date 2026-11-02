from django.db import transaction
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated,AllowAny
from apps.accounts.permissions import IsAdminOrSuperAdmin
from .models import Department
from .serializers import DepartmentSerializer
from apps.audit.models import AuditLog
class DepartmentViewSet(viewsets.ModelViewSet):
 http_method_names=["get","post","patch","head","options"]
 queryset=Department.objects.all().order_by("department_name"); serializer_class=DepartmentSerializer; permission_classes=[IsAuthenticated]
 def get_permissions(self): return [AllowAny()] if self.action=="list" else ([IsAuthenticated()] if self.action=="retrieve" else [IsAuthenticated(),IsAdminOrSuperAdmin()])
 search_fields=["department_name","department_code"]
 @transaction.atomic
 def perform_create(self,serializer):
  department=serializer.save(); AuditLog.objects.create(user=self.request.user,entity_type="department",entity_id=str(department.id),operation="CREATE",new_values={"name":department.department_name,"code":department.department_code})
 @transaction.atomic
 def perform_update(self,serializer):
  instance=serializer.instance; old={"name":instance.department_name,"code":instance.department_code,"description":instance.description,"is_active":instance.is_active}
  department=serializer.save(); AuditLog.objects.create(user=self.request.user,entity_type="department",entity_id=str(department.id),operation="UPDATE",old_values=old,new_values={"name":department.department_name,"code":department.department_code,"description":department.description,"is_active":department.is_active})
