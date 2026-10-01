from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0072_problemmention_email_audit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemcolumn',
            name='group_role',
            field=models.CharField(
                blank=True,
                choices=[('lab_technician', 'Lab'), ('customer_service', 'Customer Service')],
                max_length=40,
            ),
        ),
    ]
