from decimal import Decimal
from rest_framework import serializers
from .models import ProcurementProject, ProjectActivity, ProjectMessage, ProjectMember
class ActivitySerializer(serializers.ModelSerializer):
    actor_name=serializers.CharField(source="actor.name",read_only=True,default="System")
    actor_designation=serializers.CharField(source="actor.designation",read_only=True,default="")
    message=serializers.SerializerMethodField()
    def get_message(self,obj): return obj.project_message.message if obj.project_message_id else obj.message
    documents=serializers.SerializerMethodField()
    def get_documents(self,obj):
        return [{"id":str(d.id),"name":d.document_name,"url":f"/projects/{obj.project_id}/documents/{d.id}/download/"} for d in obj.document_set.all()]
    class Meta: model=ProjectActivity; fields=["id","actor","actor_name","actor_designation","activity_type","message","created_at","documents"]
class ProjectSerializer(serializers.ModelSerializer):
    estimated_amount=serializers.DecimalField(max_digits=14,decimal_places=2,min_value=Decimal("0"))
    created_by_name=serializers.CharField(source="created_by.name",read_only=True); department_name=serializers.CharField(source="department.department_name",read_only=True)
    class Meta: model=ProcurementProject; fields=["id","project_code","title","description","department","department_name","created_by","created_by_name","estimated_amount","current_status","created_at","updated_at"]; read_only_fields=["id","project_code","created_by","current_status","created_at","updated_at"]
class MessageSerializer(serializers.ModelSerializer):
    sender_name=serializers.CharField(source="sender.name",read_only=True)
    message=serializers.CharField(trim_whitespace=True,allow_blank=False)
    class Meta: model=ProjectMessage; fields=["id","sender","sender_name","message","created_at"]; read_only_fields=["id","sender","created_at"]
class ProjectMemberSerializer(serializers.ModelSerializer):
    user_name=serializers.CharField(source="user.name",read_only=True); user_email=serializers.EmailField(source="user.email",read_only=True)
    class Meta: model=ProjectMember; fields=["id","project","user","user_name","user_email","assigned_by","assigned_at"]; read_only_fields=["id","project","assigned_by","assigned_at"]
