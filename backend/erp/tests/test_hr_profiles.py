from decimal import Decimal
from django.db import DatabaseError,transaction
from erp.models import Business,Department,Position,Employee,Membership,Document
from erp.core import Context,execute
from erp.tests.test_api import environment,client_for

def test_employee_profile_organisation_permissions_and_isolation(environment):
 user,business,membership,location,warehouse,product=environment
 client=client_for(user,business)
 department=client.post('/api/catalog/departments/',{'name':'Production team','location':location.id},content_type='application/json')
 assert department.status_code==201
 position=client.post('/api/catalog/positions/',{'name':'Foam operator','department':department.json()['id']},content_type='application/json')
 assert position.status_code==201
 payload={'code':'EMP-W-001','name':'Synthetic weekly employee','father_name':'Test father','phone':'0700000001','email':'test@example.test','national_id':'SYNTHETIC-ONLY','address':'Herat test','emergency_name':'Test contact','emergency_phone':'0700000002','department':department.json()['id'],'position':position.json()['id'],'location':location.id,'join_date':'2026-04-01','kind':'weekly','week_start':5,'rate':'7000','effective_date':'2026-04-01','advance_limit':'8000','bank_name':'Test bank','bank_account':'TEST-ONLY','payment_method':'bank'}
 response=client.post('/api/catalog/employees/',payload,content_type='application/json');assert response.status_code==201,response.json()
 employee=Employee.objects.get(pk=response.json()['id']);assert employee.phone=='0700000001' and employee.department_id==department.json()['id']
 assert client.post('/api/catalog/employees/',payload,content_type='application/json').status_code==400
 foreign=Business.objects.create(name='Other',slug='other-profile');alien=Department.objects.create(business=foreign,name='Private')
 assert client.patch(f'/api/catalog/employees/{employee.id}/',{'department':alien.id},content_type='application/json').status_code==400
 with __import__('pytest').raises(DatabaseError),transaction.atomic():
  Employee.objects.filter(pk=employee.id).update(department=alien)
 # Only authorized payroll readers see personally identifying employee data.
 membership.permissions=['sales.view'];membership.save()
 data=client.get('/api/catalog/').json();assert data['employees']==[] and data['departments']==[] and data['positions']==[]
 assert client.post('/api/catalog/employees/',payload,content_type='application/json').status_code==403
 membership.permissions=['*'];membership.save()
 pay=execute(Context(user,business),'payroll_accrue',{'employee':employee.id,'week_start_date':'2026-04-25','date':'2026-05-01'},'weekly-profile-pay')
 assert pay.amount==Decimal('7000')
 printable=client.get(f'/api/documents/{pay.id}/print/');assert printable.status_code==200
 assert b'1405-02-05' in printable.content and b'1405-02-11' in printable.content and b'Weekly' in printable.content
 assert client.patch('/api/preferences/',{'calendar':'gregorian'},content_type='application/json').status_code==200
 printable=client.get(f'/api/documents/{pay.id}/print/')
 assert b'2026-04-25' in printable.content and b'2026-05-01' in printable.content
 assert client.patch(f'/api/catalog/employees/{employee.id}/',{'kind':'monthly'},content_type='application/json').status_code==400
 assert client.patch(f'/api/catalog/employees/{employee.id}/',{'phone':'0700000003'},content_type='application/json').status_code==200
 assert client.patch(f'/api/catalog/employees/{employee.id}/',{'rate':'8000','effective_date':'2026-04-28'},content_type='application/json').status_code==400
 assert client.patch(f'/api/catalog/employees/{employee.id}/',{'rate':'8000','effective_date':'2026-05-02'},content_type='application/json').status_code==200
 assert Document.objects.get(pk=pay.id).result['rate_used']=='7000'
 assert client.patch(f'/api/catalog/employees/{employee.id}/',{'name':'Renamed staff'},content_type='application/json').status_code==200
 printed=client.get(f'/api/documents/{pay.id}/print/');assert printed.status_code==200 and b'Synthetic weekly employee' in printed.content and b'Renamed staff' not in printed.content

def test_employee_position_must_match_department_and_account_group_validation(environment):
 user,business,member,location,*_=environment;client=client_for(user,business)
 one=Department.objects.create(business=business,name='One');two=Department.objects.create(business=business,name='Two')
 position=Position.objects.create(business=business,name='Operator',department=one)
 response=client.post('/api/catalog/employees/',{'name':'Invalid assignment','location':location.id,'kind':'weekly','department':two.id,'position':position.id},content_type='application/json')
 assert response.status_code==400
 response=client.post('/api/catalog/accounts/',{'code':'CUSTOM','name':'Wrong group','category':'asset','statement_group':'revenue'},content_type='application/json')
 assert response.status_code==400

def test_comparative_export_uses_real_period_values_and_requires_export_permission(environment):
 import csv,io
 user,business,membership,location,*_=environment;ctx=Context(user,business);client=client_for(user,business)
 execute(ctx,'opening_cash',{'location':location.id,'date':'2026-04-01','account':'CASH','amount':'1000','reason':'Synthetic reviewed opening'},'export-opening')
 expense=execute(ctx,'expense_post',{'location':location.id,'date':'2026-04-30','amount':'600','cash_account':'CASH','expense_account':'RENT'},'export-rent')
 assert client.get(f'/api/documents/{expense.id}/print/').status_code==200
 path='/api/export/profit_loss/?from=2026-04-01&to=2026-04-30&compare_from=2026-03-01&compare_to=2026-03-31'
 response=client.get(path);assert response.status_code==200
 rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))));assert 'Comparative amount' in rows[0][-1]
 rent=next(row for row in rows[1:] if row[0]=='RENT');assert rent[-1]=='0' and Decimal(rent[-2])==Decimal('600')
 membership.permissions=['accounting.view'];membership.save();assert client.get(path).status_code==403
 membership.all_locations=False;membership.location_ids=[location.id];membership.save()
 assert client.get('/api/reports/changes_equity/').status_code==403
