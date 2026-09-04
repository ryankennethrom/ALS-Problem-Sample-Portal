from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login),
    path('accounts/', views.accounts),
    path('accounts/<int:user_id>/admin/', views.account_admin_status),
    path('accounts/<int:user_id>/reset-password/', views.reset_account_password),
    path('accounts/<int:user_id>/', views.delete_account),
    path('me/', views.me),
    path('me/password/', views.change_password),
    path('users/', views.users_by_role),
    path('logout/', views.logout),
]
