from rest_framework import serializers
from .models import AuditLog
class AuditLogSerializer(serializers.ModelSerializer):
    user_name=serializers.CharField(source="user.name",read_only=True,default="System")
    class Meta: model=AuditLog; fields=["id","user","user_name","entity_type","entity_id","operation","old_values","new_values","created_at"]
