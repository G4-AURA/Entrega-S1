"""
Django settings for config project.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url  # <--- NECESARIO PARA NEON (Asegúrate de tenerlo en requirements.txt)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar las variables de entorno desde el archivo .env (para local)
load_dotenv(os.path.join(BASE_DIR, '.env'))

# --- CONFIGURACIÓN PARA WINDOWS (GDAL) ---
if os.name == 'nt':
    gdal_path = os.getenv('GDAL_LIBRARY_PATH')
    geos_path = os.getenv('GEOS_LIBRARY_PATH')
    if gdal_path:
        GDAL_LIBRARY_PATH = gdal_path
    if geos_path:
        GEOS_LIBRARY_PATH = geos_path

# --- CONFIGURACIÓN GDAL GLOBAL ---
GDAL_LIBRARY_PATH = os.getenv('GDAL_LIBRARY_PATH') or None
GEOS_LIBRARY_PATH = os.getenv('GEOS_LIBRARY_PATH') or None


# --- SEGURIDAD Y DEPLOY ---
# En producción, si no hay SECRET_KEY, usa una por defecto insegura (pero Cloud Run debe tenerla)
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key')

# DEBUG: En la nube será False. En local (si está en .env) será True.
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,.run.app').split(',')
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,https://*.run.app').split(',')


# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis', # GeoDjango
    'tours',
    'creacion',
    'rutas',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # <--- Whitenoise para estáticos
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.mapbox_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# --- BASE DE DATOS HÍBRIDA (LA PARTE CLAVE) ---
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        # Configuración por defecto para LOCAL (Docker)
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': os.getenv('DB_NAME', 'aura_db'),
        'USER': os.getenv('DB_USER', 'aura_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'aura_password'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Configuración para NUBE (Neon)
# Si existe la variable DATABASE_URL, dj_database_url la usa para sobreescribir la configuración local.
db_from_env = dj_database_url.config(conn_max_age=600, ssl_require=not DEBUG)

if db_from_env:
    DATABASES['default'].update(db_from_env)
    # IMPORTANTE: dj_database_url pone el motor estándar de postgres.
    # Nosotros necesitamos PostGIS, así que lo forzamos aquí:
    DATABASES['default']['ENGINE'] = 'django.contrib.gis.db.backends.postgis'


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# --- INTERNATIONALIZATION ---
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# --- CELERY CONFIGURATION ---
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE


# --- STATIC FILES ---
# https://docs.djangoproject.com/en/5.2/howto/static-files/
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / "static"]

# Almacenamiento eficiente para producción (Whitenoise)
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --- LOGIN / LOGOUT ---
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/catalogo/'
LOGOUT_REDIRECT_URL = '/accounts/login/'


# --- API KEYS ---
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
GRAPHHOPPER_API_KEY = os.getenv('GRAPHHOPPER_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')


# --- SEGURIDAD SSL (SOLO PRODUCCIÓN) ---
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False