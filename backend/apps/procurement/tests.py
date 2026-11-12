from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User,Role,UserRole
from apps.departments.models import Department
from apps.workflow.models import ProjectStage, StageSubmission
from apps.vendors.models import ProjectVendor, Vendor
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
  stage=ProjectStage.objects.get(project_id=response.data["id"],stage_type=ProjectStage.Type.TSC_FORMATION)
  self.assertEqual(stage.sequence,1)
 def test_admin_can_select_and_remove_verified_project_vendors_after_tender_approval(self):
  admin=User.objects.create_user("admin@example.org","very-secure-password",name="Admin",is_active=True,verification_status="VERIFIED")
  admin_role,_=Role.objects.get_or_create(name="ADMIN")
  UserRole.objects.create(user=admin,role=admin_role)
  vendor=Vendor.objects.create(vendor_name="Printer Supply Co",products_services="Office printers",verification_status=Vendor.Status.VERIFIED,is_active=True)
  client=APIClient();client.force_authenticate(admin)
  url=f"/api/v1/projects/{self.project.id}/vendors/"

  response=client.post(url,{"vendor_ids":[str(vendor.id)]},format="json")
  self.assertEqual(response.status_code,400,response.data)
  self.assertFalse(ProjectVendor.objects.filter(project=self.project).exists())

  level3_stage=ProjectStage.objects.create(
   project=self.project,
   stage_type=ProjectStage.Type.TSC_REPORT_LEVEL3,
   sequence=3,
   created_by=admin,
  )
  tender_stage=ProjectStage.objects.create(
   project=self.project,
   stage_type=ProjectStage.Type.TENDER_DRAFT,
   sequence=4,
   created_by=admin,
  )
  StageSubmission.objects.create(
   stage=tender_stage,
   submission_type=StageSubmission.Type.TENDER_DRAFT,
   submitted_by=admin,
   title="Tender draft",
   status=StageSubmission.Status.APPROVED,
  )
  response=client.post(url,{"vendor_ids":[str(vendor.id)]},format="json")
  self.assertEqual(response.status_code,400,response.data)
  self.assertFalse(ProjectVendor.objects.filter(project=self.project).exists())
  StageSubmission.objects.create(
   stage=level3_stage,
   submission_type=StageSubmission.Type.TSC_REPORT_LEVEL3,
   submitted_by=admin,
   title="TSC report",
   status=StageSubmission.Status.APPROVED,
  )
  response=client.post(url,{"vendor_ids":[str(vendor.id)]},format="json")
  self.assertEqual(response.status_code,200,response.data)
  self.assertTrue(response.data["tender_draft_approved"])
  self.assertEqual([item["vendor_id"] for item in response.data["vendors"]],[str(vendor.id)])
  self.assertTrue(ProjectVendor.objects.filter(
   project=self.project,
   vendor=vendor,
   participation_status="SELECTED",
  ).exists())

  response=client.delete(url,{"vendor_id":str(vendor.id)},format="json")
  self.assertEqual(response.status_code,200,response.data)
  self.assertEqual(response.data["vendors"],[])

 def test_non_admin_cannot_read_or_select_project_vendors(self):
  client=APIClient();client.force_authenticate(self.user)
  response=client.get(f"/api/v1/projects/{self.project.id}/vendors/")
  self.assertEqual(response.status_code,403)
