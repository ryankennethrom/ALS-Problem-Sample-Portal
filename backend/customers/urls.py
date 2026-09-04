from django.urls import path
from .views import list_customers, import_customers, suggest_distributors, suggest_end_users, suggest_client_emails, suggest_brands

urlpatterns = [
    path('', list_customers),
    path('import/', import_customers),
    path('distributors/suggest/', suggest_distributors),
    path('end-users/suggest/', suggest_end_users),
    path('client-emails/suggest/', suggest_client_emails),
    path('brands/suggest/', suggest_brands),
]
