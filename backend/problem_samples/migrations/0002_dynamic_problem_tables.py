import uuid
from django.db import migrations, models
import django.db.models.deletion


def create_default_table(apps, schema_editor):
    ProblemTable = apps.get_model('problem_samples', 'ProblemTable')
    ProblemSample = apps.get_model('problem_samples', 'ProblemSample')
    table = ProblemTable.objects.create(name='Problem Samples', description='Default problem sample table', is_default=True)
    ProblemSample.objects.filter(table__isnull=True).update(table=table)


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0001_initial'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProblemTable',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=160)),
                ('description', models.TextField(blank=True)),
                ('is_default', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='problem_tables_created', to='auth.user')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='ProblemColumn',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=160)),
                ('field_key', models.SlugField(max_length=180)),
                ('column_type', models.CharField(choices=[('text', 'Single line of text'), ('long_text', 'Multiple lines of text'), ('number', 'Number'), ('choice', 'Choice'), ('multi_choice', 'Multiple choice'), ('date', 'Date'), ('datetime', 'Date and time'), ('time', 'Time'), ('boolean', 'Yes / No'), ('email', 'Email'), ('url', 'URL')], default='text', max_length=30)),
                ('required', models.BooleanField(default=False)),
                ('searchable', models.BooleanField(default=True)),
                ('choices', models.JSONField(blank=True, default=list)),
                ('default_value', models.JSONField(blank=True, null=True)),
                ('position', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('modified_at', models.DateTimeField(auto_now=True)),
                ('table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='columns', to='problem_samples.problemtable')),
            ],
            options={'ordering': ['position', 'created_at']},
        ),
        migrations.AddConstraint(
            model_name='problemcolumn',
            constraint=models.UniqueConstraint(fields=('table', 'field_key'), name='unique_problem_column_key_per_table'),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='custom_values',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='problemsample',
            name='table',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='problem_samples', to='problem_samples.problemtable'),
        ),
        migrations.RunPython(create_default_table, migrations.RunPython.noop),
    ]
