from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User, UserRole, Role, UserVerification
from .permissions import IsAdminOrSuperAdmin, IsSuperAdmin
from .serializers import UserSerializer, RegisterSerializer, ManagedUserCreateSerializer, ManagedUserUpdateSerializer
from apps.audit.models import AuditLog
from apps.notifications.models import Notification

class RegisterView(generics.CreateAPIView):
    queryset=User.objects.all(); serializer_class=RegisterSerializer; permission_classes=[AllowAny]
class MeView(APIView):
    def get(self,request): return Response(UserSerializer(request.user).data)
class LogoutView(APIView):
    def post(self,request):
        token=request.data.get("refresh")
        if not token: return Response({"detail":"Refresh token is required."},status=400)
        try: RefreshToken(token).blacklist()
        except Exception: return Response({"detail":"Invalid refresh token."},status=400)
        return Response(status=204)
class PasswordChangeView(APIView):
    def post(self,request):
        old=request.data.get("old_password",""); new=request.data.get("new_password","")
        if not request.user.check_password(old): return Response({"old_password":"Current password is incorrect."},status=400)
        try: validate_password(new,request.user)
        except DjangoValidationError as error: return Response({"new_password":list(error.messages)},status=400)
        request.user.set_password(new); request.user.save(update_fields=["password"])
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(request.user.id),operation="PASSWORD_CHANGE")
        return Response({"detail":"Password updated."})

class UserViewSet(viewsets.ModelViewSet):
    http_method_names=["get","post","patch","head","options"]
    serializer_class=UserSerializer
    queryset=User.objects.select_related("department").prefetch_related("roles")
    permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin]
    search_fields=["name","email"]; filterset_fields=["department","verification_status","is_active","roles__name"]
    def get_permissions(self): return [permission() for permission in self.permission_classes]
    def get_serializer_class(self):
        if self.action=="create": return ManagedUserCreateSerializer
        if self.action in ["update","partial_update"]: return ManagedUserUpdateSerializer
        return UserSerializer
    def perform_create(self,serializer):
        if serializer.validated_data.get("role")=="ADMIN" and not self.request.user.has_role("SUPER_ADMIN") and not self.request.user.is_superuser:
            raise PermissionDenied("Only Super Admins can create administrators.")
        with transaction.atomic():
            user=serializer.save()
            AuditLog.objects.create(user=self.request.user,entity_type="user",entity_id=str(user.id),operation="CREATE",new_values={"email":user.email,"roles":list(user.roles.values_list("name",flat=True))})
    def perform_update(self,serializer):
        with transaction.atomic():
            instance=serializer.instance
            old={"name":instance.name,"email":instance.email,"department":str(instance.department_id) if instance.department_id else None,"designation":instance.designation,"is_active":instance.is_active}
            user=serializer.save()
            AuditLog.objects.create(user=self.request.user,entity_type="user",entity_id=str(user.id),operation="UPDATE",old_values=old,new_values={"name":user.name,"email":user.email,"department":str(user.department_id) if user.department_id else None,"designation":user.designation,"is_active":user.is_active})
    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin])
    @transaction.atomic
    def verify(self,request,pk=None):
        user=self.get_object(); user.verification_status="VERIFIED"; user.is_active=True; user.verified_by=request.user; user.verified_at=timezone.now(); user.save()
        UserVerification.objects.create(user=user,verified_by=request.user,status="VERIFIED",remarks=request.data.get("remarks",""))
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(user.id),operation="VERIFY",new_values={"status":"VERIFIED"})
        Notification.objects.create(recipient=user,title="Account verified",message="Your account is verified. You can now sign in.")
        return Response(UserSerializer(user).data)
    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin])
    @transaction.atomic
    def reject(self,request,pk=None):
        user=self.get_object(); user.verification_status="REJECTED"; user.is_active=False; user.verified_by=request.user; user.verified_at=timezone.now(); user.save()
        UserVerification.objects.create(user=user,verified_by=request.user,status="REJECTED",remarks=request.data.get("remarks",""))
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(user.id),operation="REJECT",new_values={"status":"REJECTED"})
        return Response(UserSerializer(user).data)
    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsSuperAdmin])
    @transaction.atomic
    def assign_role(self,request,pk=None):
        user=self.get_object(); role_name=request.data.get("role")
        try: role=Role.objects.get(name=role_name)
        except Role.DoesNotExist: raise ValidationError({"role":"Unknown role."})
        UserRole.objects.get_or_create(user=user,role=role,defaults={"assigned_by":request.user})
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(user.id),operation="ASSIGN_ROLE",new_values={"role":role.name})
        return Response(UserSerializer(user).data)
    @action(detail=True,methods=["post"],permission_classes=[IsAuthenticated,IsAdminOrSuperAdmin])
    @transaction.atomic
    def deactivate(self,request,pk=None):
        user=self.get_object(); user.is_active=False; user.save(update_fields=["is_active","updated_at"])
        AuditLog.objects.create(user=request.user,entity_type="user",entity_id=str(user.id),operation="DEACTIVATE",new_values={"is_active":False})
        return Response(UserSerializer(user).data)
