from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0075_phone_number_column_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='problemsample',
            name='customer_acknowledgement_action',
            field=models.CharField(
                blank=True,
                choices=[
                    ('dispose', 'Dispose Sample(s)'),
                    ('ship_back', 'Ship back samples'),
                    ('hold', 'Hold sample'),
                    ('requested_info', 'Message us about the issue'),
                ],
                db_index=True,
                help_text='Optional follow-up action selected by the customer from the problem sample tracking link.',
                max_length=20,
            ),
        ),
    ]
