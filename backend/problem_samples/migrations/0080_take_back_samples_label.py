from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0079_dumping_containers')]

    operations = [
        migrations.AlterField(
            model_name='problemsample', name='customer_acknowledgement_action',
            field=models.CharField(
                max_length=20, blank=True, db_index=True,
                help_text='Optional follow-up action selected by the customer from the problem sample tracking link.',
                choices=[
                    ('dispose', 'Dispose Sample(s)'),
                    ('ship_back', 'Take back sample(s)'),
                    ('hold', 'Hold sample'),
                    ('requested_info', 'Message us about the issue'),
                ],
            ),
        ),
    ]
