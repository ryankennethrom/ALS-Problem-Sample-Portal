from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0071_problemmention'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemmention',
            name='notified_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name='problemmention',
            name='email_confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
