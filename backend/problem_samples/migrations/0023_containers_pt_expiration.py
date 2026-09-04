from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


def backfill_customer_notification_dates(apps, schema_editor):
    ProblemHistory = apps.get_model('problem_samples', 'ProblemHistory')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    seen = set()
    rows = (ProblemHistory.objects
            .filter(action='customer_notification')
            .order_by('problem_id', 'created_at', 'id')
            .values_list('problem_id', 'created_at'))
    for problem_id, created_at in rows.iterator():
        if problem_id in seen:
            continue
        seen.add(problem_id)
        ProblemSample.objects.filter(
            pk=problem_id,
            customer_notified_at__isnull=True,
        ).update(customer_notified_at=created_at)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('problem_samples', '0022_problemcolumn_description'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProblemContainer',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='problem_containers_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-id']},
        ),
        migrations.AddField(
            model_name='problemtable',
            name='pt_days',
            field=models.PositiveIntegerField(
                default=30,
                help_text='Problem sample expiration limit (PT) in days from the first confirmed customer notification.',
                validators=[MinValueValidator(1), MaxValueValidator(3650)],
            ),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='container',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='problem_samples',
                to='problem_samples.problemcontainer',
            ),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='customer_notified_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_customer_notification_dates, migrations.RunPython.noop),
    ]
