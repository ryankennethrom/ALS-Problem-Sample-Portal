"""Merge local migration 0093 with the customer-return-label migration.

The previous release introduced 0093_customer_return_label while a separately
created 0093_alter_labemailtemplate_id_and_more migration already existed in
some local repositories. Both parent migrations must be applied before this
no-op merge. No data or schema changes are performed here.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('problem_samples', '0093_alter_labemailtemplate_id_and_more'),
        ('problem_samples', '0093_customer_return_label'),
    ]

    operations = []
