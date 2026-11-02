import uuid
from django.conf import settings
from django.db import models
class AuditLog(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    entity_type=models.CharField(max_length=80); entity_id=models.CharField(max_length=80)
    operation=models.CharField(max_length=40); old_values=models.JSONField(default=dict); new_values=models.JSONField(default=dict); created_at=models.DateTimeField(auto_now_add=True)
