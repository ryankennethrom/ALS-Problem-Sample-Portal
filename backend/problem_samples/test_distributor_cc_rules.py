"""Brand CC rules: validation, company Brand lookup, and union of matching sources."""
from django.test import TestCase
from customers.models import Customer
from .models import ProblemColumn, ProblemSample, ProblemTable
from .serializers import ProblemColumnSerializer
from .views import _brand_auto_cc


class BrandEmailRulesTests(TestCase):
    def setUp(self):
        self.table = ProblemTable.objects.create(name='Brand rules')
        self.distributor = ProblemColumn.objects.create(table=self.table, name='Distributor', field_key='distributor', column_type='distributor')
        self.end_user = ProblemColumn.objects.create(table=self.table, name='End User', field_key='end-user', column_type='end_user')
        self.brand = ProblemColumn.objects.create(table=self.table, name='Brand', field_key='brand', column_type='brand')
        Customer.objects.create(company_name='Acme Supply', customer_type='Distributor', brand='Northstar')
        Customer.objects.create(company_name='Acme Supply', customer_type='End User', brand='Wrong Type')
        Customer.objects.create(company_name='Final Customer', customer_type='End User', brand='Northstar PLUS')

    def save_rules(self, rules, dependencies=None):
        serializer = ProblemColumnSerializer(self.brand, data={
            'company_brand_dependencies': dependencies if dependencies is not None else [str(self.distributor.pk), str(self.end_user.pk)],
            'brand_cc_rules': rules,
        }, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        self.brand.refresh_from_db()

    def test_ticket_or_company_brand_matches_and_cc_is_deduplicated(self):
        rules = [
            {'match_type':'contains', 'pattern':'northstar', 'sources':['ticket', str(self.distributor.pk), str(self.end_user.pk)], 'cc_emails':['alpha@example.com', 'Beta@example.com']},
            {'match_type':'exact', 'pattern':'northstar', 'sources':[str(self.distributor.pk)], 'cc_emails':['ALPHA@example.com', 'third@example.com']},
        ]
        self.save_rules(rules)
        row = ProblemSample.objects.create(table=self.table, problem_number=101, custom_values={
            'brand':'Other', 'distributor':'Acme Supply', 'end-user':'Final Customer'})
        self.assertEqual(_brand_auto_cc(row), ['alpha@example.com', 'Beta@example.com', 'third@example.com'])

    def test_ticket_brand_alone_matches_without_company(self):
        self.save_rules([{'match_type':'contains','pattern':'north','sources':['ticket'],'cc_emails':['cc@example.com']}], [])
        row = ProblemSample.objects.create(table=self.table, problem_number=102, custom_values={'brand':'NORTHSTAR'})
        self.assertEqual(_brand_auto_cc(row), ['cc@example.com'])

    def test_unknown_company_does_not_invent_a_brand(self):
        self.save_rules([{'match_type':'contains','pattern':'north','sources':[str(self.distributor.pk)],'cc_emails':['cc@example.com']}])
        row = ProblemSample.objects.create(table=self.table, problem_number=103, custom_values={'distributor':'Not imported'})
        self.assertEqual(_brand_auto_cc(row), [])

    def test_invalid_company_sources_and_email_rejected(self):
        for bad_rule in [
            {'match_type':'contains','pattern':'north','sources':['bad-id'],'cc_emails':['cc@example.com']},
            {'match_type':'contains','pattern':'north','sources':[],'cc_emails':['cc@example.com']},
            {'match_type':'contains','pattern':'north','sources':['ticket'],'cc_emails':['bad email']},
        ]:
            with self.subTest(rule=bad_rule):
                serializer = ProblemColumnSerializer(self.brand, data={'brand_cc_rules':[bad_rule]}, partial=True)
                self.assertFalse(serializer.is_valid())
                self.assertIn('brand_cc_rules', serializer.errors)

    def test_migrated_pending_rule_is_inactive(self):
        self.brand.brand_cc_rules = [{'pending_brand_review':True,'match_type':'contains','pattern':'northstar',
            'sources':['ticket'],'cc_emails':['cc@example.com'],'send_monthly_reports':True}]
        self.brand.save(update_fields=['brand_cc_rules'])
        row = ProblemSample.objects.create(table=self.table, problem_number=104, custom_values={'brand':'northstar'})
        self.assertEqual(_brand_auto_cc(row), [])

    def test_monthly_excel_column_selection_saved_and_private_fields_rejected(self):
        batch = ProblemColumn.objects.create(table=self.table, name='Batch ID', field_key='batch-id', column_type='text')
        forbidden = ProblemColumn.objects.create(table=self.table, name='Client Email', field_key='client-email', column_type='client_email')
        rule = {'match_type':'contains', 'pattern':'north','sources':['ticket'],
                'cc_emails':['cc@example.com'], 'send_monthly_reports':True,
                'report_column_ids':[str(batch.pk)]}
        self.save_rules([rule],[])
        self.assertEqual(self.brand.brand_cc_rules[0]['report_column_ids'],[str(batch.pk)])
        rule['report_column_ids']=[str(forbidden.pk)]
        serializer=ProblemColumnSerializer(self.brand,data={'brand_cc_rules':[rule]},partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('brand_cc_rules',serializer.errors)
