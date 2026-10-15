from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0078_problem_type_customer_questions')]

    operations = [
        migrations.AddField(
            model_name='problemcontainer', name='is_dumping',
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name='problemcontainer', name='source_container',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='dumping_containers', to='problem_samples.problemcontainer',
                                    help_text='Original physical container emptied into this dumping container.'),
        ),
        migrations.AddField(
            model_name='problemcontainer', name='dumped_sample_ids',
            field=models.JSONField(blank=True, default=list,
                                   help_text='Ticket UUIDs originally transferred here, retained after undo for audit.'),
        ),
        migrations.AddField(
            model_name='problemcontainer', name='restored_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='problemcontainer', name='restored_to_container',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='restored_dumping_containers', to='problem_samples.problemcontainer'),
        ),
    ]
