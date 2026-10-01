from django.urls import path
from .email_template_views import customer_notification_template, edmonton_recipient

urlpatterns = [
    path('customer-notification/', customer_notification_template, name='customer-notification-email-template'),
    path('edmonton-recipient/', edmonton_recipient, name='edmonton-notification-recipient'),
]
