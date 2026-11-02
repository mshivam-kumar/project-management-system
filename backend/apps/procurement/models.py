import uuid
from django.conf import settings
from django.db import models, connection, transaction
from django.db.models import Max
from django.utils import timezone
class ProjectStatus(models.TextChoices):
    DRAFT="DRAFT"; SUBMITTED="SUBMITTED"; UNDER_REVIEW="UNDER_REVIEW"; COMMITTEE_FORMATION="COMMITTEE_FORMATION"; COMMITTEE_REVIEW="COMMITTEE_REVIEW"; PENDING_APPROVAL="PENDING_APPROVAL"; APPROVED="APPROVED"; RETURNED="RETURNED"; REJECTED="REJECTED"; CANCELLED="CANCELLED"
class ProcurementProject(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    project_code=models.CharField(max_length=20,unique=True,editable=False); title=models.CharField(max_length=240); description=models.TextField(blank=True)
    department=models.ForeignKey("departments.Department",on_delete=models.PROTECT,related_name="projects")
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="created_projects")
    estimated_amount=models.DecimalField(max_digits=14,decimal_places=2,default=0)
    current_status=models.CharField(max_length=32,choices=ProjectStatus.choices,default=ProjectStatus.DRAFT)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    class Meta:
        ordering=["-updated_at"]
        indexes=[models.Index(fields=["current_status","department"])]
        constraints=[models.CheckConstraint(condition=models.Q(estimated_amount__gte=0),name="project_amount_nonnegative")]
    def save(self,*args,**kwargs):
        if not self.project_code:
            with transaction.atomic():
                if connection.vendor == "postgresql":
                    # Serialize code allocation across concurrent project creation transactions.
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_advisory_xact_lock(20261102)")
                year=timezone.now().year
                last=ProcurementProject.objects.filter(project_code__startswith=f"PR-{year}-").aggregate(n=Max("project_code"))["n"]
                seq=int(last.rsplit("-",1)[1])+1 if last else 1
                self.project_code=f"PR-{year}-{seq:04d}"
                super().save(*args,**kwargs)
        else:
            super().save(*args,**kwargs)
    def __str__(self): return f"{self.project_code} {self.title}"
class ProjectActivity(models.Model):
    class Type(models.TextChoices): PROJECT_CREATED="PROJECT_CREATED"; PROJECT_UPDATED="PROJECT_UPDATED"; PROJECT_SUBMITTED="PROJECT_SUBMITTED"; MESSAGE="MESSAGE"; DOCUMENT_UPLOADED="DOCUMENT_UPLOADED"; DOCUMENT_UPDATED="DOCUMENT_UPDATED"; USER_ASSIGNED="USER_ASSIGNED"; VENDOR_ASSOCIATED="VENDOR_ASSOCIATED"; FORWARDED="FORWARDED"; APPROVED="APPROVED"; RETURNED="RETURNED"; REJECTED="REJECTED"; COMMITTEE_FORMED="COMMITTEE_FORMED"; STATUS_CHANGED="STATUS_CHANGED"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    project=models.ForeignKey(ProcurementProject,on_delete=models.CASCADE,related_name="activities")
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL)
    project_message=models.ForeignKey("ProjectMessage",null=True,blank=True,on_delete=models.SET_NULL,related_name="activities")
    activity_type=models.CharField(max_length=32,choices=Type.choices); message=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["created_at"]
class ProjectMessage(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); project=models.ForeignKey(ProcurementProject,on_delete=models.CASCADE,related_name="messages")
    sender=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); message=models.TextField(); created_at=models.DateTimeField(auto_now_add=True)

class ProjectMember(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    project=models.ForeignKey(ProcurementProject,on_delete=models.CASCADE,related_name="members")
    user=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name="project_memberships")
    assigned_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,on_delete=models.SET_NULL,related_name="project_assignments")
    assigned_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["project","user"],name="unique_project_member")]
