"""Regression coverage for the Distributor-based tracking email CC rules."""
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from .models import ProblemColumn, ProblemSample, ProblemTable
from .serializers import ProblemColumnSerializer
from .views import _distributor_auto_cc


class DistributorCCRulesTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Distributor CC test')
        self.column = ProblemColumn.objects.create(
            table=self.table, name='Distributor', field_key='distributor',
            column_type=ProblemColumn.TYPE_DISTRIBUTOR,
        )

    def test_rules_are_saved_and_merged_case_insensitively(self):
        serializer = ProblemColumnSerializer(self.column, data={'distributor_cc_rules': [
            {'match_type': 'wildcard', 'pattern': 'Acme*', 'cc_emails': ['cc@example.com', 'other@example.com']},
            {'match_type': 'contains', 'pattern': 'SUPPLIES', 'cc_emails': ['CC@EXAMPLE.COM', 'third@example.com']},
        ]}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        problem = ProblemSample.objects.create(table=self.table, problem_number=202, custom_values={'distributor': 'ACME Supplies'})
        self.assertEqual(_distributor_auto_cc(problem), ['cc@example.com', 'other@example.com', 'third@example.com'])

    def test_non_matching_and_empty_values_have_no_cc(self):
        self.column.distributor_cc_rules = [{'match_type': 'contains', 'pattern': 'acme', 'cc_emails': ['cc@example.com']}]
        self.column.save(update_fields=['distributor_cc_rules'])
        problem = ProblemSample.objects.create(table=self.table, problem_number=203, custom_values={'distributor': 'Another Company'})
        self.assertEqual(_distributor_auto_cc(problem), [])
        problem.custom_values = {'distributor': ''}
        problem.save(update_fields=['custom_values'])
        self.assertEqual(_distributor_auto_cc(problem), [])

    def test_invalid_patterns_and_cc_addresses_are_rejected(self):
        cases = [
            {'match_type': 'contains', 'pattern': '', 'cc_emails': ['good@example.com']},
            {'match_type': 'regex', 'pattern': '.*', 'cc_emails': ['good@example.com']},
            {'match_type': 'exact', 'pattern': 'Acme', 'cc_emails': ['not an email']},
            {'match_type': 'exact', 'pattern': 'Acme', 'cc_emails': []},
        ]
        for rule in cases:
            with self.subTest(rule=rule):
                serializer = ProblemColumnSerializer(self.column, data={'distributor_cc_rules': [rule]}, partial=True)
                self.assertFalse(serializer.is_valid())
                self.assertIn('distributor_cc_rules', serializer.errors)

    def test_non_distributor_column_rules_are_cleared(self):
        serializer = ProblemColumnSerializer(self.column, data={
            'column_type': 'text',
            'distributor_cc_rules': [{'match_type': 'contains', 'pattern': 'Acme', 'cc_emails': ['cc@example.com']}],
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        column = serializer.save()
        self.assertEqual(column.distributor_cc_rules, [])
