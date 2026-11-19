"""
Configuración del Sistema de Gestión de Préstamos de Equipos de Laboratorio.
Caso 1 - Práctica Grupal Semana 12 (UNCP - IS093A).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Seguridad básica. En producción definir DJANGO_SECRET_KEY y DJANGO_DEBUG=0.
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-caso1-clave-solo-para-demostracion-local-cambiar-en-produccion",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"
    ).split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "prestamos",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Middleware propio (el orden importa: requieren request.user).
    "prestamos.middleware.ActividadSesionMiddleware",
    "prestamos.middleware.AlertaPrestamosMiddleware",
    "prestamos.middleware.AuditoriaMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "prestamos.context_processors.alertas_globales",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Autenticación y sesiones
# ---------------------------------------------------------------------------
LOGIN_URL = "prestamos:login"
LOGIN_REDIRECT_URL = "prestamos:dashboard"
LOGOUT_REDIRECT_URL = "prestamos:catalogo"

SESSION_COOKIE_AGE = 30 * 60          # 30 minutos (requisito del caso 1)
SESSION_SAVE_EVERY_REQUEST = True     # renueva la cookie en cada petición
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# En local se usa HTTP: las cookies Secure deben activarse solo con HTTPS.
# Para producción: DJANGO_SECURE_COOKIES=1 (y HTTPS).
SECURE_COOKIES = os.environ.get("DJANGO_SECURE_COOKIES", "0") == "1"
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "0") == "1"
SECURE_HSTS_SECONDS = 31536000 if SECURE_COOKIES else 0

# Tiempo de inactividad controlado explícitamente por middleware (segundos).
SESSION_TIMEOUT = 30 * 60

# ---------------------------------------------------------------------------
# Correo: backend de consola para recordatorios sin servicios externos.
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "biblioteca.equipos@uncp.edu.pe"

# ---------------------------------------------------------------------------
# Logging: los eventos de seguridad/auditoría quedan en archivo y consola.
# No se registran contraseñas, cookies ni cuerpos completos de formularios.
# ---------------------------------------------------------------------------
(BASE_DIR / "logs").mkdir(exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        "archivo": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "auditoria.log",
            "formatter": "simple",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "prestamos": {
            "handlers": ["console", "archivo"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
