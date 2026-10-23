import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0087_manual_monthly_distributor_reports'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TicketCreationTiming',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('staff_label', models.CharField(max_length=200)),
                ('started_at', models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
                ('completed_at', models.DateTimeField(null=True, blank=True, db_index=True)),
                ('duration_ms', models.PositiveBigIntegerField(null=True, blank=True)),
                ('email_sent', models.BooleanField(null=True, blank=True)),
                ('completed_ticket', models.OneToOneField(to='problem_samples.problemsample',
                    on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name='creation_timing')),
                ('staff', models.ForeignKey(to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.SET_NULL, null=True, related_name='ticket_creation_timings')),
            ],
        ),
    ]
