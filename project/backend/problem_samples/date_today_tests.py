from types import SimpleNamespace

from django.test import TestCase
from django.utils import timezone

from .models import (
    CURRENT_WORKFLOW_CHOICES,
    CURRENT_WORKFLOW_DEFAULT,
    DISPOSE_AUTOMATICALLY_CHOICES,
    DISPOSE_AUTOMATICALLY_NO,
    ProblemColumn,
    ProblemTable,
    SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
    SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
)
from .serializers import ProblemColumnSerializer, ProblemSampleSerializer


class DateTodayColumnTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Date Today test', is_default=True)
        ProblemColumn.objects.create(
            table=self.table,
            name='Current Workflow',
            field_key=SYSTEM_CURRENT_WORKFLOW_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE,
            required=True,
            choices=list(CURRENT_WORKFLOW_CHOICES),
            default_value=CURRENT_WORKFLOW_DEFAULT,
            is_system=True,
            position=0,
        )
        ProblemColumn.objects.create(
            table=self.table,
            name='Dispose Automatically',
            field_key=SYSTEM_DISPOSE_AUTOMATICALLY_FIELD_KEY,
            column_type=ProblemColumn.TYPE_CHOICE,
            required=True,
            choices=list(DISPOSE_AUTOMATICALLY_CHOICES),
            default_value=DISPOSE_AUTOMATICALLY_NO,
            is_system=True,
            position=1,
        )
        self.column = ProblemColumn.objects.create(
            table=self.table,
            name='Received Date',
            field_key='received-date',
            column_type=ProblemColumn.TYPE_DATE_TODAY,
            required=False,
            position=2,
        )

    def _serializer(self, custom_values):
        request = SimpleNamespace(user=SimpleNamespace(is_authenticated=False))
        return ProblemSampleSerializer(
            data={'table': str(self.table.pk), 'custom_values': custom_values},
            context={'request': request},
        )

    def test_missing_date_today_value_defaults_to_server_local_date(self):
        serializer = self._serializer({})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data['custom_values']['received-date'],
            timezone.localdate().isoformat(),
        )

    def test_explicit_date_today_value_is_preserved(self):
        serializer = self._serializer({'received-date': '2026-09-25'})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['custom_values']['received-date'], '2026-09-25')

    def test_date_today_rejects_invalid_dates(self):
        serializer = self._serializer({'received-date': 'not-a-date'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('received-date', serializer.errors['custom_values'])

    def test_column_definition_never_persists_a_static_default(self):
        serializer = ProblemColumnSerializer(
            data={
                'table': str(self.table.pk),
                'name': 'Created Day',
                'column_type': ProblemColumn.TYPE_DATE_TODAY,
                'default_value': '2020-01-01',
                'required': False,
                'searchable': True,
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data['default_value'])
