from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('customers', '0002_customer_export_fields'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='customer',
            name='unique_customer_company_email',
        ),
    ]
