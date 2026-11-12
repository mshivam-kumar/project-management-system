import uuid
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator

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

class ProjectStage(models.Model):
    class Type(models.TextChoices):
        TSC_FORMATION="TSC_FORMATION","TSC formation"
        TSC_REPORT="TSC_REPORT","TSC report"
        TSC_REPORT_LEVEL3="TSC_REPORT_LEVEL3","TSC report - Level 3"
        TENDER_DRAFT="TENDER_DRAFT","Tender draft"
        TEC_FORMATION="TEC_FORMATION","TEC formation"
        TEC_REPORT="TEC_REPORT","TEC report"
        VENDOR_QUALIFICATION="VENDOR_QUALIFICATION","Vendor qualification"
        TAC_FORMATION="TAC_FORMATION","TAC formation"
        TAC_FINANCIAL_BIDS="TAC_FINANCIAL_BIDS","TAC financial bids"
        VENDOR_SELECTION="VENDOR_SELECTION","Vendor selection"
        TAC_FINAL_REPORT="TAC_FINAL_REPORT","TAC final report"
        NEGOTIATION="NEGOTIATION","Negotiation"
    class Status(models.TextChoices):
        NOT_STARTED="NOT_STARTED","Not started"
        IN_PROGRESS="IN_PROGRESS","In progress"
        WAITING_APPROVAL="WAITING_APPROVAL","Waiting approval"
        NEEDS_REVISION="NEEDS_REVISION","Needs revision"
        COMPLETED="COMPLETED","Completed"
        CANCELLED="CANCELLED","Cancelled"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="workflow_stages")
    stage_type=models.CharField(max_length=24,choices=Type.choices)
    sequence=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status=models.CharField(max_length=24,choices=Status.choices,default=Status.NOT_STARTED)
    planned_start=models.DateField(null=True,blank=True)
    due_date=models.DateField(null=True,blank=True)
    actual_start=models.DateTimeField(null=True,blank=True)
    completed_at=models.DateTimeField(null=True,blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="created_project_stages")
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["sequence"]
        constraints=[
            models.UniqueConstraint(fields=["project","sequence"],name="unique_project_stage_sequence"),
            models.UniqueConstraint(fields=["project","stage_type"],name="unique_project_stage_type"),
            models.CheckConstraint(condition=models.Q(due_date__isnull=True)|models.Q(planned_start__isnull=True)|models.Q(due_date__gte=models.F("planned_start")),name="project_stage_due_after_start"),
        ]

class StageSubmission(models.Model):
    class Type(models.TextChoices):
        TSC_FORMATION="TSC_FORMATION","TSC formation"
        TSC_REPORT="TSC_REPORT","TSC report"
        TSC_REPORT_LEVEL3="TSC_REPORT_LEVEL3","TSC report - Level 3"
        TENDER_DRAFT="TENDER_DRAFT","Tender draft"
        TEC_FORMATION="TEC_FORMATION","TEC formation"
        TEC_REPORT="TEC_REPORT","TEC report"
        TAC_FORMATION="TAC_FORMATION","TAC formation"
    class Status(models.TextChoices):
        DRAFT="DRAFT","Draft"
        IN_REVIEW="IN_REVIEW","In review"
        NEEDS_RESPONSE="NEEDS_RESPONSE","Needs response"
        APPROVED="APPROVED","Approved"
        REJECTED="REJECTED","Rejected"
        SUPERSEDED="SUPERSEDED","Superseded"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    stage=models.ForeignKey(ProjectStage,on_delete=models.PROTECT,related_name="submissions")
    committee=models.ForeignKey("committees.Committee",null=True,blank=True,on_delete=models.PROTECT,related_name="submissions")
    submission_type=models.CharField(max_length=24,choices=Type.choices)
    revision=models.PositiveIntegerField(default=1,validators=[MinValueValidator(1)])
    supersedes=models.ForeignKey("self",null=True,blank=True,on_delete=models.PROTECT,related_name="revisions")
    source_report=models.ForeignKey("self",null=True,blank=True,on_delete=models.PROTECT,related_name="level3_reviews")
    submitted_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="stage_submissions")
    title=models.CharField(max_length=200)
    comments=models.TextField(blank=True)
    expected_vendor_dispatch_date=models.DateField(null=True,blank=True)
    expected_bid_receipt_date=models.DateField(null=True,blank=True)
    expected_product_arrival_date=models.DateField(null=True,blank=True)
    file=models.FileField(upload_to="workflow_submissions/%Y/%m/",null=True,blank=True)
    status=models.CharField(max_length=24,choices=Status.choices,default=Status.DRAFT)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-created_at"]
        constraints=[models.UniqueConstraint(fields=["stage","submission_type","revision"],name="unique_stage_submission_revision")]

