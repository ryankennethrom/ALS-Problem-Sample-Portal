from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0005_revoke_legacy_sessions'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                blank=True,
                choices=[('lab_technician', 'Lab'), ('customer_service', 'Customer Service')],
                max_length=40,
            ),
        ),
    ]
