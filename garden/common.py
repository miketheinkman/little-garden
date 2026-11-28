"""Settings shared by the home pilot and the hosted application."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# Application definition

INSTALLED_APPS = [
    'pilot',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'pilot.device_scope.LearnerAppScope',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'garden.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'garden.wsgi.application'


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = os.environ.get("GARDEN_TIME_ZONE", "America/Chicago")

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATICFILES_DIRS = [BASE_DIR / 'static']

PASSWORD_RESET_TIMEOUT = 3600
TEST_RUNNER = "qa.runner.GardenTestRunner"

# Hosted enrollment stays closed unless a parent presents an invitation.
INVITE_ONLY_SIGNUP = True

INVITE_REQUEST_RECIPIENTS = [
    address.strip() for address in os.environ.get("GARDEN_INVITE_REQUEST_RECIPIENTS", "").split(",")
    if address.strip()
]

STRIPE_LIVE_ONE_TIME_LINK = os.environ.get("GARDEN_STRIPE_LIVE_ONE_TIME_LINK", "").strip()
STRIPE_CUSTOMER_PORTAL_LINK = os.environ.get("GARDEN_STRIPE_CUSTOMER_PORTAL_LINK", "").strip()
STRIPE_LIVE_MONTHLY_LINK = os.environ.get("GARDEN_STRIPE_LIVE_MONTHLY_LINK", "").strip()
