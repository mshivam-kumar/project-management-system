from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsAdminOrSuperAdmin
from .models import AuditLog
from .serializers import AuditLogSerializer
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
 queryset=AuditLog.objects.select_related("user").all(); serializer_class=AuditLogSerializer; permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin]; ordering_fields=["created_at"]
