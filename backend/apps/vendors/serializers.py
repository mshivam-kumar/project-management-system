from rest_framework import serializers
from .models import Vendor,VendorCategory,VendorDocument
class VendorSerializer(serializers.ModelSerializer):
    categories=serializers.PrimaryKeyRelatedField(many=True,queryset=VendorCategory.objects.all(),required=False)
    class Meta:
        model=Vendor; fields=["id","vendor_name","registration_number","gstin","email","phone","address","verification_status","verified_by","verified_at","is_active","categories","created_at","updated_at"]
        read_only_fields=["id","verification_status","verified_by","verified_at","created_at","updated_at"]
class VendorCategorySerializer(serializers.ModelSerializer):
    class Meta: model=VendorCategory; fields=["id","name","description"]
class VendorDocumentSerializer(serializers.ModelSerializer):
    class Meta: model=VendorDocument; fields=["id","vendor","document_name","document_type","uploaded_by","uploaded_at"]; read_only_fields=["id","vendor","uploaded_by","uploaded_at"]
