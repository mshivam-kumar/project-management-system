import uuid
from django.conf import settings
from django.db import models
class Committee(models.Model):
    class Type(models.TextChoices):
        TSC="TSC","Technical Specification Committee"
        TEC="TEC","Technical Evaluation Committee"
        TAC="TAC","Tender Acceptance Committee"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="committees")
    committee_name=models.CharField(max_length=180)
    committee_type=models.CharField(max_length=8,choices=Type.choices,default=Type.TSC)
    chair=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name="chaired_committees")
    formed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    formed_at=models.DateTimeField(auto_now_add=True)
    status=models.CharField(max_length=32,default="DRAFT")
class CommitteeMember(models.Model):
    committee=models.ForeignKey(Committee,on_delete=models.CASCADE,related_name="members"); user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); designation=models.CharField(max_length=160,blank=True); assigned_at=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["committee","user"],name="unique_committee_member")]
