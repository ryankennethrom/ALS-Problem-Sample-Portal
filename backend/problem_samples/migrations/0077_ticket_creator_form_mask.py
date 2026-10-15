from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0076_customer_message_issue_label')]
    operations = [
        migrations.AddField(model_name='problemcolumn', name='form_mask_rules', field=models.JSONField(default=dict, blank=True, help_text='Choice label -> per-column, images and attachments states for ticket creation.')),
        migrations.AlterField(model_name='problemcolumn', name='column_type', field=models.CharField(max_length=30, default='text', choices=[('text', 'Single line of text'), ('long_text', 'Multiple lines of text'), ('number', 'Number'), ('choice', 'Choice'), ('multi_choice', 'Multiple choice'), ('date', 'Date'), ('date_today', 'Date (Today)'), ('datetime', 'Date and time'), ('time', 'Time'), ('boolean', 'Yes / No'), ('email', 'Email'), ('phone', 'Phone Number'), ('url', 'URL'), ('fixed', 'Fixed Value'), ('group', 'Group'), ('distributor', 'Distributor'), ('end_user', 'End User'), ('brand', 'Brand'), ('client_email', 'Client Email'), ('row_creator', 'Row Creator'), ('recent_row_modifier', 'Recent Row Modifier'), ('intercolumn_controller', 'Intercolumn Value Controller'), ('ticket_creator_form_mask', 'Ticket Creator Form Mask')])),
    ]
