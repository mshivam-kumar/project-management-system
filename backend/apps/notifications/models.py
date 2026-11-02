import uuid
from django.conf import settings
from django.db import models
class Notification(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); recipient=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="notifications"); project=models.ForeignKey("procurement.ProcurementProject",null=True,blank=True,on_delete=models.CASCADE)
    title=models.CharField(max_length=180); message=models.TextField(); is_read=models.BooleanField(default=False); created_at=models.DateTimeField(auto_now_add=True)
