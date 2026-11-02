from django.test import TestCase
from rest_framework.test import APIClient
from .models import User,Role,UserRole,UserVerification
from apps.departments.models import Department
from apps.audit.models import AuditLog

class AuthenticationAndVerificationTests(TestCase):
    def setUp(self):
        self.client=APIClient()
        self.department=Department.objects.create(department_name="IT",department_code="IT")
        self.admin=User.objects.create_user("admin@example.org","Admin-password-123",name="Admin",is_active=True,is_staff=True,is_superuser=True,verification_status="VERIFIED")
        self.admin_role=Role.objects.create(name="SUPER_ADMIN")
        UserRole.objects.create(user=self.admin,role=self.admin_role)
    def test_registration_is_pending_and_cannot_log_in(self):
        response=self.client.post("/api/v1/auth/register/",{"name":"New Person","email":"new@example.org","password":"Strong-password-123","department":str(self.department.id)},format="json")
        self.assertEqual(response.status_code,201)
        user=User.objects.get(email="new@example.org")
        self.assertFalse(user.is_active)
        self.assertEqual(user.verification_status,"PENDING")
        self.assertEqual(self.client.post("/api/v1/auth/login/",{"email":user.email,"password":"Strong-password-123"},format="json").status_code,401)
    def test_admin_verification_enables_login_and_records_history(self):
        user=User.objects.create_user("new@example.org","Strong-password-123",name="New Person",department=self.department)
        Role.objects.create(name="USER")
        self.client.force_authenticate(self.admin)
        response=self.client.post(f"/api/v1/users/{user.id}/verify/",{},format="json")
        self.assertEqual(response.status_code,200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.verification_status,"VERIFIED")
        self.assertTrue(UserVerification.objects.filter(user=user,status="VERIFIED").exists())
        self.assertTrue(AuditLog.objects.filter(entity_id=str(user.id),operation="VERIFY").exists())
        self.client.force_authenticate(None)
        login=self.client.post("/api/v1/auth/login/",{"email":user.email,"password":"Strong-password-123"},format="json")
        self.assertEqual(login.status_code,200)
    def test_admin_can_create_regular_user_with_hashed_password(self):
        self.client.force_authenticate(self.admin)
        response=self.client.post("/api/v1/users/",{"name":"Created Person","email":"created@example.org","password":"Strong-password-123","department":str(self.department.id),"role":"USER"},format="json")
        self.assertEqual(response.status_code,201)
        user=User.objects.get(email="created@example.org")
        self.assertTrue(user.check_password("Strong-password-123"))
        self.assertTrue(user.roles.filter(name="USER").exists())
    def test_non_admin_cannot_list_users(self):
        user=User.objects.create_user("person@example.org","Strong-password-123",name="Person",is_active=True,verification_status="VERIFIED")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/v1/users/").status_code,403)

class NotificationAndPasswordTests(TestCase):
    def test_notifications_are_private_and_markable(self):
        from apps.notifications.models import Notification
        user=User.objects.create_user("one@example.org","strong-password-123",name="One",is_active=True,verification_status="VERIFIED")
        other=User.objects.create_user("two@example.org","strong-password-123",name="Two",is_active=True,verification_status="VERIFIED")
        item=Notification.objects.create(recipient=user,title="Hello",message="Private notice")
        client=APIClient();client.force_authenticate(other)
        self.assertEqual(client.get("/api/v1/notifications/").data["count"],0)
        client.force_authenticate(user)
        response=client.patch(f"/api/v1/notifications/{item.id}/read/")
        self.assertEqual(response.status_code,200)
        item.refresh_from_db();self.assertTrue(item.is_read)
    def test_password_change_requires_current_password(self):
        user=User.objects.create_user("one@example.org","old-password-123",name="One",is_active=True,verification_status="VERIFIED")
        client=APIClient();client.force_authenticate(user)
        response=client.post("/api/v1/auth/password-change/",{"old_password":"old-password-123","new_password":"new-password-456"},format="json")
        self.assertEqual(response.status_code,200)
        user.refresh_from_db();self.assertTrue(user.check_password("new-password-456"))
