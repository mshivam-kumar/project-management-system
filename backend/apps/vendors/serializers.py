from rest_framework import serializers
from .models import Vendor
class VendorSerializer(serializers.ModelSerializer):
 class Meta: model=Vendor; fields="__all__"; read_only_fields=["id","verified_by","verified_at","created_at","updated_at"]
