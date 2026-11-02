import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0,backend").split(",")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "rest_framework_simplejwt.token_blacklist", "django_filters", "corsheaders",
    "apps.accounts", "apps.departments", "apps.procurement", "apps.vendors", "apps.documents",
    "apps.workflow", "apps.committees", "apps.notifications", "apps.audit",
]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware",
 "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
 "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
 "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE":"django.db.backends.postgresql", "NAME":os.getenv("POSTGRES_DB","procurement"), "USER":os.getenv("POSTGRES_USER","procurement"), "PASSWORD":os.getenv("POSTGRES_PASSWORD","procurement"), "HOST":os.getenv("POSTGRES_HOST","db"), "PORT":os.getenv("POSTGRES_PORT","5432")}}
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [{"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},{"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator"},{"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"},{"NAME":"django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE="en-us"; TIME_ZONE="Asia/Kolkata"; USE_I18N=True; USE_TZ=True
STATIC_URL="static/"; MEDIA_ROOT=BASE_DIR/"media"; MEDIA_URL="/media/"; DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES":["apps.accounts.authentication.VerifiedJWTAuthentication"],"DEFAULT_PERMISSION_CLASSES":["rest_framework.permissions.IsAuthenticated"],"DEFAULT_FILTER_BACKENDS":["django_filters.rest_framework.DjangoFilterBackend","rest_framework.filters.SearchFilter","rest_framework.filters.OrderingFilter"],"DEFAULT_PAGINATION_CLASS":"rest_framework.pagination.PageNumberPagination","PAGE_SIZE":20}
SIMPLE_JWT={"TOKEN_OBTAIN_SERIALIZER":"apps.accounts.serializers.VerifiedTokenObtainPairSerializer","ROTATE_REFRESH_TOKENS":True,"BLACKLIST_AFTER_ROTATION":True}
CORS_ALLOWED_ORIGINS=os.getenv("CORS_ALLOWED_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(",")
