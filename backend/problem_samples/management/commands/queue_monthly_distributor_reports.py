from django.core.management.base import BaseCommand
from problem_samples.system_email_service import queue_due_monthly_reports


class Command(BaseCommand):
    help = 'Queue due Distributor monthly reports without sending them. Safe to run every day.'

    def handle(self, *args, **options):
        result = queue_due_monthly_reports()
        self.stdout.write(self.style.SUCCESS(
            f'Queued {result["created"]} new monthly system emails for {result["period_start"]} through {result["period_end"]} (end exclusive).'
        ))
