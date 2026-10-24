from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [('accounts', '0007_lab'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name='MicrosoftMailConnection', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('tenant_id', models.CharField(max_length=64)),
            ('microsoft_user_id', models.CharField(max_length=100)),
            ('email', models.EmailField(max_length=254)),
            ('encrypted_tokens', models.TextField()),
            ('expires_at', models.DateTimeField()),
            ('connected_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='microsoft_mail', to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='MicrosoftAuthorizationAttempt', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('state_hash', models.CharField(db_index=True, max_length=64, unique=True)),
            ('verifier', models.CharField(max_length=150)),
            ('nonce', models.CharField(max_length=100)),
            ('redirect_uri', models.URLField(max_length=500)),
            ('expires_at', models.DateTimeField()),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('session', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='accounts.appsession')),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='MicrosoftMailSend', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('idempotency_key', models.UUIDField()),
            ('status', models.CharField(default='pending', max_length=24)),
            ('recipient_count', models.PositiveIntegerField(default=0)),
            ('subject', models.CharField(blank=True, max_length=300)),
            ('accepted_at', models.DateTimeField(blank=True, null=True)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'constraints': [models.UniqueConstraint(fields=('user', 'idempotency_key'), name='microsoft_mail_send_per_user_key')]}),
    ]
