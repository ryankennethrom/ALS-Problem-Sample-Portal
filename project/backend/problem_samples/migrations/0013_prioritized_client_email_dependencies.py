from django.db import migrations, models
import django.db.models.deletion


def copy_legacy_dependency(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    for column in ProblemColumn.objects.filter(column_type='client_email').exclude(depends_on_column_id=None):
        if not column.client_email_dependencies:
            column.client_email_dependencies = [str(column.depends_on_column_id)]
            column.save(update_fields=['client_email_dependencies'])


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0012_client_email_column_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemcolumn',
            name='client_email_dependencies',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Ordered ProblemColumn UUIDs used as Client Email company fallbacks.',
            ),
        ),
        migrations.AlterField(
            model_name='problemcolumn',
            name='depends_on_column',
            field=models.ForeignKey(
                blank=True,
                help_text='Legacy first dependency for Client Email columns.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='dependent_columns',
                to='problem_samples.problemcolumn',
            ),
        ),
        migrations.RunPython(copy_legacy_dependency, migrations.RunPython.noop),
    ]
