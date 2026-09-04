from django.urls import path
from .views import (
    customer_overview,
    import_customers,
    list_customers,
    suggest_brands,
    suggest_client_emails,
    suggest_distributors,
    suggest_end_users,
)

urlpatterns = [
    path('', list_customers),
    path('overview/', customer_overview),
    path('import/', import_customers),
    path('distributors/suggest/', suggest_distributors),
    path('end-users/suggest/', suggest_end_users),
    path('client-emails/suggest/', suggest_client_emails),
    path('brands/suggest/', suggest_brands),
]
