"""
Django settings for config project.
"""

from datetime import timedelta
from pathlib import Path

import environ
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me")

# Cloudinary: almacenamiento de las evidencias fotograficas (RF-13).
# El API Secret solo vive en el backend (.env); jamas viaja a la web ni al movil.
CLOUDINARY_CLOUD_NAME = env("CLOUDINARY_CLOUD_NAME", default="")
CLOUDINARY_API_KEY = env("CLOUDINARY_API_KEY", default="")
CLOUDINARY_API_SECRET = env("CLOUDINARY_API_SECRET", default="")
CLOUDINARY_FOLDER = env("CLOUDINARY_FOLDER", default="evidencias_campanias")

# Microservicio de clustering K-Means (Fase 5, RF-17). Servicio interno: solo el backend lo
# llama, con la clave compartida ML_API_KEY (la misma en el .env del microservicio).
ML_SERVICE_URL = env("ML_SERVICE_URL", default="http://localhost:8001")
ML_API_KEY = env("ML_API_KEY", default="")
ML_TIMEOUT_SEGUNDOS = env.int("ML_TIMEOUT_SEGUNDOS", default=60)

# Notificaciones push (Firebase Cloud Messaging). FIREBASE_CREDENTIALS_JSON es el contenido
# del JSON de la cuenta de servicio (en la nube viene de Secret Manager; nunca en git). Vacio =
# notificaciones desactivadas.
FIREBASE_CREDENTIALS_JSON = env("FIREBASE_CREDENTIALS_JSON", default="")
FCM_TIMEOUT_SEGUNDOS = env.int("FCM_TIMEOUT_SEGUNDOS", default=5)

# Agente de Reportes (LLM con tool calling, API compatible con OpenAI: Groq por defecto).
# Sin GROQ_API_KEY el agente funciona igual con el interprete de reglas (motor "reglas").
GROQ_API_KEY = env("GROQ_API_KEY", default="")
GROQ_MODEL = env("GROQ_MODEL", default="llama-3.3-70b-versatile")
GROQ_API_URL = env("GROQ_API_URL", default="https://api.groq.com/openai/v1/chat/completions")
GROQ_TIMEOUT_SEGUNDOS = env.int("GROQ_TIMEOUT_SEGUNDOS", default=30)

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "corsheaders",
    "apps.common",  # utilidades compartidas (campos, excepciones, comandos); sin modelos
    "apps.usuarios",
    "apps.catastro",
    "apps.campanias",
    "apps.fiscalizacion",
    "apps.analitica",
    "apps.reportes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# PostGIS (Supabase) — ver .env / .env.example para las variables requeridas.

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT", default="5432"),
        # Reutilizar la conexion con Supabase: abrir una nueva por peticion (TLS a la nube)
        # tarda ~1.8 s y a veces el pooler la cierra de golpe (500 intermitentes).
        # CONN_HEALTH_CHECKS descarta una conexion muerta antes de usarla.
        # 0 = una conexion por peticion. En desarrollo se usa >0 junto con
        # `runserver --nothreading` (ver docker-compose.yml): con un hilo por peticion,
        # las conexiones persistentes se acumularian.
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=0),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 10,
            # TCP keepalives: evitan que un firewall/pooler corte conexiones inactivas
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
        # Los modelos managed=False (BasedeDatos.sql) no tienen migraciones, asi
        # que Django no puede crearlos en una BD de test efimera nueva. Se
        # reutiliza la misma Supabase para tests (decision del equipo: no hay
        # aislamiento, correr tests con cuidado sobre datos compartidos).
        "TEST": {"NAME": env("DB_NAME")},
    }
}

AUTH_USER_MODEL = "usuarios.Usuario"


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "es"

TIME_ZONE = "America/La_Paz"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django REST Framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.usuarios.authentication.JWTAuthenticationConSubtipos",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.manejar_excepciones",
}

# JWT: el access dura poco; el refresh dura 14 dias para que un inspector sin senal varios
# dias pueda sincronizar al volver sin tener que iniciar sesion de nuevo (MOVIL.md, G7).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API Sistema de Riesgo de Incendios",
    "DESCRIPTION": (
        "API del backend para evaluacion y zonificacion de riesgo de incendios (Bomberos UUBR)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "EstadoCampaniaEnum": "apps.campanias.models.Campania.ESTADO_CHOICES",
    },
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_HEADERS = [*default_headers, "idempotency-key"]
CORS_EXPOSE_HEADERS = ["Content-Disposition", "X-Reporte-Id"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
