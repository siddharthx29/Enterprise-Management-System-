"""
Django settings for project.
"""

from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

# Load variables from .env file into environment (local dev only)
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-temp-key-change-this')

# Reads DEBUG from environment — set to "False" on Render, "True" locally
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "teamnexterp.com",
    "www.teamnexterp.com",
    ".onrender.com"
]

# Tell Django it's behind a proxy (Required for Render HTTPS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.sitemaps',
    'django.contrib.staticfiles',
    'myapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'myapp' / 'Templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'project.wsgi.application'

if 'DATABASE_URL' in os.environ:
    DATABASES = {
        'default': dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require={'sslmode': 'require'} if os.environ.get('DATABASE_URL','').startswith('postgres') else False
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

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

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Use CompressedStaticFilesStorage to avoid crashes if manifest is missing on Render
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CSRF_TRUSTED_ORIGINS = [
    "https://teamnexterp.com",
    "https://www.teamnexterp.com",
    "https://*.onrender.com"
]

# ============================================================
# Email Settings — all values read from environment variables
# ============================================================
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False") == "True"
EMAIL_TIMEOUT = 30

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER

# ============================================================
# Session settings for reliability on Render
# ============================================================
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ============================================================
# Logging — prints ALL errors including email errors to Render logs
# ============================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        # This will log ALL email errors to Render logs
        'django.core.mail': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # This logs your app's print() and errors
        'myapp': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# ============================================================
# Startup email config check — prints to Render logs on boot
# ============================================================
import sys
print("=== EMAIL CONFIG CHECK ===", file=sys.stderr)
print(f"EMAIL_HOST: {EMAIL_HOST}", file=sys.stderr)
print(f"EMAIL_PORT: {EMAIL_PORT}", file=sys.stderr)
print(f"EMAIL_HOST_USER: {EMAIL_HOST_USER}", file=sys.stderr)
print(f"EMAIL_HOST_PASSWORD set: {'YES' if EMAIL_HOST_PASSWORD else 'NO - THIS IS THE PROBLEM'}", file=sys.stderr)
print(f"EMAIL_USE_TLS: {EMAIL_USE_TLS}", file=sys.stderr)
print(f"DEFAULT_FROM_EMAIL: {DEFAULT_FROM_EMAIL}", file=sys.stderr)
print("==========================", file=sys.stderr)