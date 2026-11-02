import uuid
from django.conf import settings
from django.db import models
class Document(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE,related_name="documents")
    activity=models.ForeignKey("procurement.ProjectActivity",null=True,blank=True,on_delete=models.SET_NULL); uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    document_name=models.CharField(max_length=255); document_type=models.CharField(max_length=100,blank=True); mime_type=models.CharField(max_length=100); file_size=models.PositiveIntegerField(); created_at=models.DateTimeField(auto_now_add=True)
class DocumentVersion(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); document=models.ForeignKey(Document,on_delete=models.CASCADE,related_name="versions"); version_number=models.PositiveIntegerField()
    storage_path=models.FileField(upload_to="project_documents/%Y/%m/"); uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); uploaded_at=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["document","version_number"],name="unique_document_version")]
