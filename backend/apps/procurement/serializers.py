from rest_framework import serializers
from .models import ProcurementProject, ProjectActivity, ProjectMessage
class ActivitySerializer(serializers.ModelSerializer):
 actor_name=serializers.CharField(source="actor.name",read_only=True,default="System")
 class Meta: model=ProjectActivity; fields=["id","actor","actor_name","activity_type","message","created_at"]
class ProjectSerializer(serializers.ModelSerializer):
 created_by_name=serializers.CharField(source="created_by.name",read_only=True); department_name=serializers.CharField(source="department.department_name",read_only=True)
 class Meta: model=ProcurementProject; fields=["id","project_code","title","description","department","department_name","created_by","created_by_name","estimated_amount","current_status","created_at","updated_at"]; read_only_fields=["id","project_code","created_by","current_status","created_at","updated_at"]
class MessageSerializer(serializers.ModelSerializer):
 sender_name=serializers.CharField(source="sender.name",read_only=True)
 class Meta: model=ProjectMessage; fields=["id","sender","sender_name","message","created_at"]; read_only_fields=["id","sender","created_at"]
