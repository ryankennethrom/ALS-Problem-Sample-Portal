from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from problem_samples.dashboard_views import DashboardView, DashboardOpenedTicketsView, DashboardStorageView, CustomerRespondedTicketsView
from problem_samples.terminal_cleanup_views import OldTicketDefinitionView, TerminalTicketCleanupView
from problem_samples.backup_restore_views import BackupRestoreStatusView, BackupPrepareDownloadView, BackupDownloadView, BackupRestoreView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/dashboard/', DashboardView.as_view()),
    path('api/dashboard/opened-tickets/', DashboardOpenedTicketsView.as_view()),
    path('api/dashboard/storage/', DashboardStorageView.as_view()),
    path('api/dashboard/customer-responded/', CustomerRespondedTicketsView.as_view()),
    path('api/admin/terminal-ticket-cleanup/', TerminalTicketCleanupView.as_view()),
    path('api/admin/old-ticket-definition/', OldTicketDefinitionView.as_view()),
    path('api/admin/backup-restore/', BackupRestoreStatusView.as_view()),
    path('api/admin/backup-restore/prepare-download/', BackupPrepareDownloadView.as_view()),
    path('api/admin/backup-restore/download/', BackupDownloadView.as_view()),
    path('api/admin/backup-restore/restore/', BackupRestoreView.as_view()),
    path('api/problem-samples/', include('problem_samples.urls')),
    path('api/public/problem-sample-tracking/', include('problem_samples.public_urls')),
    # Legacy API alias for already-deployed frontend builds.
    path('api/public/problem-acknowledgements/', include('problem_samples.public_urls')),
    path('api/problem-tables/', include('problem_samples.table_urls')),
    path('api/problem-containers/', include('problem_samples.container_urls')),
    path('api/problem-columns/', include('problem_samples.column_urls')),
    path('api/email-templates/', include('problem_samples.email_template_urls')),
    path('api/customers/', include('customers.urls')),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
