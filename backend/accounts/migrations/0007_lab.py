from django.db import migrations, models
import django.db.models.deletion


def add_edmonton(apps, schema_editor):
    Lab = apps.get_model('accounts', 'Lab')
    Lab.objects.using(schema_editor.connection.alias).get_or_create(
        code='EDM', defaults={'name': 'Edmonton', 'lab_notification_mode': 'addresses',
        'lab_notification_emails': ['NA.EDM@alsglobal.com'],
        'customer_service_notification_mode': 'staff'})


class Migration(migrations.Migration):
    dependencies = [('accounts', '0006_alter_userprofile_role_label')]
    operations = [
        migrations.CreateModel(name='Lab', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)),
            ('name', models.CharField(max_length=100, unique=True)),
            ('code', models.CharField(max_length=12, unique=True)),
            ('next_container_number', models.PositiveBigIntegerField(default=1)),
            ('lab_notification_mode', models.CharField(max_length=12, default='addresses')),
            ('lab_notification_emails', models.JSONField(default=list, blank=True)),
            ('customer_service_notification_mode', models.CharField(max_length=12, default='staff')),
            ('customer_service_notification_emails', models.JSONField(default=list, blank=True)),
        ], options={'ordering': ['name']}),
        migrations.AddField(model_name='userprofile', name='lab', field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='staff_profiles', to='accounts.lab')),
        migrations.RunPython(add_edmonton, migrations.RunPython.noop),
    ]
