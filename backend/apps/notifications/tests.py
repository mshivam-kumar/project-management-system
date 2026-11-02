from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User
from .models import Notification
class NotificationAccessTests(TestCase):
 def test_users_only_see_their_own_notifications(self):
  first=User.objects.create_user("first@example.org","strong-password-123",name="First",is_active=True,verification_status="VERIFIED")
  second=User.objects.create_user("second@example.org","strong-password-123",name="Second",is_active=True,verification_status="VERIFIED")
  Notification.objects.create(recipient=first,title="Private",message="Only first user")
  client=APIClient();client.force_authenticate(second)
  self.assertEqual(client.get("/api/v1/notifications/").data["count"],0)
