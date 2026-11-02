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
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

class ProjectCollaborationTests(TestCase):
 def setUp(self):
  self.department=Department.objects.create(department_name="Procurement",department_code="PROC")
  self.owner=User.objects.create_user("owner@example.org","very-secure-password",name="Owner",is_active=True,verification_status="VERIFIED")
  self.assignee=User.objects.create_user("assigned@example.org","very-secure-password",name="Assigned",is_active=True,verification_status="VERIFIED")
  self.project=ProcurementProject.objects.create(title="Shared request",department=self.department,created_by=self.owner)
 def test_assigned_user_can_view_project_and_timeline(self):
  from .models import ProjectMember
  ProjectMember.objects.create(project=self.project,user=self.assignee,assigned_by=self.owner)
  client=APIClient();client.force_authenticate(self.assignee)
  self.assertEqual(client.get(f"/api/v1/projects/{self.project.id}/").status_code,200)
  self.assertEqual(client.get(f"/api/v1/projects/{self.project.id}/activities/").status_code,200)
 def test_message_is_persisted_with_timeline_activity(self):
  client=APIClient();client.force_authenticate(self.owner)
  response=client.post(f"/api/v1/projects/{self.project.id}/messages/",{"message":"Please review the scope."},format="json")
  self.assertEqual(response.status_code,201)
  self.assertTrue(ProjectActivity.objects.filter(project=self.project,activity_type="MESSAGE",project_message__message="Please review the scope.").exists())
 def test_pdf_upload_rejects_non_pdf(self):
  client=APIClient();client.force_authenticate(self.owner)
  upload=SimpleUploadedFile("notes.pdf",b"not a pdf",content_type="application/pdf")
  response=client.post(f"/api/v1/projects/{self.project.id}/documents/",{"file":upload},format="multipart")
  self.assertEqual(response.status_code,400)
 @override_settings(MEDIA_ROOT="/tmp/procurement-test-media")
 def test_pdf_upload_creates_document_and_activity(self):
  client=APIClient();client.force_authenticate(self.owner)
  upload=SimpleUploadedFile("scope.pdf",b"%PDF-1.4\nminimal test pdf",content_type="application/pdf")
  response=client.post(f"/api/v1/projects/{self.project.id}/documents/",{"file":upload},format="multipart")
  self.assertEqual(response.status_code,201)
  self.assertTrue(ProjectActivity.objects.filter(project=self.project,activity_type="DOCUMENT_UPLOADED").exists())
  self.assertEqual(client.get(f"/api/v1/projects/{self.project.id}/documents/").status_code,200)
  file_response=client.get(f"/api/v1/projects/{self.project.id}/documents/{response.data['id']}/download/")
  self.assertEqual(file_response.status_code,200)
  outsider=User.objects.create_user("outsider@example.org","very-secure-password",name="Outsider",is_active=True,verification_status="VERIFIED")
  client.force_authenticate(outsider)
  self.assertEqual(client.get(f"/api/v1/projects/{self.project.id}/documents/{response.data['id']}/download/").status_code,404)
 def test_only_verified_active_vendors_can_be_associated(self):
  from apps.vendors.models import Vendor,ProjectVendor
  vendor=Vendor.objects.create(vendor_name="Awaiting review")
  client=APIClient();client.force_authenticate(self.owner)
  url=f"/api/v1/projects/{self.project.id}/vendors/"
  self.assertEqual(client.post(url,{"vendor":str(vendor.id)},format="json").status_code,400)
  vendor.verification_status="VERIFIED";vendor.save(update_fields=["verification_status"])
  response=client.post(url,{"vendor":str(vendor.id)},format="json")
  self.assertEqual(response.status_code,201)
  self.assertTrue(ProjectVendor.objects.filter(project=self.project,vendor=vendor).exists())
