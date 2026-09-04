import hashlib
import secrets
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class UserProfile(models.Model):
    ROLE_LAB_TECHNICIAN = 'lab_technician'
    ROLE_CUSTOMER_SERVICE = 'customer_service'
    ROLE_CHOICES = [
        (ROLE_LAB_TECHNICIAN, 'Lab Technician'),
        (ROLE_CUSTOMER_SERVICE, 'Customer Service'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tracker_profile')
    role = models.CharField(max_length=40, choices=ROLE_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.email or self.user.username} - {self.get_role_display() or "No role"}'


class LoginLink(models.Model):
    email = models.EmailField(db_index=True)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def new_token():
        # 48 random bytes -> roughly 384 bits of entropy before URL-safe encoding.
        return secrets.token_urlsafe(48)

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @property
    def active(self):
        return self.used_at is None and self.expires_at > timezone.now()


class AppSession(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name='app_sessions')
    token_hash=models.CharField(max_length=64,unique=True,db_index=True)
    expires_at=models.DateTimeField(db_index=True)
    revoked_at=models.DateTimeField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

    @staticmethod
    def new_token():
        return secrets.token_urlsafe(40)

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(token.encode('utf-8')).hexdigest()

    @property
    def active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()
