from rest_framework import serializers
from .models import Vendor,VendorCategory,VendorDocument
class VendorSerializer(serializers.ModelSerializer):
    categories=serializers.PrimaryKeyRelatedField(many=True,queryset=VendorCategory.objects.all(),required=False)
    category_names=serializers.SerializerMethodField()
    class Meta:
        model=Vendor; fields=["id","vendor_name","registration_number","gstin","email","phone","address","products_services","verification_status","verified_by","verified_at","is_active","categories","category_names","created_at","updated_at"]
        read_only_fields=["id","verification_status","verified_by","verified_at","created_at","updated_at"]
    def get_category_names(self,obj):
        return list(obj.categories.order_by("name").values_list("name",flat=True))

class VendorMatchSerializer(serializers.Serializer):
    query=serializers.CharField(min_length=2,max_length=500,trim_whitespace=True)
class VendorCategorySerializer(serializers.ModelSerializer):
    class Meta: model=VendorCategory; fields=["id","name","description"]
class VendorDocumentSerializer(serializers.ModelSerializer):
    class Meta: model=VendorDocument; fields=["id","vendor","document_name","document_type","uploaded_by","uploaded_at"]; read_only_fields=["id","vendor","uploaded_by","uploaded_at"]
