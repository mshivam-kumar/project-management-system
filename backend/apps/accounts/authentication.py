from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
class VerifiedJWTAuthentication(JWTAuthentication):
 def authenticate(self,request):
  result=super().authenticate(request)
  if result and (not result[0].is_active or result[0].verification_status!="VERIFIED"):
   raise AuthenticationFailed("Account is not active or verified.")
  return result
