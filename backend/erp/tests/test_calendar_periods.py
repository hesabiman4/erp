"""PostgreSQL acceptance for prospective calendars, payroll and actual ledgers."""
from datetime import date
from decimal import Decimal
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from erp.core import Context, execute
from erp.models import Business, Document, Employee, Entry, StockMovement, Party, Account
from erp.tests.test_api import environment, client_for
from erp.calendar_periods import month_bounds, period_data, workspace
from erp.reports import report
from erp.growth_api import budgets_actual


def change(ctx, monkeypatch, calendar='jalali', effective='2026-03-21', key='calendar-switch'):
    monkeypatch.setattr('erp.calendar_periods.timezone.localdate', lambda: date(2026,3,1))
    return execute(ctx,'calendar_policy',{'date':'2026-03-01','calendar':calendar,'effective_from':effective,
                   'reason':'Reviewed contractual calendar transition'},key)


def employee(business, location, kind='monthly', rate='31000', **kwargs):
    return Employee.objects.create(business=business,location=location,name='Calendar acceptance employee',
                                   kind=kind,rate=rate,join_date='2026-01-01',**kwargs)


def test_jalali_real_month_boundaries_and_leap_validation():
    assert month_bounds('1405-01','jalali')==(date(2026,3,21),date(2026,4,20))
    assert period_data('۱۴۰۳-۱۲','jalali')['days']==30
    assert period_data('1404-12','jalali')['days']==29
    assert period_data('1405-07','jalali')['days']==30
    assert period_data('2024-02','gregorian')['days']==29
    for value,calendar in [('2026-13','gregorian'),('1405-00','jalali'),('2026-01','jalali'),('1405-01','gregorian'),('1405/01','jalali'),('1405-01','display')]:
        with pytest.raises(ValidationError):month_bounds(value,calendar)


def test_calendar_policy_prospective_append_only_scoped_and_nonfinancial(environment,monkeypatch):
    user,business,member,loc,*_=environment;ctx=Context(user,business);client=client_for(user,business)
    original_entries=Entry.objects.count();doc=change(ctx,monkeypatch)
    assert doc.result['calendar']=='jalali' and doc.result['financial_posting'] is False
    assert Entry.objects.count()==original_entries and not StockMovement.objects.filter(document=doc).exists()
    assert execute(ctx,'calendar_policy',doc.data,'calendar-switch').id==doc.id
    assert workspace(ctx,{'for_date':'2026-03-20'})['active_calendar']=='gregorian'
    assert workspace(ctx,{'for_date':'2026-03-21'})['active_calendar']=='jalali'
    with pytest.raises(ValidationError):change(ctx,monkeypatch,effective='2026-03-22',key='nonfirst')
    with pytest.raises(ValidationError):change(ctx,monkeypatch,calendar='gregorian',effective='2026-03-01',key='past-policy')
    business.refresh_from_db()
    assert client.patch('/api/business/',{'settings':{}},content_type='application/json').status_code==400
    assert client.patch('/api/business/',{'settings':{**business.settings,'name_note':'allowed'}},content_type='application/json').status_code==200
    member.permissions=['settings.manage'];member.save()
    with pytest.raises(PermissionDenied):change(Context(user,business),monkeypatch,calendar='gregorian',effective='2026-05-01',key='no-accounting')
    member.permissions=['*'];member.all_locations=False;member.location_ids=[loc.id];member.save()
    with pytest.raises(PermissionDenied):change(Context(user,business),monkeypatch,calendar='gregorian',effective='2026-05-01',key='partial-business')


def test_jalali_payroll_transition_prorates_old_month_preserves_history(environment,monkeypatch):
    user,business,member,loc,*_=environment;ctx=Context(user,business);staff=employee(business,loc)
    historical=execute(ctx,'payroll_accrue',{'date':'2026-02-28','employee':staff.id,'period':'2026-02'},'calendar-old-pay')
    original=dict(historical.result)
    change(ctx,monkeypatch)
    short=execute(ctx,'payroll_accrue',{'date':'2026-03-20','employee':staff.id,'period':'2026-03'},'calendar-transition-pay')
    assert short.amount==Decimal('20000')
    assert short.result['earning_from']=='2026-03-01' and short.result['earning_through']=='2026-03-20'
    assert short.result['denominator_days']==31
    pay=execute(ctx,'payroll_accrue',{'date':'2026-04-20','employee':staff.id,'period':'1405-01','period_calendar':'jalali'},'calendar-jalali-pay')
    assert pay.amount==Decimal('31000') and pay.result['period_key']=='jalali:1405-01'
    assert pay.data['period']=='2026-03' and pay.data['calendar_period']=='1405-01'
    assert pay.result['earning_from']=='2026-03-21' and pay.result['earning_through']=='2026-04-20'
    assert sum((entry.debit-entry.credit for entry in pay.entries.all()),Decimal(0))==0
    historical.refresh_from_db();assert historical.result==original
    with pytest.raises(ValidationError):execute(ctx,'payroll_accrue',{'date':'2026-04-21','employee':staff.id,'period':'1405-01','period_calendar':'jalali'},'calendar-duplicate')
    with pytest.raises(ValidationError):execute(ctx,'payroll_accrue',{'date':'2026-04-30','employee':staff.id,'period':'2026-04'},'calendar-wrong-basis')


def test_calendar_change_rejects_already_earned_overlaps_and_historical_change(environment,monkeypatch):
    user,business,member,loc,*_=environment;ctx=Context(user,business);staff=employee(business,loc)
    execute(ctx,'payroll_accrue',{'date':'2026-03-31','employee':staff.id,'period':'2026-03'},'calendar-already-paid-month')
    with pytest.raises(ValidationError):change(ctx,monkeypatch)
    business.refresh_from_db();assert business.settings.get('calendar_policies',[])==[]
    with pytest.raises(ValidationError):change(ctx,monkeypatch,effective='2026-02-20',key='historic-month')


