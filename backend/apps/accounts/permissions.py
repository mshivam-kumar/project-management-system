from rest_framework.permissions import BasePermission

def has_any_role(user, *roles): return user.is_authenticated and (user.is_superuser or user.roles.filter(name__in=roles).exists())
class IsAdminOrSuperAdmin(BasePermission):
    def has_permission(self, request, view): return has_any_role(request.user,"ADMIN","SUPER_ADMIN")
class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view): return has_any_role(request.user,"SUPER_ADMIN")
