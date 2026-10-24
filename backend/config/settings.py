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
    'problem_samples.public_rate_limit.PublicTrackingRateLimitMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'problem_samples.middleware.AutomaticDisposalTransitionMiddleware',
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

# Internal isolated-backup-upgrade worker ONLY. Never set this on the web service.
if os.environ.get('ALS_UPGRADE_STAGING_DATABASE'):
    DATABASES['default']['NAME'] = os.environ['ALS_UPGRADE_STAGING_DATABASE']
elif os.environ.get('ALS_UPGRADE_STAGING_SCHEMA'):
    # Only the internal restoration worker supplies a random, private schema.
    # No fallback to public: a missed table must fail, never hit live tables.
    _upgrade_schema = os.environ['ALS_UPGRADE_STAGING_SCHEMA']
    if not _upgrade_schema.startswith('als_tracker_upgrade_'):
        raise RuntimeError('Invalid staging schema override.')
    _upgrade_options = DATABASES['default'].setdefault('OPTIONS', {})
    _upgrade_options['options'] = (_upgrade_options.get('options', '') + ' -c search_path=' + _upgrade_schema).strip()
AUTH_PASSWORD_VALIDATORS=[]
LANGUAGE_CODE='en-us'
TIME_ZONE='America/Edmonton'
USE_I18N=True
USE_TZ=True
STATIC_URL='static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
MEDIA_URL='/media/'
MEDIA_ROOT=Path(os.getenv('MEDIA_ROOT') or os.getenv('RAILWAY_VOLUME_MOUNT_PATH') or (BASE_DIR / 'media'))
if os.environ.get('ALS_UPGRADE_STAGING_DATABASE') or os.environ.get('ALS_UPGRADE_STAGING_SCHEMA'):
    # Staging migrations must never touch the production media volume.
    MEDIA_ROOT = Path(os.getenv('ALS_UPGRADE_STAGE_MEDIA_ROOT') or '/tmp/als-upgrade-stage-media')
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'

CORS_ALLOWED_ORIGINS=[x.strip() for x in os.getenv('CORS_ALLOWED_ORIGINS','http://localhost:3000').split(',') if x.strip()]
CORS_ALLOW_CREDENTIALS=False
CORS_ALLOW_HEADERS=(*default_headers, 'x-change-reason', 'x-active-lab')

REST_FRAMEWORK={
    'DEFAULT_AUTHENTICATION_CLASSES':['accounts.authentication.BearerSessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES':['rest_framework.permissions.IsAuthenticated'],
}

# Use forwarded IPs only after verifying that the ingress overwrites or appends
# X-Forwarded-For through the configured number of trusted proxy hops.
PUBLIC_TRACKING_TRUSTED_PROXY_HOPS = int(os.getenv('PUBLIC_TRACKING_TRUSTED_PROXY_HOPS', '0'))
PUBLIC_TRACKING_READ_LIMIT_PER_MINUTE = int(os.getenv('PUBLIC_TRACKING_READ_LIMIT_PER_MINUTE', '60'))
PUBLIC_TRACKING_READ_LIMIT_PER_HOUR = int(os.getenv('PUBLIC_TRACKING_READ_LIMIT_PER_HOUR', '600'))
PUBLIC_TRACKING_WRITE_LIMIT_PER_MINUTE = int(os.getenv('PUBLIC_TRACKING_WRITE_LIMIT_PER_MINUTE', '10'))
PUBLIC_TRACKING_WRITE_LIMIT_PER_HOUR = int(os.getenv('PUBLIC_TRACKING_WRITE_LIMIT_PER_HOUR', '60'))

SESSION_EXPIRES_HOURS=int(os.getenv('SESSION_EXPIRES_HOURS','12'))
FRONTEND_URL=os.getenv('FRONTEND_URL','http://localhost:3000')
