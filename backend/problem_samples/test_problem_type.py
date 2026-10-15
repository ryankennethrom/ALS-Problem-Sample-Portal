"""Regression tests for the Problem Type column type."""
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
    resolve_problem_type,
)
from .serializers import ProblemColumnSerializer, ProblemSampleSerializer
from .models import selected_problem_type_prompts, ProblemSample
from .views import ProblemAcknowledgementView


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
            column_type=ProblemColumn.TYPE_PROBLEM_TYPE, choices=['Simple', 'Detailed'],
            default_value='Simple', form_mask_rules={
                'Simple': {'columns': {str(self.target.id): 'hidden'}, 'images': 'hidden'},
                'Detailed': {'columns': {str(self.target.id): 'shown'}},
            },
        )
        self.mask_b = ProblemColumn.objects.create(
            table=self.table, name='Form category', field_key='form-category',
            column_type=ProblemColumn.TYPE_PROBLEM_TYPE, choices=['Strict', 'Relaxed'],
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
        resolved = resolve_problem_type(self.table, {
            'form-version': 'Simple', 'form-category': 'Strict',
        })
        self.assertEqual(resolved['reference'], 'required')
        self.assertEqual(resolved['images'], 'required')
        self.assertEqual(resolved['attachments'], 'required')

    def test_shown_wins_over_hidden(self):
        resolved = resolve_problem_type(self.table, {
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


    def test_choice_customer_questions_are_validated_and_snapshotted(self):
        serializer = ProblemColumnSerializer(instance=self.mask_a, data={
            'form_mask_rules': {
                'Simple': {'columns': {str(self.target.id): 'hidden'}, 'customer_details': ' What went wrong? '},
                'Detailed': {'columns': {}, 'customer_details': 'Please attach photos.'},
            },
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        selected = selected_problem_type_prompts(self.table, {
            'form-version': 'Simple', 'form-category': 'Relaxed',
        })
        self.assertEqual(selected, [{'column': 'Form version', 'choice': 'Simple', 'message': 'What went wrong?'}])
        self.mask_a.form_mask_rules = {'Simple': {'customer_details': 'Admin changed this'}}
        self.mask_a.save(update_fields=['form_mask_rules'])
        self.assertEqual(selected[0]['message'], 'What went wrong?')

    def test_multiple_problem_types_produce_independent_customer_questions(self):
        self.mask_a.form_mask_rules['Simple']['customer_details'] = 'What is the issue?'
        self.mask_b.form_mask_rules['Strict']['customer_details'] = 'When did this happen?'
        self.mask_a.save(update_fields=['form_mask_rules'])
        self.mask_b.save(update_fields=['form_mask_rules'])
        prompts = selected_problem_type_prompts(self.table, {
            'form-version': 'Simple', 'form-category': 'Strict',
        })
        self.assertEqual([prompt['message'] for prompt in prompts], ['What is the issue?', 'When did this happen?'])

    def test_non_text_customer_questions_are_rejected(self):
        serializer = ProblemColumnSerializer(instance=self.mask_a, data={
            'form_mask_rules': {'Simple': {'columns': {}, 'customer_details': ['unexpected']}},
        }, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('form_mask_rules', serializer.errors)

    def test_prompt_appears_as_first_public_chat_message(self):
        problem = ProblemSample.objects.create(
            table=self.table, problem_number=99,
            problem_type_prompts=[{
                'column': 'Problem Type', 'choice': 'Leaking container',
                'message': 'Please describe where the leak occurred.',
            }],
        )
        thread = ProblemAcknowledgementView()._public_conversation(problem)
        self.assertEqual(len(thread), 1)
        self.assertEqual(thread[0]['sender'], 'staff')
        self.assertEqual(thread[0]['sender_label'], 'ALS Edmonton')
        self.assertIn('Please describe where the leak occurred.', thread[0]['message'])
