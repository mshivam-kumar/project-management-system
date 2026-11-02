from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import User, UserRole, Role, UserVerification
from .permissions import IsAdminOrSuperAdmin, IsSuperAdmin
from .serializers import UserSerializer, RegisterSerializer
from apps.audit.models import AuditLog
class RegisterView(generics.CreateAPIView): queryset=User.objects.all(); serializer_class=RegisterSerializer; permission_classes=[AllowAny]
class MeView(APIView):
    def get(self,request): return Response(UserSerializer(request.user).data)
class UserViewSet(viewsets.ModelViewSet):
    serializer_class=UserSerializer; queryset=User.objects.select_related("department").prefetch_related("roles")
    search_fields=["name","email"]; filterset_fields=["department","verification_status","is_active"]
    def get_permissions(self): return [IsAuthenticated(), IsAdminOrSuperAdmin()]
    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin])
    @transaction.atomic
    def verify(self,request,pk=None):
        user=self.get_object(); user.verification_status="VERIFIED"; user.is_active=True; user.verified_by=request.user; user.verified_at=timezone.now(); user.save()
        UserVerification.objects.create(user=user,verified_by=request.user,status="VERIFIED",remarks=request.data.get("remarks",""))
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(user.id),operation="VERIFY",new_values={"status":"VERIFIED"})
        return Response(UserSerializer(user).data)
    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin])
    @transaction.atomic
    def reject(self,request,pk=None):
        user=self.get_object(); user.verification_status="REJECTED"; user.is_active=False; user.verified_by=request.user; user.verified_at=timezone.now(); user.save()
        UserVerification.objects.create(user=user,verified_by=request.user,status="REJECTED",remarks=request.data.get("remarks",""))
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(user.id),operation="REJECT",new_values={"status":"REJECTED"})
        return Response(UserSerializer(user).data)
    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsSuperAdmin])
    def assign_role(self,request,pk=None):
        user=self.get_object(); role=Role.objects.get(name=request.data["role"]); UserRole.objects.get_or_create(user=user,role=role,defaults={"assigned_by":request.user})
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(user.id),operation="ASSIGN_ROLE",new_values={"role":role.name})
        return Response(UserSerializer(user).data)
