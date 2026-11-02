from rest_framework import serializers
from .models import User, Role, UserRole, UserVerification
class UserSerializer(serializers.ModelSerializer):
    roles=serializers.SlugRelatedField(many=True,read_only=True,slug_field="name")
    department_name=serializers.CharField(source="department.department_name",read_only=True)
    class Meta: model=User; fields=["id","name","email","department","department_name","designation","is_active","verification_status","roles","created_at"]; read_only_fields=["id","is_active","verification_status","created_at"]
class RegisterSerializer(serializers.ModelSerializer):
    password=serializers.CharField(write_only=True,min_length=10)
    class Meta: model=User; fields=["name","email","password","department","designation"]
    def create(self,data):
        user=User.objects.create_user(**data); role,_=Role.objects.get_or_create(name="USER",defaults={"description":"Regular user"}); UserRole.objects.create(user=user,role=role); UserVerification.objects.create(user=user,status="PENDING",remarks="Registration submitted"); return user
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
 def validate(self,attrs):
  data=super().validate(attrs)
  if not self.user.is_active or self.user.verification_status!="VERIFIED": raise AuthenticationFailed("Account is awaiting verification or inactive.")
  return data
