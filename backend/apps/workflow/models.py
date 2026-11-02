import uuid
from django.conf import settings
from django.db import models
class WorkflowTemplate(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); name=models.CharField(max_length=160); description=models.TextField(blank=True); is_active=models.BooleanField(default=True)
class WorkflowStage(models.Model):
    workflow_template=models.ForeignKey(WorkflowTemplate,on_delete=models.CASCADE,related_name="stages"); stage_name=models.CharField(max_length=160); sequence=models.PositiveIntegerField(); description=models.TextField(blank=True)
    class Meta: ordering=["sequence"]; constraints=[models.UniqueConstraint(fields=["workflow_template","sequence"],name="unique_workflow_stage_sequence")]
class WorkflowRule(models.Model):
    from_stage=models.ForeignKey(WorkflowStage,on_delete=models.CASCADE,related_name="outgoing_rules"); to_stage=models.ForeignKey(WorkflowStage,on_delete=models.CASCADE,related_name="incoming_rules"); action=models.CharField(max_length=80); is_active=models.BooleanField(default=True)
class ProjectWorkflow(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="workflows"); workflow_template=models.ForeignKey(WorkflowTemplate,on_delete=models.PROTECT)
    started_at=models.DateTimeField(auto_now_add=True); completed_at=models.DateTimeField(null=True,blank=True)
class WorkflowTask(models.Model):
    class Status(models.TextChoices): PENDING="PENDING"; IN_PROGRESS="IN_PROGRESS"; COMPLETED="COMPLETED"; CANCELLED="CANCELLED"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="workflow_tasks"); stage=models.ForeignKey(WorkflowStage,on_delete=models.PROTECT)
    assigned_to=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL); assigned_role=models.CharField(max_length=30,blank=True); status=models.CharField(max_length=16,choices=Status.choices,default=Status.PENDING)
    assigned_at=models.DateTimeField(auto_now_add=True); due_date=models.DateTimeField(null=True,blank=True); completed_at=models.DateTimeField(null=True,blank=True)
class WorkflowAction(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); task=models.ForeignKey(WorkflowTask,on_delete=models.PROTECT,related_name="actions"); performed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    action=models.CharField(max_length=80); remarks=models.TextField(blank=True); previous_stage=models.ForeignKey(WorkflowStage,null=True,blank=True,on_delete=models.PROTECT,related_name="previous_actions"); next_stage=models.ForeignKey(WorkflowStage,null=True,blank=True,on_delete=models.PROTECT,related_name="next_actions"); created_at=models.DateTimeField(auto_now_add=True)
