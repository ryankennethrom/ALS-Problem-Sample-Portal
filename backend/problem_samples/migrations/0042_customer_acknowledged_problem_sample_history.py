from django.db import migrations, models


OLD_SUMMARY = 'Customer acknowledged notification'
NEW_SUMMARY = 'Customer acknowledged problem sample'


def forward(apps, schema_editor):
    ProblemHistory = apps.get_model('problem_samples', 'ProblemHistory')
    ProblemHistory.objects.filter(action='acknowledged', summary=OLD_SUMMARY).update(summary=NEW_SUMMARY)


def reverse(apps, schema_editor):
    ProblemHistory = apps.get_model('problem_samples', 'ProblemHistory')
    ProblemHistory.objects.filter(action='acknowledged', summary=NEW_SUMMARY).update(summary=OLD_SUMMARY)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0041_rename_days_until_up_for_disposal'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
        migrations.AlterField(
            model_name='problemhistory',
            name='action',
            field=models.CharField(
                choices=[
                    ('created', 'Created'),
                    ('updated', 'Saved changes'),
                    ('comment', 'Added comment'),
                    ('customer_notification', 'Customer notification sent'),
                    ('acknowledged', 'Customer acknowledged problem sample'),
                ],
                max_length=30,
            ),
        ),
    ]
