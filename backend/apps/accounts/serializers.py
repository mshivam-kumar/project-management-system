from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from .models import User, Role, UserRole, UserVerification
class UserSerializer(serializers.ModelSerializer):
    roles=serializers.SlugRelatedField(many=True,read_only=True,slug_field="name")
    department_name=serializers.CharField(source="department.department_name",read_only=True)
    class Meta: model=User; fields=["id","name","email","department","department_name","designation","is_active","verification_status","roles","created_at"]; read_only_fields=["id","is_active","verification_status","created_at"]
class RegisterSerializer(serializers.ModelSerializer):
    password=serializers.CharField(write_only=True,min_length=10)
    class Meta: model=User; fields=["name","email","password","department","designation"]
    def validate_password(self,value):
        validate_password(value)
        return value
    def create(self,data):
        user=User.objects.create_user(**data); role,_=Role.objects.get_or_create(name="USER",defaults={"description":"Regular user"}); UserRole.objects.create(user=user,role=role); UserVerification.objects.create(user=user,status="PENDING",remarks="Registration submitted"); return user
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed
class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
 def validate(self,attrs):
  data=super().validate(attrs)
  if not self.user.is_active or self.user.verification_status!="VERIFIED": raise AuthenticationFailed("Account is awaiting verification or inactive.")
  return data

class ManagedUserCreateSerializer(serializers.ModelSerializer):
    password=serializers.CharField(write_only=True,min_length=10)
    role=serializers.ChoiceField(choices=[("USER","USER"),("ADMIN","ADMIN")],default="USER")
    class Meta:
        model=User
        fields=["name","email","password","department","designation","role"]
    def validate_password(self,value):
        validate_password(value)
        return value
    def create(self,data):
        role_name=data.pop("role")
        password=data.pop("password")
        user=User.objects.create_user(password=password,is_active=True,verification_status="VERIFIED",**data)
        role,_=Role.objects.get_or_create(name=role_name)
        UserRole.objects.create(user=user,role=role,assigned_by=self.context["request"].user)
        UserVerification.objects.create(user=user,verified_by=self.context["request"].user,status="VERIFIED",remarks="Created by administrator")
        return user

class ManagedUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model=User
        fields=["name","email","department","designation","is_active"]
