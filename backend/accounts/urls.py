from django.urls import path
from . import views
urlpatterns=[
    path('request-link/', views.request_login_link),
    path('verify-link/', views.verify_login_link),
    path('me/',views.me),
    path('users/',views.users_by_role),
    path('logout/',views.logout),
]
