"""Separates one-time column backfill from future-ticket defaults."""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import UserProfile
from .models import ProblemColumn, ProblemSample, ProblemTable
from .serializers import ProblemSampleSerializer


class FillExistingColumnTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='columnadmin', password='test')
        UserProfile.objects.create(user=self.user, is_admin=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.table = ProblemTable.objects.create(name='Column backfill test')
        self.first = ProblemSample.objects.create(table=self.table, problem_number=1, custom_values={'legacy': 'keep'})
        self.second = ProblemSample.objects.create(table=self.table, problem_number=2, custom_values={})

    def add(self, **settings):
        return self.client.post('/api/problem-columns/', {
            'table': str(self.table.pk), 'name': settings.pop('name', 'New Field'),
            'column_type': settings.pop('column_type', 'text'), **settings,
        }, format='json')

    def test_default_only_fills_future_tickets_not_existing(self):
        result = self.add(default_value='future')
        self.assertEqual(result.status_code, 201, result.data)
        column = ProblemColumn.objects.get(pk=result.data['id'])
        self.assertEqual(column.default_value, 'future')
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertNotIn(column.field_key, self.first.custom_values)
        self.assertNotIn(column.field_key, self.second.custom_values)
        new_ticket = ProblemSampleSerializer(data={'table': str(self.table.pk), 'custom_values': {}})
        self.assertTrue(new_ticket.is_valid(), new_ticket.errors)
        self.assertEqual(new_ticket.validated_data['custom_values'][column.field_key], 'future')

    def test_fill_only_populates_existing_and_does_not_become_default(self):
        result = self.add(fill_existing_with='legacy', name='Historical')
        self.assertEqual(result.status_code, 201, result.data)
        self.assertNotIn('fill_existing_with', result.data)
        column = ProblemColumn.objects.get(pk=result.data['id'])
        self.assertIsNone(column.default_value)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.custom_values, {'legacy': 'keep', column.field_key: 'legacy'})
        self.assertEqual(self.second.custom_values[column.field_key], 'legacy')
        new_ticket = ProblemSampleSerializer(data={'table': str(self.table.pk), 'custom_values': {}})
        self.assertTrue(new_ticket.is_valid(), new_ticket.errors)
        self.assertFalse(new_ticket.validated_data['custom_values'].get(column.field_key))

    def test_both_values_are_independent(self):
        result = self.add(default_value='future', fill_existing_with='past')
        self.assertEqual(result.status_code, 201, result.data)
        column = ProblemColumn.objects.get(pk=result.data['id'])
        self.first.refresh_from_db()
        self.assertEqual(self.first.custom_values[column.field_key], 'past')
        self.assertEqual(column.default_value, 'future')

    def test_required_needs_backfill_even_with_future_default(self):
        result = self.add(required=True, default_value='future')
        self.assertEqual(result.status_code, 400, result.data)
        self.assertIn('fill_existing_with', result.data)
        self.assertFalse(ProblemColumn.objects.filter(name='New Field', table=self.table).exists())
        result = self.add(required=True, fill_existing_with='past')
        self.assertEqual(result.status_code, 201, result.data)

    def test_choice_validation_and_atomic_rollback(self):
        result = self.add(column_type='choice', choices=['A', 'B'], fill_existing_with='C')
        self.assertEqual(result.status_code, 400)
        self.assertIn('fill_existing_with', result.data)
        self.first.refresh_from_db()
        self.assertEqual(self.first.custom_values, {'legacy': 'keep'})

    def test_false_and_zero_are_valid_backfills(self):
        response_bool = self.add(name='Active', column_type='boolean', fill_existing_with=False)
        self.assertEqual(response_bool.status_code, 201, response_bool.data)
        response_number = self.add(name='Quantity', column_type='number', fill_existing_with=0)
        self.assertEqual(response_number.status_code, 201, response_number.data)
        self.first.refresh_from_db()
        self.assertIs(self.first.custom_values['active'], False)
        self.assertEqual(self.first.custom_values['quantity'], 0)

    def test_fill_instruction_cannot_be_used_on_column_edit(self):
        column = ProblemColumn.objects.create(table=self.table, name='Existing', field_key='existing')
        result = self.client.patch('/api/problem-columns/%s/' % column.pk, {'fill_existing_with': 'hack'}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertIn('fill_existing_with', result.data)

    def test_automatic_types_keep_existing_behavior(self):
        response = self.add(name='Created Today', column_type='date_today', fill_existing_with='2026-01-01')
        self.assertEqual(response.status_code, 400)
        self.assertIn('fill_existing_with', response.data)
