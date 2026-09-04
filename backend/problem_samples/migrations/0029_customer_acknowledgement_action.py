from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0028_fixed_status_values'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemsample',
            name='customer_acknowledgement_action',
            field=models.CharField(
                blank=True,
                choices=[
                    ('dispose', 'Dispose Sample(s)'),
                    ('ship_back', 'Ship back samples'),
                    ('neither', 'Neither, right now, I will be contacting customer service'),
                ],
                db_index=True,
                help_text='Optional follow-up action selected by the customer after acknowledging the problem sample notification.',
                max_length=20,
            ),
        ),
    ]
