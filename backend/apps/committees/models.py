import uuid
from django.conf import settings
from django.db import models
class Committee(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="committees"); committee_name=models.CharField(max_length=180); formed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); formed_at=models.DateTimeField(auto_now_add=True); status=models.CharField(max_length=32,default="ACTIVE")
class CommitteeMember(models.Model):
    committee=models.ForeignKey(Committee,on_delete=models.CASCADE,related_name="members"); user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); designation=models.CharField(max_length=160,blank=True); assigned_at=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["committee","user"],name="unique_committee_member")]
