from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User,Role,UserRole
from .models import Department
class DepartmentPermissionTests(TestCase):
 def test_admin_can_manage_but_user_cannot(self):
  admin=User.objects.create_user("admin@x.test","strong-password-123",name="Admin",is_active=True,verification_status="VERIFIED")
  role=Role.objects.create(name="ADMIN");UserRole.objects.create(user=admin,role=role)
  client=APIClient();client.force_authenticate(admin)
  response=client.post("/api/v1/departments/",{"department_name":"Finance","department_code":"FIN"},format="json")
  self.assertEqual(response.status_code,201)
  regular=User.objects.create_user("user@x.test","strong-password-123",name="User",is_active=True,verification_status="VERIFIED")
  client.force_authenticate(regular)
  self.assertEqual(client.post("/api/v1/departments/",{"department_name":"HR","department_code":"HR"},format="json").status_code,403)
