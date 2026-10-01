from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0016_problemattachment'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemimage',
            name='include_in_customer_notification',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='problemattachment',
            name='include_in_customer_notification',
            field=models.BooleanField(default=True),
        ),
    ]
