from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounts.models import UserProfile
from .models import ProblemColumn, ProblemTable
from .views import ensure_builtin_columns


class ProblemColumnReorderTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='reorder.admin', password='pw', email='reorder.admin@alsglobal.com')
        UserProfile.objects.update_or_create(user=self.admin, defaults={'is_admin': True})
        self.client.force_authenticate(self.admin)
        self.table = ProblemTable.objects.create(name='Reorder Test', created_by=self.admin)
        ensure_builtin_columns(self.table)
        self.custom = ProblemColumn.objects.create(
            table=self.table, name='Customer Ref', field_key='customer-ref', column_type=ProblemColumn.TYPE_TEXT,
            position=99,
        )

    def test_admin_can_reorder_all_columns(self):
        ids = [str(value) for value in self.table.columns.values_list('id', flat=True)]
        ids.reverse()
        response = self.client.post(
            f'/api/problem-tables/{self.table.id}/reorder-columns/',
            {'column_ids': ids},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        saved = [str(value) for value in self.table.columns.order_by('position', 'created_at').values_list('id', flat=True)]
        self.assertEqual(saved, ids)
        self.assertEqual([column['id'] for column in response.data['columns']], ids)

    def test_reorder_requires_every_column_exactly_once(self):
        ids = [str(value) for value in self.table.columns.values_list('id', flat=True)]
        response = self.client.post(
            f'/api/problem-tables/{self.table.id}/reorder-columns/',
            {'column_ids': ids[:-1]},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

        duplicate = ids[:-1] + [ids[0]]
        response = self.client.post(
            f'/api/problem-tables/{self.table.id}/reorder-columns/',
            {'column_ids': duplicate},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
