"""Issue Description is optional, and absent from customer chat context."""
import importlib

from django.apps import apps
from django.test import TestCase

from .models import (
    CURRENT_WORKFLOW_DEFAULT,
    ProblemColumn,
    ProblemSample,
    ProblemTable,
    ProblemTrackingLink,
    generate_acknowledgement_token,
)
from .serializers import ProblemSampleSerializer


class IssueDescriptionOptionalTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Issue Description regression table')
        self.issue_column = ProblemColumn.objects.create(
            table=self.table, name='Issue Description', field_key='issue-description',
            column_type=ProblemColumn.TYPE_LONG_TEXT, required=True,
        )
        self.another_required_column = ProblemColumn.objects.create(
            table=self.table, name='Tracking Number', field_key='tracking-number',
            required=True, default_value='TRK123',
        )

    def make_optional(self):
        migration = importlib.import_module(
            'problem_samples.migrations.0081_issue_description_optional'
        )
        migration.make_issue_description_optional(apps, None)
        self.issue_column.refresh_from_db()

    def test_migration_relaxes_only_issue_description(self):
        self.make_optional()
        self.assertFalse(self.issue_column.required)
        self.another_required_column.refresh_from_db()
        self.assertTrue(self.another_required_column.required)

    def test_ticket_can_be_created_without_issue_description(self):
        self.make_optional()
        serializer = ProblemSampleSerializer(data={
            'table': str(self.table.pk),
            'custom_values': {'tracking-number': 'TRK123'},
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertFalse(serializer.validated_data['custom_values'].get('issue-description'))

    def test_customer_chat_excludes_issue_description_but_keeps_problem_type_questions(self):
        self.make_optional()
        ProblemColumn.objects.create(
            table=self.table, name='Problem Type', field_key='problem-type',
            column_type=ProblemColumn.TYPE_PROBLEM_TYPE, choices=['Damaged'],
        )
        ticket = ProblemSample.objects.create(
            table=self.table, problem_number=42,
            current_workflow=CURRENT_WORKFLOW_DEFAULT,
            issue_description='Internal issue description should not be in chat header',
            custom_values={
                'issue-description': 'Internal issue description should not be in chat header',
                'problem-type': 'Damaged',
            },
            problem_type_prompts=[{
                'column': 'Problem Type', 'choice': 'Damaged',
                'message': 'Please provide a picture of the damaged sample.',
            }],
        )
        ProblemTrackingLink.objects.create(
            ticket=ticket, tracking_token=generate_acknowledgement_token(),
        )
        url = f'/api/public/problem-sample-tracking/{ticket.acknowledgement_token}/'
        result = self.client.get(url)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('problem_issue', result.data)
        self.assertEqual(result.data['problem_type'], 'Damaged')
        self.assertTrue(any(
            'Please provide a picture' in message['message']
            for message in result.data['conversation']
        ))
