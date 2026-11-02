from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Notification
from .serializers import NotificationSerializer
class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
 serializer_class=NotificationSerializer; permission_classes=[IsAuthenticated]
 def get_queryset(self): return Notification.objects.filter(recipient=self.request.user)
 @action(detail=True,methods=["patch"])
 def read(self,request,pk=None):
  item=self.get_object(); item.is_read=True; item.save(update_fields=["is_read"]); return Response(self.get_serializer(item).data)