class ApprovalPolicy(models.Model):
    name=models.CharField(max_length=160)
    submission_type=models.CharField(max_length=24,choices=StageSubmission.Type.choices)
    is_active=models.BooleanField(default=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="created_approval_policies")
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["submission_type"],condition=models.Q(is_active=True),name="unique_active_approval_policy_type")]

class ApprovalPolicyLevel(models.Model):
    policy=models.ForeignKey(ApprovalPolicy,on_delete=models.CASCADE,related_name="levels")
    sequence=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    approver_role=models.CharField(max_length=60,blank=True)
    approver=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name="approval_policy_assignments")
    class Meta:
        ordering=["sequence"]
        constraints=[models.UniqueConstraint(fields=["policy","sequence"],name="unique_policy_level_sequence")]

class ApprovalRequest(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS="IN_PROGRESS","In progress"
        NEEDS_RESPONSE="NEEDS_RESPONSE","Needs response"
        APPROVED="APPROVED","Approved"
        REJECTED="REJECTED","Rejected"
        SUPERSEDED="SUPERSEDED","Superseded"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    submission=models.ForeignKey(StageSubmission,on_delete=models.PROTECT,related_name="approval_requests")
    policy=models.ForeignKey(ApprovalPolicy,null=True,blank=True,on_delete=models.PROTECT,related_name="requests")
    policy_name=models.CharField(max_length=160)
    status=models.CharField(max_length=24,choices=Status.choices,default=Status.IN_PROGRESS)
    supersedes=models.ForeignKey("self",null=True,blank=True,on_delete=models.PROTECT,related_name="revisions")
    created_at=models.DateTimeField(auto_now_add=True)
    closed_at=models.DateTimeField(null=True,blank=True)

class ApprovalStep(models.Model):
    class Status(models.TextChoices):
        BLOCKED="BLOCKED","Blocked"
        PENDING="PENDING","Pending"
        QUERY="QUERY","Query raised"
        APPROVED="APPROVED","Approved"
        REJECTED="REJECTED","Rejected"
    request=models.ForeignKey(ApprovalRequest,on_delete=models.PROTECT,related_name="steps")
    sequence=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    approver_role=models.CharField(max_length=60,blank=True)
    assigned_user=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name="approval_steps")
    status=models.CharField(max_length=16,choices=Status.choices,default=Status.BLOCKED)
    class Meta:
        ordering=["sequence"]
        constraints=[models.UniqueConstraint(fields=["request","sequence"],name="unique_request_step_sequence")]

class ApprovalEvent(models.Model):
    class Action(models.TextChoices):
        SUBMITTED="SUBMITTED","Submitted"
        APPROVED="APPROVED","Approved"
        QUERY="QUERY","Query"
        RESPONSE="RESPONSE","Response"
        REJECTED="REJECTED","Rejected"
        RESUBMITTED="RESUBMITTED","Resubmitted"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    request=models.ForeignKey(ApprovalRequest,on_delete=models.PROTECT,related_name="events")
    step=models.ForeignKey(ApprovalStep,null=True,blank=True,on_delete=models.PROTECT,related_name="events")
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="approval_events")
    action=models.CharField(max_length=16,choices=Action.choices)
    comment=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["created_at"]

class Tender(models.Model):
    class Status(models.TextChoices):
        DRAFT="DRAFT","Draft"
        APPROVED="APPROVED","Approved"
        DISTRIBUTED="DISTRIBUTED","Distributed"
        CLOSED="CLOSED","Closed"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    project=models.OneToOneField("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="tender")
    reference=models.CharField(max_length=100,blank=True)
    status=models.CharField(max_length=16,choices=Status.choices,default=Status.DRAFT)
    bid_due_at=models.DateTimeField(null=True,blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="created_tenders")
    created_at=models.DateTimeField(auto_now_add=True)

class TenderDispatch(models.Model):
    tender=models.ForeignKey(Tender,on_delete=models.CASCADE,related_name="dispatches")
    vendor=models.ForeignKey("vendors.Vendor",on_delete=models.PROTECT,related_name="tender_dispatches")
    recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="recorded_tender_dispatches")
    method=models.CharField(max_length=40,default="OFFLINE")
    reference=models.CharField(max_length=160,blank=True)
    notes=models.TextField(blank=True)
    dispatched_at=models.DateTimeField()

class VendorBid(models.Model):
    class Status(models.TextChoices):
        RECEIVED="RECEIVED","Received"
        WITHDRAWN="WITHDRAWN","Withdrawn"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    tender=models.ForeignKey(Tender,on_delete=models.PROTECT,related_name="bids")
    vendor=models.ForeignKey("vendors.Vendor",on_delete=models.PROTECT,related_name="bids")
    recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="recorded_bids")
    received_at=models.DateTimeField()
    status=models.CharField(max_length=16,choices=Status.choices,default=Status.RECEIVED)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["created_at"]
        constraints=[models.UniqueConstraint(fields=["tender","vendor"],name="unique_tender_vendor_bid")]

