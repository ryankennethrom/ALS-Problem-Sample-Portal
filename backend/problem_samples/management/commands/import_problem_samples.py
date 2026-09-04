import csv
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from problem_samples.models import (
    ProblemSample, ProblemComment, ProblemTable, ProblemColumn,
    PROBLEM_STATUS_AUTOMATICALLY_DISPOSED, PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL, PROBLEM_STATUS_TO_BE_DISPOSED, PROBLEM_STATUS_TO_BE_SHIPPED_BACK,
    PROBLEM_STATUS_DISPOSED, PROBLEM_STATUS_SHIPPED_BACK,
)


def clean(row,key): return (row.get(key) or '').strip()

def parse_date(value):
    if not value: return None
    for fmt in ('%m/%d/%Y','%Y-%m-%d','%m/%d/%y'):
        try: return datetime.strptime(value,fmt).date()
        except ValueError: pass
    return None

def parse_int(value):
    try: return int(value) if value.strip() else None
    except (ValueError,AttributeError): return None

def parse_bool(value): return str(value or '').strip().lower() in {'1','true','yes','y','x'}


def normalize_status(value, *, email_confirmation=False):
    text = str(value or '').strip()
    folded = text.casefold()
    if folded == PROBLEM_STATUS_DISPOSED.casefold():
        return PROBLEM_STATUS_DISPOSED
    if folded in {'to be disposed', PROBLEM_STATUS_TO_BE_DISPOSED.casefold()}:
        return PROBLEM_STATUS_TO_BE_DISPOSED
    if folded == PROBLEM_STATUS_TO_BE_SHIPPED_BACK.casefold():
        return PROBLEM_STATUS_TO_BE_SHIPPED_BACK
    if folded == PROBLEM_STATUS_SHIPPED_BACK.casefold():
        return PROBLEM_STATUS_SHIPPED_BACK
    if folded in {PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL.casefold(), 'problem acknowledged by customer'}:
        return PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL
    if folded in {
        PROBLEM_STATUS_AUTOMATICALLY_DISPOSED.casefold(),
        'customer not yet contacted',
        'customer emailed by system',
        'notified',
    } or email_confirmation:
        return PROBLEM_STATUS_AUTOMATICALLY_DISPOSED
    # New/unknown rows start with automatic disposal halted unless the imported
    # record explicitly indicates that the automatic-disposal workflow is active.
    return PROBLEM_STATUS_HALTED_AUTOMATIC_DISPOSAL


class Command(BaseCommand):
    help='Import a legacy Problem Samples CSV export.'

    def add_arguments(self,parser): parser.add_argument('csv_path')

    def handle(self,*args,**opts):
        created=updated=0
        table = ProblemTable.objects.filter(is_default=True).first() or ProblemTable.objects.create(name='Problem Samples', description='Default problem sample table', is_default=True)
        ProblemColumn.objects.update_or_create(
            table=table, field_key='problem-id',
            defaults={'name':'Problem ID','column_type':'number','required':True,'searchable':True,'choices':[],'default_value':None,'position':0,'is_system':True},
        )
        available_keys = set(table.columns.filter(is_system=False).values_list('field_key', flat=True))

        with open(opts['csv_path'],newline='',encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                source_id=clean(row,'ID')
                received = parse_date(clean(row,'Date Received'))
                count = parse_int(clean(row,'Number of problem samples in shipment'))
                notify = parse_bool(clean(row,'Notify'))
                email_confirmation = parse_bool(clean(row,'Email Confirmation'))
                defaults={
                    'status':normalize_status(clean(row,'Status'), email_confirmation=email_confirmation),'als_tracking_number':clean(row,'ALS Sample Tracking Number'),
                    'problem_sample_count':count,
                    'brand':clean(row,'Brand'),'distributor':clean(row,'Distributor '),'end_user':clean(row,'End User'),
                    'date_received':received,'problem_type':clean(row,'Problem Type'),
                    'issue_description':clean(row,'Issue description'),'client_contact_email':clean(row,'Client Contact Email'),
                    'courier':clean(row,'Courier'),'courier_tracking_number':clean(row,'Courier Tracking '),
                    'legacy_created_by':clean(row,'Created By'),'legacy_modified_by':clean(row,'Modified By'),
                    'notify':notify,'email_confirmation':email_confirmation,
                }
                existing = ProblemSample.objects.filter(table=table, source_id=source_id).first()
                if existing:
                    for field, value in defaults.items():
                        setattr(existing, field, value)
                    existing.save()
                    obj, was_created = existing, False
                else:
                    with transaction.atomic():
                        locked = ProblemTable.objects.select_for_update().get(pk=table.pk)
                        preferred = parse_int(source_id)
                        if preferred and preferred > 0 and not ProblemSample.objects.filter(table=locked, problem_number=preferred).exists():
                            number = preferred
                            if locked.next_problem_id <= number:
                                locked.next_problem_id = number + 1
                                locked.save(update_fields=['next_problem_id', 'modified_at'])
                        else:
                            number = locked.next_problem_id
                            locked.next_problem_id = number + 1
                            locked.save(update_fields=['next_problem_id', 'modified_at'])
                        obj = ProblemSample.objects.create(table=locked, source_id=source_id, problem_number=number, **defaults)
                        was_created = True

                # Keep the dynamic/default-table view in sync when the legacy columns
                # were seeded by migration 0003.
                dynamic = {
                    'status': defaults['status'],
                    'als-sample-tracking-number': defaults['als_tracking_number'],
                    'number-of-problem-samples-in-shipment': count,
                    'brand': defaults['brand'],
                    'distributor': defaults['distributor'],
                    'end-user': defaults['end_user'],
                    'date-received': received.isoformat() if received else '',
                    'problem-type': defaults['problem_type'],
                    'issue-description': defaults['issue_description'],
                    'created-by': defaults['legacy_created_by'],
                    'client-contact-email': defaults['client_contact_email'],
                    'courier': defaults['courier'],
                    'courier-tracking': defaults['courier_tracking_number'],
                    'modified-by': defaults['legacy_modified_by'],
                    'notify': notify,
                    'email-confirmation': email_confirmation,
                }
                if available_keys:
                    values = dict(obj.custom_values or {})
                    values.update({k:v for k,v in dynamic.items() if k in available_keys})
                    obj.custom_values = values
                    obj.save(update_fields=['custom_values'])

                created += int(was_created); updated += int(not was_created)
                comment=clean(row,'Comment/ Follow Up')
                if comment and not obj.comments.filter(body=comment).exists():
                    ProblemComment.objects.create(problem=obj,body=comment,legacy_author=defaults['legacy_modified_by'] or defaults['legacy_created_by'])
        self.stdout.write(self.style.SUCCESS(f'Imported: {created} created, {updated} updated.'))
