"""Regression tests for the Ticket Creator Form Mask column type."""
from types import SimpleNamespace

from django.test import TestCase

from .models import (
    CURRENT_WORKFLOW_CHOICES,
    CURRENT_WORKFLOW_DEFAULT,
    DISPOSE_AUTOMATICALLY_CHOICES,
    DISPOSE_AUTOMATICALLY_NO,
    ProblemColumn,
    ProblemTable,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
    resolve_ticket_creator_form_mask,
)
from .serializers import ProblemColumnSerializer, ProblemSampleSerializer


class TicketCreatorFormMaskTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Masked form test', is_default=True)
        ProblemColumn.objects.create(
            table=self.table, name='Current Workflow', field_key=SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE, choices=list(CURRENT_WORKFLOW_CHOICES),
            default_value=CURRENT_WORKFLOW_DEFAULT, required=True, is_system=True,
        )
        ProblemColumn.objects.create(
            table=self.table, name='Dispose Automatically', field_key=SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE, choices=list(DISPOSE_AUTOMATICALLY_CHOICES),
            default_value=DISPOSE_AUTOMATICALLY_NO, required=True, is_system=True,
        )
        self.target = ProblemColumn.objects.create(
            table=self.table, name='Reference', field_key='reference', column_type=ProblemColumn.TYPE_TEXT,
        )
        self.mask_a = ProblemColumn.objects.create(
            table=self.table, name='Form version', field_key='form-version',
            column_type=ProblemColumn.TYPE_TICKET_CREATOR_FORM_MASK, choices=['Simple', 'Detailed'],
            default_value='Simple', form_mask_rules={
                'Simple': {'columns': {str(self.target.id): 'hidden'}, 'images': 'hidden'},
                'Detailed': {'columns': {str(self.target.id): 'shown'}},
            },
        )
        self.mask_b = ProblemColumn.objects.create(
            table=self.table, name='Form category', field_key='form-category',
            column_type=ProblemColumn.TYPE_TICKET_CREATOR_FORM_MASK, choices=['Strict', 'Relaxed'],
            default_value='Strict', form_mask_rules={
                'Strict': {'columns': {str(self.target.id): 'required'}, 'images': 'required', 'attachments': 'required'},
                'Relaxed': {'columns': {str(self.target.id): 'hidden'}},
            },
        )

    def sample_serializer(self, values):
        return ProblemSampleSerializer(
            data={'table': str(self.table.pk), 'custom_values': values},
            context={'request': SimpleNamespace(user=SimpleNamespace(is_authenticated=False))},
        )

    def test_required_wins_over_hidden_for_columns_and_images(self):
        resolved = resolve_ticket_creator_form_mask(self.table, {
            'form-version': 'Simple', 'form-category': 'Strict',
        })
        self.assertEqual(resolved['reference'], 'required')
        self.assertEqual(resolved['images'], 'required')
        self.assertEqual(resolved['attachments'], 'required')

    def test_shown_wins_over_hidden(self):
        resolved = resolve_ticket_creator_form_mask(self.table, {
            'form-version': 'Detailed', 'form-category': 'Relaxed',
        })
        self.assertEqual(resolved['reference'], 'shown')

    def test_hidden_field_is_discarded_from_new_tickets(self):
        serializer = self.sample_serializer({
            'form-version': 'Simple', 'form-category': 'Relaxed', 'reference': 'malicious-hidden-value',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertNotIn('reference', serializer.validated_data['custom_values'])

    def test_required_by_mask_is_enforced_on_new_tickets(self):
        serializer = self.sample_serializer({
            'form-version': 'Simple', 'form-category': 'Strict',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('reference', serializer.errors['custom_values'])

    def test_rejects_hiding_database_required_column_without_default(self):
        self.target.required = True
        self.target.save(update_fields=['required'])
        serializer = ProblemColumnSerializer(instance=self.mask_a, data={
            'form_mask_rules': self.mask_a.form_mask_rules,
        }, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('form_mask_rules', serializer.errors)

    def test_database_required_hidden_column_uses_default(self):
        self.target.required = True
        self.target.default_value = 'Automatic reference'
        self.target.save(update_fields=['required', 'default_value'])
        serializer = self.sample_serializer({
            'form-version': 'Simple', 'form-category': 'Relaxed',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['custom_values']['reference'], 'Automatic reference')
