from django.db import migrations, models


def rename_existing_masks(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(column_type='ticket_creator_form_mask').update(column_type='problem_type')


def revert_existing_masks(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(column_type='problem_type').update(column_type='ticket_creator_form_mask')


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0077_ticket_creator_form_mask')]

    operations = [
        migrations.AddField(
            model_name='preparedproblemsample', name='problem_type_prompts',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='problemsample', name='problem_type_prompts',
            field=models.JSONField(
                blank=True, default=list,
                help_text='Customer-facing questions snapshotted from selected Problem Type choices.',
            ),
        ),
        migrations.AlterField(
            model_name='problemcolumn', name='form_mask_rules',
            field=models.JSONField(blank=True, default=dict, help_text='Choice label -> form visibility and customer instructions.'),
        ),
        migrations.AlterField(
            model_name='problemcolumn', name='column_type',
            field=models.CharField(max_length=30, default='text', choices=[
                ('text', 'Single line of text'), ('long_text', 'Multiple lines of text'),
                ('number', 'Number'), ('choice', 'Choice'), ('multi_choice', 'Multiple choice'),
                ('date', 'Date'), ('date_today', 'Date (Today)'), ('datetime', 'Date and time'),
                ('time', 'Time'), ('boolean', 'Yes / No'), ('email', 'Email'), ('phone', 'Phone Number'),
                ('url', 'URL'), ('fixed', 'Fixed Value'), ('group', 'Group'),
                ('distributor', 'Distributor'), ('end_user', 'End User'), ('brand', 'Brand'),
                ('client_email', 'Client Email'), ('row_creator', 'Row Creator'),
                ('recent_row_modifier', 'Recent Row Modifier'),
                ('intercolumn_controller', 'Intercolumn Value Controller'),
                ('problem_type', 'Problem Type'),
            ]),
        ),
        migrations.RunPython(rename_existing_masks, revert_existing_masks),
    ]
