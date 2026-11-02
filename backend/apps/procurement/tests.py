from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User,Role,UserRole
from apps.departments.models import Department
from .models import ProcurementProject,ProjectActivity
class ProjectAccessTests(TestCase):
 def setUp(self):
  self.department=Department.objects.create(department_name="IT",department_code="IT")
  self.user=User.objects.create_user("user@example.org","very-secure-password",name="Regular",is_active=True,verification_status="VERIFIED")
  role=Role.objects.create(name="USER");UserRole.objects.create(user=self.user,role=role)
  self.other=User.objects.create_user("other@example.org","very-secure-password",name="Other",is_active=True,verification_status="VERIFIED")
  self.project=ProcurementProject.objects.create(title="Visible to owner",department=self.department,created_by=self.user)
  ProjectActivity.objects.create(project=self.project,actor=self.user,activity_type="PROJECT_CREATED",message="Created")
 def test_project_list_is_scoped_to_creator(self):
  client=APIClient();client.force_authenticate(self.user)
  response=client.get("/api/v1/projects/")
  self.assertEqual(response.status_code,200);self.assertEqual(response.data["count"],1)
 def test_other_users_cannot_retrieve_project(self):
  client=APIClient();client.force_authenticate(self.other)
  response=client.get(f"/api/v1/projects/{self.project.id}/")
  self.assertEqual(response.status_code,404)
 def test_creation_writes_initial_activity(self):
  client=APIClient();client.force_authenticate(self.user)
  response=client.post("/api/v1/projects/",{"title":"New request","department":str(self.department.id),"estimated_amount":"1250.00"},format="json")
  self.assertEqual(response.status_code,201);self.assertTrue(ProjectActivity.objects.filter(project_id=response.data["id"],activity_type="PROJECT_CREATED").exists())
