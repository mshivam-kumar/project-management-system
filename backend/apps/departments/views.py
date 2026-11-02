from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsAdminOrSuperAdmin
from .models import Department
from .serializers import DepartmentSerializer
class DepartmentViewSet(viewsets.ModelViewSet):
 queryset=Department.objects.all().order_by("department_name"); serializer_class=DepartmentSerializer; permission_classes=[IsAuthenticated]
 def get_permissions(self): return [IsAuthenticated()] if self.action in ["list","retrieve"] else [IsAuthenticated(),IsAdminOrSuperAdmin()]
 search_fields=["department_name","department_code"]
