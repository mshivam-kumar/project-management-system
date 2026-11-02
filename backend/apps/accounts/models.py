import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email: raise ValueError("Email is required")
        user=self.model(email=self.normalize_email(email), **extra)
        user.set_password(password); user.save(using=self._db); return user
    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True); extra.setdefault("is_superuser", True); extra.setdefault("is_active", True); extra.setdefault("verification_status", "VERIFIED")
        return self.create_user(email, password, **extra)

class User(AbstractBaseUser, PermissionsMixin):
    class Verification(models.TextChoices): PENDING="PENDING"; VERIFIED="VERIFIED"; REJECTED="REJECTED"
    id=models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name=models.CharField(max_length=160); email=models.EmailField(unique=True)
    department=models.ForeignKey("departments.Department",null=True,blank=True,on_delete=models.SET_NULL,related_name="users")
    designation=models.CharField(max_length=160,blank=True)
    is_active=models.BooleanField(default=False); is_staff=models.BooleanField(default=False)
    verification_status=models.CharField(max_length=16,choices=Verification.choices,default=Verification.PENDING)
    verified_by=models.ForeignKey("self",null=True,blank=True,on_delete=models.SET_NULL,related_name="verified_users")
    verified_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
    roles=models.ManyToManyField("Role",through="UserRole",related_name="users")
    objects=UserManager(); USERNAME_FIELD="email"; REQUIRED_FIELDS=["name"]
    def has_role(self, role): return self.roles.filter(name=role).exists()
    def __str__(self): return self.name

class Role(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name=models.CharField(max_length=30,unique=True); description=models.CharField(max_length=255,blank=True)
    def __str__(self): return self.name
class UserRole(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user=models.ForeignKey(User,on_delete=models.CASCADE); role=models.ForeignKey(Role,on_delete=models.PROTECT)
    assigned_by=models.ForeignKey(User,null=True,blank=True,on_delete=models.SET_NULL,related_name="role_assignments")
    assigned_at=models.DateTimeField(auto_now_add=True)
    class Meta: constraints=[models.UniqueConstraint(fields=["user","role"],name="unique_user_role")]
class UserVerification(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    user=models.ForeignKey(User,on_delete=models.PROTECT,related_name="verification_history")
    verified_by=models.ForeignKey(User,null=True,on_delete=models.SET_NULL,related_name="verification_actions")
    status=models.CharField(max_length=16,choices=User.Verification.choices); remarks=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)