def test_jalali_daily_attendance_and_hourly_earning_windows(environment,monkeypatch):
    user,business,member,loc,*_=environment;ctx=Context(user,business);staff=employee(business,loc,kind='hourly',rate='100')
    change(ctx,monkeypatch)
    execute(ctx,'attendance_record',{'date':'2026-03-25','employee':staff.id,'hours':'2','days':'1'},'calendar-hours-first')
    first=execute(ctx,'payroll_accrue',{'date':'2026-03-25','employee':staff.id,'period':'1405-01','period_calendar':'jalali'},'calendar-hour-pay-first')
    assert first.amount==Decimal('200') and first.data['earning_from']=='2026-03-21'
    with pytest.raises(ValidationError):execute(ctx,'payroll_accrue',{'date':'2026-03-25','employee':staff.id,'period':'1405-01','period_calendar':'jalali'},'calendar-hour-pay-duplicate')
    with pytest.raises(ValidationError):execute(ctx,'attendance_record',{'date':'2026-03-24','employee':staff.id,'hours':'1'},'calendar-hours-in-closed-window')
    execute(ctx,'attendance_record',{'date':'2026-03-26','employee':staff.id,'hours':'3','days':'1'},'calendar-hours-second')
    second=execute(ctx,'payroll_accrue',{'date':'2026-03-26','employee':staff.id,'period':'1405-01','period_calendar':'jalali'},'calendar-hour-pay-second')
    assert second.amount==Decimal('300') and second.data['earning_from']=='2026-03-26'


def test_jalali_employment_proration_and_weekly_dates_remain_explicit(environment,monkeypatch):
    user,business,member,loc,*_=environment;ctx=Context(user,business);staff=employee(business,loc)
    staff.join_date='2026-03-31';staff.save();change(ctx,monkeypatch)
    pay=execute(ctx,'payroll_accrue',{'date':'2026-04-20','employee':staff.id,'period':'1405-01','period_calendar':'jalali'},'calendar-prorated')
    assert pay.amount==Decimal('21000') and pay.result['denominator_days']==31
    weekly=employee(business,loc,kind='weekly',rate='7000')
    week=execute(ctx,'payroll_accrue',{'date':'2026-03-27','employee':weekly.id,'week_start_date':'2026-03-21'},'calendar-week-remains')
    assert week.amount==Decimal('7000') and week.result['earning_through']=='2026-03-27'
    with pytest.raises(ValidationError):execute(ctx,'payroll_accrue',{'date':'2026-04-19','employee':staff.id,'period':'1405-01','period_calendar':'jalali'},'calendar-too-early')


def test_jalali_reports_and_budgets_use_real_ledger_dates(environment,monkeypatch):
    user,business,member,loc,*_=environment;ctx=Context(user,business);supplier=Party.objects.create(business=business,name='Calendar supplier',kind='supplier')
    for day,amount,key in [('2026-03-20','10','before'),('2026-03-21','100','first'),('2026-04-20','200','last'),('2026-04-21','20','after')]:
        execute(ctx,'expense_post',{'date':day,'location':loc.id,'supplier':supplier.id,'expense_account':'RENT','amount':amount},'calendar-rent-'+key)
    pnl=report(ctx,'profit_loss',{'calendar_period':'1405-01','period_calendar':'jalali'})
    assert Decimal(pnl['totals']['profit'])==Decimal('-300')
    assert pnl['as_of']=='2026-04-20' and pnl['date_from']=='2026-03-21'
    with pytest.raises(ValidationError):report(ctx,'profit_loss',{'calendar_period':'1405-01','period_calendar':'jalali','from':'2026-04-01'})
    rent=Account.objects.get(business=business,code='RENT')
    execute(ctx,'budget_set',{'date':'2026-03-01','period':'1405-01','period_calendar':'jalali','account':rent.id,'location':loc.id,'line':'shared','amount':'500'},'calendar-budget-jalali')
    execute(ctx,'budget_set',{'date':'2026-03-01','period':'2026-03','account':rent.id,'location':loc.id,'line':'shared','amount':'1000'},'calendar-budget-gregorian')
    actual=budgets_actual(ctx,{'period':'1405-01','period_calendar':'jalali'})
    assert actual['rows'][0]['budget']=='500.00' and Decimal(actual['rows'][0]['actual'])==300
    assert actual['first']=='2026-03-21'
    old=budgets_actual(ctx,{'period':'2026-03'})
    assert old['rows'][0]['budget']=='1000.00' and Decimal(old['rows'][0]['actual'])==110


def test_calendar_boundary_and_workspace_api_business_permissions(environment):
    user,business,member,*_=environment;client=client_for(user,business)
    result=client.get('/api/calendar/?view=period&calendar=jalali&value=1405-01')
    assert result.status_code==200 and result.json()['first']=='2026-03-21'
    assert client.get('/api/business-periods/?for_date=2026-03-01').json()['active_calendar']=='gregorian'
    other=Business.objects.create(name='Isolated calendar business',slug='calendar-other')
    assert client.get('/api/business-periods/',HTTP_X_BUSINESS_ID=str(other.id)).status_code==403
    member.permissions=['sales.view'];member.save()
    assert client.get('/api/business-periods/').status_code==403
    member.permissions=['payroll.post'];member.save()
    assert client.get('/api/business-periods/').status_code==200
