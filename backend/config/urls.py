from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.accounts.views import UserViewSet, RegisterView, MeView
from apps.departments.views import DepartmentViewSet
from apps.procurement.views import ProjectViewSet
from apps.vendors.views import VendorViewSet
from apps.audit.views import AuditLogViewSet
from apps.notifications.views import NotificationViewSet

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("departments", DepartmentViewSet)
router.register("projects", ProjectViewSet)
router.register("vendors", VendorViewSet)
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("notifications", NotificationViewSet, basename="notification")
urlpatterns = [path("admin/", admin.site.urls), path("api/v1/auth/login/", TokenObtainPairView.as_view()), path("api/v1/auth/refresh/", TokenRefreshView.as_view()), path("api/v1/auth/register/", RegisterView.as_view()), path("api/v1/auth/me/", MeView.as_view()), path("api/v1/", include(router.urls))]
