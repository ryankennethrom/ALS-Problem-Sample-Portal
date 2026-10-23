from django.urls import path
from . import views
from . import lab_views

urlpatterns = [
    path('labs/', lab_views.labs),
    path('labs/<int:lab_id>/', lab_views.lab_detail),
    path('me/lab/', lab_views.my_lab),
    path('labs/notifications/', lab_views.lab_notifications),
    path('login/', views.login),
    # Compatibility alias for proxies/older frontend builds that omit the trailing slash.
    # Avoids CommonMiddleware trying (and failing) to redirect a POST to login/.
    path('login', views.login),
    path('accounts/', views.accounts),
    path('accounts/<int:user_id>/admin/', views.account_admin_status),
    path('accounts/<int:user_id>/profile/', views.account_profile),
    path('accounts/<int:user_id>/reset-password/', views.reset_account_password),
    path('accounts/<int:user_id>/', views.delete_account),
    path('me/', views.me),
    path('me/password/', views.change_password),
    path('users/', views.users_by_role),
    path('logout/', views.logout),
]
