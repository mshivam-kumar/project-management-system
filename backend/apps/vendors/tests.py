from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User,Role,UserRole
from apps.audit.models import AuditLog
from .models import Vendor,VendorVerification
class VendorVerificationTests(TestCase):
 def setUp(self):
  self.admin=User.objects.create_user("admin@x.test","strong-password-123",name="Admin",is_active=True,verification_status="VERIFIED")
  role=Role.objects.create(name="ADMIN");UserRole.objects.create(user=self.admin,role=role)
  self.vendor=Vendor.objects.create(vendor_name="Example Supply")
  self.client=APIClient();self.client.force_authenticate(self.admin)
 def test_verification_is_audited_and_historic(self):
  response=self.client.post(f"/api/v1/vendors/{self.vendor.id}/verify/",{},format="json")
  self.assertEqual(response.status_code,200)
  self.vendor.refresh_from_db()
  self.assertEqual(self.vendor.verification_status,"VERIFIED")
  self.assertTrue(VendorVerification.objects.filter(vendor=self.vendor,decision="VERIFIED").exists())
  self.assertTrue(AuditLog.objects.filter(entity_type="vendor",operation="VERIFIED").exists())
