from django.test import TestCase
class ServiceLandingPageTests(TestCase):
 def test_backend_root_points_to_frontend_and_api(self):
  response=self.client.get("/")
  self.assertEqual(response.status_code,200)
  self.assertContains(response,"http://localhost:5173/")
  self.assertContains(response,"/api/v1/")
