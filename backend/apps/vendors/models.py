import uuid
from django.conf import settings
from django.db import models
class VendorCategory(models.Model):
    name=models.CharField(max_length=120,unique=True); description=models.TextField(blank=True)
    def __str__(self): return self.name
class Vendor(models.Model):
    class Status(models.TextChoices): PENDING="PENDING"; VERIFIED="VERIFIED"; REJECTED="REJECTED"; SUSPENDED="SUSPENDED"; INACTIVE="INACTIVE"
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); vendor_name=models.CharField(max_length=200); registration_number=models.CharField(max_length=80,blank=True)
    gstin=models.CharField(max_length=20,blank=True); email=models.EmailField(blank=True); phone=models.CharField(max_length=32,blank=True); address=models.TextField(blank=True)
    verification_status=models.CharField(max_length=16,choices=Status.choices,default=Status.PENDING); verified_by=models.ForeignKey(settings.AUTH_USER_MODEL,null=True,blank=True,on_delete=models.SET_NULL)
    verified_at=models.DateTimeField(null=True,blank=True); is_active=models.BooleanField(default=True); categories=models.ManyToManyField(VendorCategory,through="VendorCategoryMapping")
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
class VendorCategoryMapping(models.Model):
    vendor=models.ForeignKey(Vendor,on_delete=models.CASCADE); category=models.ForeignKey(VendorCategory,on_delete=models.CASCADE)
    class Meta: constraints=[models.UniqueConstraint(fields=["vendor","category"],name="unique_vendor_category")]
class VendorDocument(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); vendor=models.ForeignKey(Vendor,on_delete=models.CASCADE,related_name="documents")
    document_name=models.CharField(max_length=200); document_type=models.CharField(max_length=80); storage_path=models.CharField(max_length=500); uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); uploaded_at=models.DateTimeField(auto_now_add=True)
class VendorVerification(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False); vendor=models.ForeignKey(Vendor,on_delete=models.PROTECT,related_name="verification_history")
    verified_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT); decision=models.CharField(max_length=16); remarks=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)
class ProjectVendor(models.Model):
    project=models.ForeignKey("procurement.ProcurementProject",on_delete=models.CASCADE); vendor=models.ForeignKey(Vendor,on_delete=models.PROTECT)
    participation_status=models.CharField(max_length=32,default="INVITED"); created_at=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["project","vendor"],name="unique_project_vendor")]
