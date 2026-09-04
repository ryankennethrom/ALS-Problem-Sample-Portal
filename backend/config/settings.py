from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {'1','true','yes','on'}

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'unsafe-dev-key')
DEBUG = env_bool('DJANGO_DEBUG', True)
ALLOWED_HOSTS = [x.strip() for x in os.getenv('DJANGO_ALLOWED_HOSTS','localhost,127.0.0.1').split(',') if x.strip()]
if DEBUG and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('*')

INSTALLED_APPS = [
    'django.contrib.admin','django.contrib.auth','django.contrib.contenttypes',
    'django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles',
    'corsheaders','rest_framework','accounts','problem_samples','customers',
]
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF='config.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION='config.wsgi.application'
ASGI_APPLICATION='config.asgi.application'
DEFAULT_DATABASE_URL = 'postgresql://problem_sample_tracker:problem_sample_tracker@127.0.0.1:5432/problem_sample_tracker'
DATABASE_URL = os.getenv('DATABASE_URL', DEFAULT_DATABASE_URL).strip() or DEFAULT_DATABASE_URL
DATABASES = {
    'default': dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=60,
        conn_health_checks=True,
    )
}
AUTH_PASSWORD_VALIDATORS=[]
LANGUAGE_CODE='en-us'
TIME_ZONE='America/Edmonton'
USE_I18N=True
USE_TZ=True
STATIC_URL='static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
MEDIA_URL='/media/'
MEDIA_ROOT=BASE_DIR/'media'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS=[x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:3000').split(',') if x.strip()]
CORS_ALLOW_CREDENTIALS=False
CORS_ALLOW_HEADERS=(*default_headers, 'x-change-reason')

REST_FRAMEWORK={
    'DEFAULT_AUTHENTICATION_CLASSES':['accounts.authentication.BearerSessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.IsAuthenticated'],
}

AUTH_ALLOWED_DOMAIN=os.getenv('AUTH_ALLOWED_DOMAIN','alsglobal.com').lower().strip()
AUTH_ALLOWED_EMAILS={x.strip().lower() for x in os.getenv('AUTH_ALLOWED_EMAILS','').split(',') if x.strip()}
LOGIN_LINK_EXPIRES_MINUTES=5
SESSION_EXPIRES_HOURS=int(os.getenv('SESSION_EXPIRES_HOURS','12'))
FRONTEND_URL=os.getenv('FRONTEND_URL','http://localhost:3000')

EMAIL_BACKEND=os.getenv('EMAIL_BACKEND','django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL=os.getenv('DEFAULT_FROM_EMAIL','Edmonton Problem Sample Tracker <noreply@example.com>')
EMAIL_HOST=os.getenv('EMAIL_HOST','')
EMAIL_PORT=int(os.getenv('EMAIL_PORT','587'))
EMAIL_HOST_USER=os.getenv('EMAIL_HOST_USER','')
EMAIL_HOST_PASSWORD=os.getenv('EMAIL_HOST_PASSWORD','')
EMAIL_USE_TLS=env_bool('EMAIL_USE_TLS', True)
