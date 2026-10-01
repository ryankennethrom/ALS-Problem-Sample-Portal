from django.db import migrations


FIELD_KEY = 'system-days-until-automatic-disposal'
OLD_NAME = 'Days until automatic disposal'
NEW_NAME = 'Days until up for disposal'


def forward(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key=FIELD_KEY).update(name=NEW_NAME)


def reverse(apps, schema_editor):
    ProblemColumn = apps.get_model('problem_samples', 'ProblemColumn')
    ProblemColumn.objects.filter(field_key=FIELD_KEY).update(name=OLD_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0040_automatic_disposal_expiration_anchor'),
    ]

    operations = [
        migrations.RunPython(forward, reverse),
    ]
