from django.contrib.auth.models import User
from django.db import models


class MicrosoftMailConnection(models.Model):
    """An optional, per-user delegated Graph connection. Tokens are Fernet-encrypted."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='microsoft_mail')
    tenant_id = models.CharField(max_length=64)
    microsoft_user_id = models.CharField(max_length=100)
    email = models.EmailField()
    encrypted_tokens = models.TextField()
    expires_at = models.DateTimeField()
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class MicrosoftAuthorizationAttempt(models.Model):
    state_hash = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey('accounts.AppSession', on_delete=models.CASCADE)
    verifier = models.CharField(max_length=150)
    nonce = models.CharField(max_length=100)
    redirect_uri = models.URLField(max_length=500)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class MicrosoftMailSend(models.Model):
    """Audit provider acceptance, not proof of eventual delivery."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    idempotency_key = models.UUIDField()
    status = models.CharField(max_length=24, default='pending')
    recipient_count = models.PositiveIntegerField(default=0)
    subject = models.CharField(max_length=300, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'idempotency_key'], name='microsoft_mail_send_per_user_key')]
