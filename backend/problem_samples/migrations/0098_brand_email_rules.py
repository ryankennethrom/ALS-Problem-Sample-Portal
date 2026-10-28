"""Move distributor-owned email rules to Brand with company-Brand sources."""
import copy
import uuid
from django.db import migrations, models


def move_rules(apps, schema_editor):
    Column = apps.get_model('problem_samples', 'ProblemColumn')
    SystemEmail = apps.get_model('problem_samples', 'SystemEmail')
    for table_id in Column.objects.filter(column_type='distributor').values_list('table_id', flat=True).distinct():
        distributors = list(Column.objects.filter(table_id=table_id, column_type='distributor').order_by('position', 'created_at'))
        distributors = [column for column in distributors if column.distributor_cc_rules]
        if not distributors:
            continue
        brand = Column.objects.filter(table_id=table_id, column_type='brand').order_by('position', 'created_at').first()
        if brand is None:
            # Never discard configured email recipients just because a table lacks a Brand field.
            used = set(Column.objects.filter(table_id=table_id).values_list('field_key', flat=True))
            key = next((value for value in ('brand', 'email-rule-brand') if value not in used), 'brand-email-rules')
            while key in used:
                key = f'brand-email-rules-{uuid.uuid4().hex[:6]}'
            brand = Column.objects.create(table_id=table_id, name='Brand', field_key=key,
                                          column_type='brand', position=max(c.position for c in distributors)+1)
        deps = list(brand.company_brand_dependencies or [])
        rules = list(brand.brand_cc_rules or [])
        for distributor in distributors:
            source_id = str(distributor.pk)
            if source_id not in deps:
                deps.append(source_id)
            for old in distributor.distributor_cc_rules:
                if not isinstance(old, dict):
                    continue
                item = copy.deepcopy(old)
                item['sources'] = [source_id]
                # Old patterns matched company NAMES; they must be rechecked against
                # exported Brand values before customer CC or monthly mail can resume.
                item['pending_brand_review'] = True
                existing_ids = {str(rule.get('id')) for rule in rules if isinstance(rule, dict)}
                old_id = item.get('id')
                if not item.get('id') or str(item['id']) in existing_ids:
                    item['id'] = str(uuid.uuid4())
                rules.append(item)
                # Reassign queued/sent report snapshots so scheduled deduplication
                # still works after rules move from Distributor to Brand columns.
                try:
                    parsed_old_id = uuid.UUID(str(old_id))
                except (ValueError, TypeError, AttributeError):
                    parsed_old_id = None
                if parsed_old_id:
                    SystemEmail.objects.filter(source_column_id=distributor.pk,
                                               rule_identifier=parsed_old_id).update(
                        source_column_id=brand.pk, rule_identifier=item['id'])
        brand.company_brand_dependencies = deps
        brand.brand_cc_rules = rules
        brand.save(update_fields=['company_brand_dependencies', 'brand_cc_rules'])


class Migration(migrations.Migration):
    dependencies = [('problem_samples', '0097_reactivate_empty_edmonton_pc_00003')]
    operations = [
        migrations.AddField('problemcolumn', 'company_brand_dependencies', models.JSONField(default=list, blank=True,
              help_text='Company column IDs whose imported Brand values may be used in Brand email rules.')),
        migrations.AddField('problemcolumn', 'brand_cc_rules', models.JSONField(default=list, blank=True,
              help_text='Email CC/monthly report rules based on ticket Brand or dependent company Brands.')),
        migrations.RunPython(move_rules, migrations.RunPython.noop),
        migrations.RemoveField('problemcolumn', 'distributor_cc_rules'),
    ]
