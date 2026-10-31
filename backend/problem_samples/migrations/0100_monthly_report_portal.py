import uuid
from django.db import migrations, models


def allocate_tokens(apps, schema_editor):
    emails = apps.get_model('problem_samples', 'SystemEmail')
    for email in emails.objects.using(schema_editor.connection.alias).all().only('pk').iterator(chunk_size=1000):
        emails.objects.using(schema_editor.connection.alias).filter(pk=email.pk).update(public_token=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0099_terminal_tracking_link_duration')]
    operations = [
        migrations.AddField(model_name='systememail', name='public_token', field=models.UUIDField(null=True, editable=False)),
        migrations.RunPython(allocate_tokens, migrations.RunPython.noop),
        migrations.AlterField(model_name='systememail', name='public_token', field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
        migrations.AddField(model_name='systememail', name='public_expires_at', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='systememail', name='public_revoked_at', field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name='systememail', name='report_snapshot', field=models.JSONField(default=dict, blank=True)),
    ]
