from django.contrib import admin
from .models import AppSession, LoginLink, UserProfile

admin.site.register(UserProfile)
admin.site.register(LoginLink)
admin.site.register(AppSession)
