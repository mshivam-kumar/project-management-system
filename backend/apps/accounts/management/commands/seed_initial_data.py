import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.accounts.models import Role,UserRole
from apps.departments.models import Department
class Command(BaseCommand):
 help="Create base roles, sample departments, and optionally the first super admin."
 def handle(self,*args,**options):
  for name,description in [("SUPER_ADMIN","System-wide administration"),("ADMIN","Operational administration"),("USER","Regular user")]: Role.objects.get_or_create(name=name,defaults={"description":description})
  for name,code in [("Information Technology","IT"),("Procurement","PROC"),("Finance","FIN")]: Department.objects.get_or_create(department_code=code,defaults={"department_name":name})
  email=os.getenv("BOOTSTRAP_ADMIN_EMAIL"); password=os.getenv("BOOTSTRAP_ADMIN_PASSWORD"); name=os.getenv("BOOTSTRAP_ADMIN_NAME","System Administrator")
  if email and password:
   User=get_user_model(); user,created=User.objects.get_or_create(email=email,defaults={"name":name,"is_active":True,"is_staff":True,"is_superuser":True,"verification_status":"VERIFIED"})
   if created: user.set_password(password); user.save()
   role=Role.objects.get(name="SUPER_ADMIN"); UserRole.objects.get_or_create(user=user,role=role)
   self.stdout.write(self.style.SUCCESS(f"Bootstrap administrator ready: {email}"))
  else: self.stdout.write("Roles and departments seeded. Set BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD to create the first admin.")
