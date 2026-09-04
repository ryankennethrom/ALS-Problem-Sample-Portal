from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/problem-samples/', include('problem_samples.urls')),
    path('api/public/problem-sample-tracking/', include('problem_samples.public_urls')),
    # Legacy API alias for already-deployed frontend builds.
    path('api/public/problem-acknowledgements/', include('problem_samples.public_urls')),
    path('api/problem-tables/', include('problem_samples.table_urls')),
    path('api/problem-containers/', include('problem_samples.container_urls')),
    path('api/problem-columns/', include('problem_samples.column_urls')),
    path('api/customers/', include('customers.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