class BidDocument(models.Model):
    class Type(models.TextChoices):
        TECHNICAL="TECHNICAL","Technical"
        FINANCIAL="FINANCIAL","Financial"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    bid=models.ForeignKey(VendorBid,on_delete=models.CASCADE,related_name="documents")
    document_type=models.CharField(max_length=12,choices=Type.choices)
    version=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    file=models.FileField(upload_to="restricted_bids/%Y/%m/")
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="bid_documents")
    uploaded_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["document_type","version"]
        constraints=[models.UniqueConstraint(fields=["bid","document_type","version"],name="unique_bid_document_version")]

class TACVendorShortlist(models.Model):
    committee=models.ForeignKey("committees.Committee",on_delete=models.CASCADE,related_name="vendor_shortlist")
    vendor=models.ForeignKey("vendors.Vendor",on_delete=models.PROTECT,related_name="tac_shortlists")
    financial_document=models.ForeignKey(BidDocument,on_delete=models.PROTECT,related_name="tac_shortlists")
    selected_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="tac_vendor_shortlists")
    selected_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["selected_at"]
        constraints=[
            models.UniqueConstraint(fields=["committee","vendor"],name="unique_tac_shortlist_vendor"),
            models.UniqueConstraint(fields=["committee","financial_document"],name="unique_tac_shortlist_financial_document"),
        ]

class TSCWorkDocument(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    committee=models.ForeignKey("committees.Committee",on_delete=models.CASCADE,related_name="work_documents")
    version=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    file=models.FileField(upload_to="tsc_work_documents/%Y/%m/")
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="tsc_work_documents")
    uploaded_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-uploaded_at"]
        constraints=[models.UniqueConstraint(fields=["committee","version"],name="unique_tsc_work_document_version")]

class TECWorkDocument(models.Model):
    class Type(models.TextChoices):
        WORKING="WORKING","Working report"
        FINAL="FINAL","Final report"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    committee=models.ForeignKey("committees.Committee",on_delete=models.CASCADE,related_name="tec_work_documents")
    document_type=models.CharField(max_length=8,choices=Type.choices,default=Type.WORKING)
    version=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    file=models.FileField(upload_to="tec_work_documents/%Y/%m/")
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="tec_work_documents")
    uploaded_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["document_type","-uploaded_at"]
        constraints=[models.UniqueConstraint(fields=["committee","document_type","version"],name="unique_tec_document_version")]

class TACWorkDocument(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    committee=models.ForeignKey("committees.Committee",on_delete=models.CASCADE,related_name="tac_work_documents")
    version=models.PositiveIntegerField(validators=[MinValueValidator(1)])
    file=models.FileField(upload_to="tac_work_documents/%Y/%m/")
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="tac_work_documents")
    uploaded_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["-uploaded_at"]
        constraints=[models.UniqueConstraint(fields=["committee","version"],name="unique_tac_document_version")]

class TACVote(models.Model):
    committee=models.ForeignKey("committees.Committee",on_delete=models.PROTECT,related_name="votes")
    voter=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="tac_votes")
    vendor=models.ForeignKey("vendors.Vendor",on_delete=models.PROTECT,related_name="tac_votes")
    round_number=models.PositiveIntegerField(default=1,validators=[MinValueValidator(1)])
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["committee","voter","round_number"],name="unique_tac_vote_per_round")]

class VendorSelection(models.Model):
    class Status(models.TextChoices):
        SELECTED="SELECTED","Selected"
        NO_MAJORITY="NO_MAJORITY","No majority"
    committee=models.ForeignKey("committees.Committee",on_delete=models.PROTECT,related_name="selections")
    vendor=models.ForeignKey("vendors.Vendor",null=True,blank=True,on_delete=models.PROTECT,related_name="selections")
    selected_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.PROTECT,related_name="vendor_selections")
    round_number=models.PositiveIntegerField(default=1)
    status=models.CharField(max_length=16,choices=Status.choices)
    decided_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["committee","round_number"],name="unique_tac_selection_round")]

class NegotiationMessage(models.Model):
    class Direction(models.TextChoices):
        SENT="SENT","Sent to vendor"
        RECEIVED="RECEIVED","Received from vendor"
        INTERNAL="INTERNAL","Internal note"
    project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="negotiation_messages")
    vendor=models.ForeignKey("vendors.Vendor",on_delete=models.PROTECT,related_name="negotiation_messages")
    direction=models.CharField(max_length=12,choices=Direction.choices)
    message=models.TextField()
    external_reference=models.CharField(max_length=160,blank=True)
    recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name="negotiation_messages")
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=["created_at"]
