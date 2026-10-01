from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0070_rename_waiting_for_customer_workflow'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProblemMention',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('comment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='problem_samples.problemcomment')),
                ('mentioned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='ticket_mentions_created', to=settings.AUTH_USER_MODEL)),
                ('mentioned_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ticket_mentions', to=settings.AUTH_USER_MODEL)),
                ('problem', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='problem_samples.problemsample')),
            ],
            options={'ordering': ['-created_at', '-id']},
        ),
        migrations.AddConstraint(
            model_name='problemmention',
            constraint=models.UniqueConstraint(fields=('comment', 'mentioned_user'), name='unique_ticket_comment_mention_user'),
        ),
        migrations.AddIndex(
            model_name='problemmention',
            index=models.Index(fields=['mentioned_user', 'read_at', '-created_at'], name='ticket_mention_inbox_idx'),
        ),
    ]
