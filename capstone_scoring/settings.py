"""
Django settings for the Capstone Defense Scoring System (LAN-based).

Runs on one host machine; panelists connect from other workstations on the
same LAN through a browser. No internet is required (no CDN assets).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Change this before deploying. Can also be set via environment variable.
SECRET_KEY = os.environ.get(
    "CAPSTONE_SECRET_KEY",
    "django-insecure-change-me-capstone-scoring-cdk-ite",
)

DEBUG = os.environ.get("CAPSTONE_DEBUG", "1") == "1"

# LAN access: accept requests addressed to this machine's IP from any
# workstation on the local network.
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "defense",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "capstone_scoring.urls"

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
                "defense.context_processors.institution",
            ],
        },
    },
]

WSGI_APPLICATION = "capstone_scoring.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        # Several panelists may save at the same moment; wait instead of
        # failing with "database is locked".
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 6}},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Manila"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "defense:dashboard"
LOGOUT_REDIRECT_URL = "login"

# Shown on screens and printouts.
INSTITUTION = {
    "name": "COLEGIO de KIDAPAWAN, INC.",
    "address": "Quezon Boulevard, Kidapawan City",
    "department": "INFORMATION TECHNOLOGY EDUCATION DEPARTMENT",
    "form_title": "CAPSTONE PROJECT AND RESEARCH FINAL DEFENSE FORM",
}
