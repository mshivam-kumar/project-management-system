from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
import os
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from apps.accounts.views import UserViewSet, MeView
from apps.departments.views import DepartmentViewSet
from apps.procurement.views import ProjectViewSet, DashboardSummaryView
from apps.vendors.views import VendorViewSet, VendorCategoryViewSet
from apps.audit.views import AuditLogViewSet
from apps.notifications.views import NotificationViewSet
from apps.committees.views import CommitteeViewSet
from apps.accounts.views import LogoutView, PasswordChangeView

router = DefaultRouter()
router.register("users", UserViewSet)
router.register("departments", DepartmentViewSet)
router.register("projects", ProjectViewSet, basename="project")
router.register("committees", CommitteeViewSet, basename="committee")
router.register("vendors", VendorViewSet)
router.register("vendor-categories", VendorCategoryViewSet, basename="vendor-category")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")
router.register("notifications", NotificationViewSet, basename="notification")
def home(request):
    frontend = os.getenv("FRONTEND_URL", "http://localhost:5173/")
    page = format_html(
        """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Procurement Portal</title><style>body{{font:16px system-ui,sans-serif;max-width:760px;margin:10vh auto;padding:0 24px;color:#1d2939}}a{{color:#2864c5}}.card{{padding:24px;border:1px solid #e7ecf2;border-radius:12px;margin-top:24px}}li{{margin:12px 0}}</style></head><body><h1>Procurement Project Management System</h1><p>The backend is running.</p><div class="card"><h2>Open the application</h2><ul><li><a href="{}">Procurement frontend</a> (sign in here)</li><li><a href="/api/v1/">Versioned API</a></li><li><a href="/admin/">Django administration</a></li></ul></div></body></html>""",
        frontend,
    )
    return HttpResponse(page)

urlpatterns = [path("", home, name="home"), path("admin/", admin.site.urls), path("api/v1/auth/login/", TokenObtainPairView.as_view()), path("api/v1/auth/refresh/", TokenRefreshView.as_view()), path("api/v1/auth/me/", MeView.as_view()), path("api/v1/auth/logout/", LogoutView.as_view()), path("api/v1/auth/password-change/", PasswordChangeView.as_view()), path("api/v1/dashboard/summary/", DashboardSummaryView.as_view()), path("api/v1/", include(router.urls))]
