from django.test import TestCase
from rest_framework import serializers

from .models import ProblemColumn, ProblemTable
from .serializers import _validate_custom_value


class PhoneColumnTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Phone tests')
        self.column = ProblemColumn.objects.create(
            table=self.table,
            name='Phone',
            field_key='phone',
            column_type=ProblemColumn.TYPE_PHONE,
        )

    def test_phone_column_choice_exists(self):
        self.assertIn((ProblemColumn.TYPE_PHONE, 'Phone Number'), ProblemColumn.COLUMN_TYPES)

    def test_phone_value_preserves_common_formatting(self):
        value = '+1 (780) 555-1234 ext 42'
        self.assertEqual(_validate_custom_value(self.column, value), value)

    def test_phone_value_accepts_simple_and_international_numbers(self):
        self.assertEqual(_validate_custom_value(self.column, '780-555-1234'), '780-555-1234')
        self.assertEqual(_validate_custom_value(self.column, '+44 20 7946 0958'), '+44 20 7946 0958')

    def test_phone_value_rejects_non_phone_text_and_too_few_digits(self):
        with self.assertRaises(serializers.ValidationError):
            _validate_custom_value(self.column, 'call me later')
        with self.assertRaises(serializers.ValidationError):
            _validate_custom_value(self.column, '123')
