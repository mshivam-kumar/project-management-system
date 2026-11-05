from django.db import transaction
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied,ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.accounts.permissions import has_any_role,IsAdminOrSuperAdmin
from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.procurement.models import ProcurementProject,ProjectActivity
from .models import Committee,CommitteeMember
from .serializers import CommitteeSerializer,CommitteeMemberSerializer
class CommitteeViewSet(viewsets.ModelViewSet):
    http_method_names=["get","post","patch","head","options"]
    serializer_class=CommitteeSerializer; permission_classes=[IsAuthenticated]; search_fields=["committee_name"]
    def get_queryset(self):
        qs=Committee.objects.select_related("project","formed_by").prefetch_related("members__user")
        if has_any_role(self.request.user,"ADMIN","SUPER_ADMIN"): return qs
        return qs.filter(
            Q(project__created_by=self.request.user)
            | Q(project__members__user=self.request.user)
            | Q(members__user=self.request.user)
        ).distinct()
    @transaction.atomic
    def perform_create(self,serializer):
        project=serializer.validated_data["project"]
        allowed=has_any_role(self.request.user,"ADMIN","SUPER_ADMIN") or project.created_by_id==self.request.user.id or project.members.filter(user=self.request.user).exists()
        if not allowed: raise PermissionDenied("You do not have access to that project.")
        committee=serializer.save(formed_by=self.request.user)
        ProjectActivity.objects.create(project=project,actor=self.request.user,activity_type="COMMITTEE_FORMED",message=f"Committee formed: {committee.committee_name}")
        AuditLog.objects.create(user=self.request.user,entity_type="committee",entity_id=str(committee.id),operation="CREATE",new_values={"committee_name":committee.committee_name})
    def get_permissions(self):
        if self.action in ["update","partial_update","destroy"]: return [IsAuthenticated(),IsAdminOrSuperAdmin()]
        return [IsAuthenticated()]
    @action(detail=True,methods=["get","post"])
    @transaction.atomic
    def members(self,request,pk=None):
        committee=self.get_object()
        if request.method=="GET": return Response(CommitteeMemberSerializer(committee.members.select_related("user").all(),many=True).data)
        if not has_any_role(request.user,"ADMIN","SUPER_ADMIN") and committee.project.created_by_id!=request.user.id: raise PermissionDenied("Only project owners or admins can manage committee members.")
        try: user=User.objects.get(id=request.data.get("user"),is_active=True,verification_status="VERIFIED")
        except User.DoesNotExist: raise ValidationError({"user":"Choose an active, verified user."})
        member,created=CommitteeMember.objects.get_or_create(committee=committee,user=user,defaults={"designation":request.data.get("designation") or user.designation})
        if created:
            AuditLog.objects.create(user=request.user,entity_type="committee_member",entity_id=str(member.id),operation="ASSIGN")
            Notification.objects.create(recipient=user,project=committee.project,title="Committee assignment",message=f"You were added to {committee.committee_name}.")
        return Response(CommitteeMemberSerializer(member).data,status=201 if created else 200)
