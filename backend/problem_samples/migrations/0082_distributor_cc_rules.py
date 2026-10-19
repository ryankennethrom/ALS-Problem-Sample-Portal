from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0081_issue_description_optional')]

    operations = [
        migrations.AddField(
            model_name='problemcolumn',
            name='distributor_cc_rules',
            field=models.JSONField(default=list, blank=True, help_text='Distributor name match patterns and customer tracking email CC recipients.'),
        ),
    ]
