from rest_framework import serializers
from .models import Committee,CommitteeMember
class CommitteeSerializer(serializers.ModelSerializer):
    formed_by_name=serializers.CharField(source="formed_by.name",read_only=True)
    project_code=serializers.CharField(source="project.project_code",read_only=True)
    project_title=serializers.CharField(source="project.title",read_only=True)
    class Meta: model=Committee; fields=["id","project","project_code","project_title","committee_name","formed_by","formed_by_name","formed_at","status"]; read_only_fields=["id","formed_by","formed_at"]
class CommitteeMemberSerializer(serializers.ModelSerializer):
    user_name=serializers.CharField(source="user.name",read_only=True)
    user_email=serializers.EmailField(source="user.email",read_only=True)
    class Meta: model=CommitteeMember; fields=["id","user","user_name","user_email","designation","assigned_at"]; read_only_fields=["id","assigned_at"]
