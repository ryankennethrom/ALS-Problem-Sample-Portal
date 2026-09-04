from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0021_brand_column_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='problemcolumn',
            name='description',
            field=models.TextField(blank=True),
        ),
    ]
