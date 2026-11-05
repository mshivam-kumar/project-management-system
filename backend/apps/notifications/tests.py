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

 def test_unread_filter_and_count_are_private(self):
  first=User.objects.create_user("first@example.org","strong-password-123",name="First",is_active=True,verification_status="VERIFIED")
  second=User.objects.create_user("second@example.org","strong-password-123",name="Second",is_active=True,verification_status="VERIFIED")
  Notification.objects.create(recipient=first,title="Unread",message="Pending notice")
  Notification.objects.create(recipient=first,title="Read",message="Already handled",is_read=True)
  client=APIClient();client.force_authenticate(first)
  unread=client.get("/api/v1/notifications/?unread=true")
  self.assertEqual(unread.status_code,200)
  self.assertEqual(unread.data["count"],1)
  self.assertEqual(unread.data["results"][0]["title"],"Unread")
  self.assertEqual(client.get("/api/v1/notifications/unread-count/").data["count"],1)
  client.force_authenticate(second)
  self.assertEqual(client.get("/api/v1/notifications/unread-count/").data["count"],0)

 def test_read_all_only_updates_the_signed_in_users_notices(self):
  first=User.objects.create_user("first@example.org","strong-password-123",name="First",is_active=True,verification_status="VERIFIED")
  second=User.objects.create_user("second@example.org","strong-password-123",name="Second",is_active=True,verification_status="VERIFIED")
  own=Notification.objects.create(recipient=first,title="Own",message="Read this")
  other=Notification.objects.create(recipient=second,title="Other",message="Keep unread")
  client=APIClient();client.force_authenticate(first)
  response=client.patch("/api/v1/notifications/read-all/")
  self.assertEqual(response.status_code,200)
  self.assertEqual(response.data["updated"],1)
  own.refresh_from_db();other.refresh_from_db()
  self.assertTrue(own.is_read)
  self.assertFalse(other.is_read)
