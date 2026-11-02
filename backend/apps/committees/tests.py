from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User,Role,UserRole
from apps.departments.models import Department
from apps.procurement.models import ProcurementProject,ProjectActivity
from .models import Committee,CommitteeMember
class CommitteeFoundationTests(TestCase):
 def setUp(self):
  self.department=Department.objects.create(department_name="Operations",department_code="OPS")
  self.admin=User.objects.create_user("admin@example.org","strong-password-123",name="Admin",is_active=True,verification_status="VERIFIED")
  role=Role.objects.create(name="ADMIN");UserRole.objects.create(user=self.admin,role=role)
  self.member=User.objects.create_user("member@example.org","strong-password-123",name="Member",is_active=True,verification_status="VERIFIED")
  self.project=ProcurementProject.objects.create(title="Equipment",department=self.department,created_by=self.admin)
  self.client=APIClient();self.client.force_authenticate(self.admin)
 def test_admin_can_form_committee_and_assign_member(self):
  response=self.client.post("/api/v1/committees/",{"project":str(self.project.id),"committee_name":"Evaluation Committee"},format="json")
  self.assertEqual(response.status_code,201)
  committee=Committee.objects.get(id=response.data["id"])
  member_response=self.client.post(f"/api/v1/committees/{committee.id}/members/",{"user":str(self.member.id),"designation":"Evaluator"},format="json")
  self.assertEqual(member_response.status_code,201)
  self.assertTrue(CommitteeMember.objects.filter(committee=committee,user=self.member).exists())
  self.assertTrue(ProjectActivity.objects.filter(project=self.project,activity_type="COMMITTEE_FORMED").exists())
