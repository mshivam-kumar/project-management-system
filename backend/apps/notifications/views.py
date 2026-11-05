from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
 serializer_class=NotificationSerializer; permission_classes=[IsAuthenticated]
 def get_queryset(self):
  queryset=Notification.objects.filter(recipient=self.request.user).order_by("-created_at","-id")
  if self.request.query_params.get("unread") in {"1","true","yes"}: queryset=queryset.filter(is_read=False)
  return queryset
 @action(detail=False,methods=["get"],url_path="unread-count")
 def unread_count(self,request):
  return Response({"count":self.get_queryset().filter(is_read=False).count()})
 @action(detail=True,methods=["patch"])
 def read(self,request,pk=None):
  item=self.get_object(); item.is_read=True; item.save(update_fields=["is_read"]); return Response(self.get_serializer(item).data)
 @action(detail=False,methods=["patch"],url_path="read-all")
 def read_all(self,request):
  updated=self.get_queryset().filter(is_read=False).update(is_read=True)
  return Response({"updated":updated})
