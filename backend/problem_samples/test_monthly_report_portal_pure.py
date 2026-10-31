"""Dependency-free tests for Excel reports and bearer-link email content."""
import ast
import io
import json
import re
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

SOURCE=Path(__file__).with_name('monthly_report_portal.py')
names={'_safe_text','_excel_value','render_excel','report_url','make_report_email_body','reportable_column'}
functions=[n for n in ast.parse(SOURCE.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in names]
namespace={'io':io,'json':json,'re':re,'timedelta':timedelta,
           'settings': SimpleNamespace(FRONTEND_URL='https://tracker.example.test'),
           'timezone':SimpleNamespace(localtime=lambda x:x)}
exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),str(SOURCE),'exec'),namespace)

class ReportExcelPureTests(unittest.TestCase):
    def example(self):
        return {'lab':'Edmonton','table':'ALS Tickets','rule_pattern':'Northstar',
                'period_start':'2026-10-01','period_end':'2026-10-31','total':2,
                'workflow_counts':{'Follow Up Required':1,'Disposed':1},
                'columns':[{'id':'id1','label':'Batch'},{'id':'id2','label':'Customer details'}],
                'tickets':[{'number':123,'status':'Follow Up Required','created_at':'2026-10-29',
                            'matched_sources':['Ticket Brand'],'details':[
                              {'id':'id1','label':'Batch','value':'=HYPERLINK("x")'},
                              {'id':'id2','label':'Customer details','value':'Information'}]},
                           {'number':124,'status':'Disposed','created_at':'2026-10-30',
                            'matched_sources':['Company Brand'],'details':[]}]}

    def test_link_stays_compatible_with_existing_emails(self):
        mail=SimpleNamespace(public_token='c91167cd-8888-4555-b0ca-3b0b506c1612')
        self.assertEqual(namespace['report_url'](mail), 'https://tracker.example.test/reports/monthly/c91167cd-8888-4555-b0ca-3b0b506c1612')

    def test_email_contains_download_link_not_ticket_details(self):
        mail=SimpleNamespace(public_token='c91167cd-8888-4555-b0ca-3b0b506c1612',
            generation_mode='scheduled',lab=SimpleNamespace(name='Edmonton'),
            period_start=date(2026,10,1),period_end=date(2026,11,1),matched_ticket_count=2,
            public_expires_at=datetime(2027,1,29,tzinfo=timezone.utc))
        body=namespace['make_report_email_body'](mail)
        self.assertIn('Download Excel monthly report',body)
        self.assertIn('90 days',body)
        self.assertIn('two worksheet tabs: Summary and Tickets', body)
        self.assertIn('To view the ticket rows, open the Tickets tab', body)
        self.assertNotIn('Ticket #',body)

    def test_redacts_tracking_urls_inside_text(self):
        scrub=namespace['_safe_text']
        self.assertNotIn('/track/abc123',scrub('Customer: https://test.example/track/abc123'))
        self.assertIn('[tracking link redacted]',scrub('Customer: https://test.example/track/abc123'))
        self.assertNotIn('SECRETTOKEN',scrub('tracking_token: SECRETTOKEN'))

    def test_excel_workbook_has_summary_ticket_headers_and_selected_columns(self):
        from openpyxl import load_workbook
        data=namespace['render_excel'](self.example())
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(data)))
        book=load_workbook(io.BytesIO(data),read_only=True,data_only=False)
        self.assertEqual(book.sheetnames,['Summary','Tickets'])
        tickets=list(book['Tickets'].iter_rows(values_only=True))
        self.assertEqual(tickets[1],('Ticket #','Current Workflow','Batch','Customer details'))
        self.assertEqual(tickets[2][0],123)
        self.assertEqual(tickets[3][1],'Disposed')
        self.assertEqual(tickets[2][2], "\'=HYPERLINK(\"x\")")
        self.assertNotIn('Tracking Token', tickets[1])
        self.assertNotIn('Created', tickets[1])
        self.assertNotIn('Brand Matched Via', tickets[1])

    def test_excel_dangerous_text_is_not_formula(self):
        from openpyxl import load_workbook
        data=namespace['render_excel'](self.example())
        workbook=load_workbook(io.BytesIO(data),read_only=True,data_only=False)
        self.assertEqual(workbook['Tickets']['C3'].data_type,'s')
        for value in ('=1+1','+SUM(A1)','-SUM(A1)','@cmd'):
            self.assertEqual(namespace['_excel_value'](value),"'"+value)

    def test_private_column_filter_denies_tokens_and_client_emails(self):
        accept=namespace['reportable_column']
        col=lambda name,key,col_type='text':SimpleNamespace(name=name,field_key=key,column_type=col_type)
        self.assertFalse(accept(col('Tracking Link','system-tracking-link')))
        self.assertFalse(accept(col('Client Email','client-email','client_email')))
        self.assertFalse(accept(col('Courier Account','courier-account')))
        self.assertTrue(accept(col('Batch ID','batch-id')))

    def test_legacy_snapshots_still_produce_xlsx(self):
        from openpyxl import load_workbook
        legacy=self.example()
        legacy.pop('columns')
        legacy['tickets'][0]['details']=[{'label':'Batch','value':'Old record'}]
        legacy['tickets'][1]['details']=[]
        workbook=load_workbook(io.BytesIO(namespace['render_excel'](legacy)),read_only=True)
        self.assertEqual(workbook['Tickets']['C2'].value,'Batch')
        self.assertEqual(workbook['Tickets']['C3'].value,'Old record')

if __name__=='__main__': unittest.main()
