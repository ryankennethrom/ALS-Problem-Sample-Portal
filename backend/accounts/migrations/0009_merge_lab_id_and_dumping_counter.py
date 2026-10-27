"""Merge the local Lab ID alteration with the dumping-container counter.

Some existing installations already have accounts.0008_alter_lab_id. The
independent 0008_next_dumping_container_number migration in the DC update
branched at accounts.0007_lab. Both branches must be preserved and applied
before the problem_samples DC-renumbering migration runs.

This merge adds no columns and changes no data.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0008_alter_lab_id'),
        ('accounts', '0008_next_dumping_container_number'),
    ]

    operations = []
