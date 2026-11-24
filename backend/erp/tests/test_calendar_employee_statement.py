from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from erp.tests.test_api import environment,client_for
from erp.models import Employee,Location,Business,UserPreference
from erp.core import Context,execute
from erp.localization import calendar_month

def test_jalali_month_grid_afghan_names_and_leap_dates(environment):
 user,business,*_=environment;client=client_for(user,business)
 grid=client.get('/api/calendar/',{'view':'month','year':1405,'month':8}).json()
 assert grid['month_name']=='عقرب' and len(grid['days'])==42
 selected=next(day for day in grid['days'] if day['jalali']=='1405-08-08')
 assert selected['gregorian']=='2026-10-30'
 assert date.fromisoformat(grid['days'][0]['gregorian']).weekday()==5
 assert calendar_month(1399,12)['last']=='2021-03-20'
 assert calendar_month(1400,12)['last']=='2022-03-20'
 assert calendar_month(1405,1)['first']=='2026-03-21'
 assert client.get('/api/calendar/',{'view':'month','year':1405,'month':13}).status_code==400
 assert client.get('/api/calendar/',{'view':'month','year':9999,'month':1}).status_code==400

def test_jalali_is_new_user_default_and_explicit_gregorian_persists(environment):
 user,business,*_=environment;client=client_for(user,business)
 assert client.get('/api/preferences/').json()['calendar']=='jalali'
 assert UserPreference.objects.get(user=user).calendar=='jalali'
 assert client.patch('/api/preferences/',{'calendar':'gregorian'},content_type='application/json').status_code==200
 assert client.get('/api/preferences/').json()['calendar']=='gregorian'

def test_employee_statement_distinguishes_cash_recovery_and_opening_balances(environment):
 user,business,member,loc,warehouse,product=environment;ctx=Context(user,business);client=client_for(user,business)
 employee=Employee.objects.create(business=business,location=loc,name='Statement employee',code='EMP-STMT',kind='monthly',rate=25000,advance_limit=50000)
 def post(kind,when,**payload):return execute(ctx,kind,{'date':when,**payload},str(uuid4()))
 post('employee_advance','2026-06-05',employee=employee.id,amount='8000')
 salary=post('payroll_accrue','2026-06-30',employee=employee.id,period='2026-06',deductions=[{'account':'TAX','amount':'1000'}])
 post('payroll_settle','2026-07-01',payroll=salary.id,amount='15000',advance_recovery='5000')
 data=client.get('/api/reports/employee_statement/',{'employee':employee.id,'to':'2026-07-31'}).json()
 expected={'salary_earned':25000,'salary_paid':15000,'advances_paid':8000,'advance_outstanding':3000,'salary_payable':4000,'advance_recovered':5000,'deductions':1000}
 for key,value in expected.items():assert Decimal(data['totals'][key])==value,(key,data['totals'])
 assert [Decimal(row['balance']) for row in data['rows']]==[24000,4000]
 july=client.get('/api/reports/employee_statement/',{'employee':employee.id,'from':'2026-07-01','to':'2026-07-31'}).json()
 assert Decimal(july['totals']['opening'])==24000 and Decimal(july['totals']['closing'])==4000
 advances=client.get('/api/reports/employee_statement/',{'employee':employee.id,'account':'ADVANCES','from':'2026-07-01','to':'2026-07-31'}).json()
 assert Decimal(advances['totals']['opening'])==8000 and Decimal(advances['rows'][0]['balance'])==3000
 june=client.get('/api/reports/employee_statement/',{'employee':employee.id,'to':'2026-06-30'}).json()
 assert Decimal(june['totals']['salary_payable'])==24000 and Decimal(june['totals']['salary_paid'])==0
 assert 'bank_account' not in data['employee'] and 'national_id' not in data['employee']

def test_employee_statement_pagination_export_and_business_scope(environment):
 user,business,member,loc,*_=environment;ctx=Context(user,business);client=client_for(user,business)
 employee=Employee.objects.create(business=business,location=loc,name='Paged employee',kind='daily',rate=100,advance_limit=1000)
 for day in range(1,4):execute(ctx,'employee_advance',{'date':f'2026-06-0{day}','employee':employee.id,'amount':'100'},str(uuid4()))
 query={'employee':employee.id,'account':'ADVANCES','to':'2026-06-30','limit':1,'offset':1}
 page=client.get('/api/reports/employee_statement/',query).json()
 assert page['count']==3 and len(page['rows'])==1 and Decimal(page['rows'][0]['balance'])==200
 exported=client.get('/api/export/employee_statement/',query)
 assert exported.status_code==200 and exported.content.decode().count('EMPLOYEE_ADVANCE')==3
 other=Business.objects.create(name='Private business',slug='private-employee-stmt');other_loc=Location.objects.create(business=other,name='Private',code='P')
 private=Employee.objects.create(business=other,location=other_loc,name='Private',kind='daily',rate=100)
 assert client.get('/api/reports/employee_statement/',{'employee':private.id}).status_code==400
 member.all_locations=False;member.location_ids=[];member.save()
 assert client.get('/api/reports/employee_statement/',{'employee':employee.id}).status_code==403
 member.permissions=['sales.view'];member.save()
 assert client.get('/api/reports/employee_statement/',{'employee':employee.id}).status_code==403
