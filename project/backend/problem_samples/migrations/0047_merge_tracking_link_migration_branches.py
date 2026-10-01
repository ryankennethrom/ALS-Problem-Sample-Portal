from django.db import migrations


class Migration(migrations.Migration):
    """Merge the token-field and persistent tracking-link migration branches."""

    dependencies = [
        ('problem_samples', '0045_alter_problemsample_acknowledgement_token'),
        ('problem_samples', '0046_reactivate_tracking_links_for_followup_statuses'),
    ]

    operations = []
