"""Actual PostgreSQL revisions, review history, isolation and exact bracket math."""
from io import StringIO
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from django.conf import settings
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.management import call_command
from django.db import DatabaseError,close_old_connections,transaction
from django.utils import timezone
from erp.core import Context
from erp.models import AuditEvent,Business,Document,Entry,Membership,StockMovement,TaxRule
from erp.tax_models import TaxSchedule,TaxScheduleChange
from erp.taxation import change,calculate,select_schedule
from erp.tests.test_api import environment,client_for


def research():
    return json.loads((settings.ROOT_DIR/'backend/erp/data/afghan_tax_research_20261122.json').read_text(encoding='utf-8'))


def create(ctx,index=1,**updates):
    rule={**research()[index],**updates}
    return change(ctx,'create',{'rule':rule,'reason':'Reviewed synthetic tax research record.'},'create-'+rule['schedule_version'])


def confirm(ctx,rule,key='confirm-rule',**updates):
    return change(ctx,'confirm',{'reason':'Reviewed test applicability and official source.',
        'expected_revision':rule['confirmation_revision'],**updates},key,rule['id'])


def unchanged():
    return Document.objects.count(),Entry.objects.count(),StockMovement.objects.count(),TaxRule.objects.count()


def test_revision_history_retry_stale_decision_and_nonposting(environment):
    user,biz,*_=environment;ctx=Context(user,biz);before=unchanged()
    draft=create(ctx);rule=TaxSchedule.objects.get(pk=draft['id'])
    assert rule.requires_confirmation and rule.verified_at is None and rule.confirmation_revision==0
    assert create(ctx)==draft and TaxSchedule.objects.count()==1
    with pytest.raises(ValidationError):create(ctx,name_fa='Different request with reused key')
    reviewed=confirm(ctx,draft)
    assert not reviewed['requires_confirmation'] and reviewed['verified_at'] and reviewed['confirmation_revision']==1
    assert confirm(ctx,draft)==reviewed # Same authorized idempotent request, including stale expected revision.
    with pytest.raises(ValidationError,match='changed'):confirm(ctx,draft,key='stale-confirmation')
    revoked=change(ctx,'revoke',{'expected_revision':1,'reason':'Applicability evidence needs another review.'},'revoke-rule',rule.pk)
    assert revoked['requires_confirmation'] and revoked['verified_at'] is None and revoked['confirmation_revision']==2
    later=create(ctx,schedule_version='AF-REVISED',supersedes=rule.pk,name_fa='نسخهٔ اصلاحی آزمایشی')
    rule.refresh_from_db();assert rule.name_fa==draft['name_fa'] and rule.brackets==draft['brackets']
    assert later['supersedes']==rule.pk and later['requires_confirmation']
    events=list(rule.changes.order_by('pk'));assert [e.operation for e in events]==['create','confirm','revoke']
    assert events[1].before==draft and events[1].after==reviewed
    assert AuditEvent.objects.filter(business=biz,action__startswith='tax.schedule.').count()==4
    assert unchanged()==before


@pytest.mark.parametrize('index,amount,expected',[
    (0,'0','0.00'),(0,'5000','0.00'),(0,'5000.50','0.01'),(0,'12500','150.00'),
    (0,'12500.10','150.01'),(0,'100000','8900.00'),(0,'100000.05','8900.01'),(0,'200000','28900.00'),
    (1,'0','0.00'),(1,'10000','0.00'),(1,'10000.05','0.01'),(1,'100000','9000.00'),
    (1,'100000.10','9000.02'),(1,'200000','24000.00'),(1,'۲۰٬۰۰۰','1000.00'),
    (2,'120000','12000.00'),(3,'120000','24000.00'),(4,'100000','2000.00'),
])
def test_salary_old_new_and_flat_research_values(environment,index,amount,expected):
    user,biz,*_=environment;ctx=Context(user,biz);created=create(ctx,index);rule=TaxSchedule.objects.get(pk=created['id'])
    with pytest.raises(ValidationError,match='Confirm'):calculate(rule,amount)
    preview=calculate(rule,amount,require_confirmed=False)
    assert preview['tax_amount']==expected and preview['requires_confirmation'] and preview['financial_posting'] is False
    confirm(ctx,created);rule.refresh_from_db();assert calculate(rule,amount)['tax_amount']==expected


def test_version_cutoff_override_currency_and_ambiguity_fail_closed(environment):
    user,biz,member,*_=environment;ctx=Context(user,biz)
    old=create(ctx,0);new=create(ctx,1)
    with pytest.raises(ValidationError,match='No confirmed'):select_schedule(ctx,'salary_wht','general','2026-07-11')
    confirm(ctx,old,'confirm-old');confirm(ctx,new,'confirm-new')
    assert select_schedule(ctx,'salary_wht','general','2026-07-10').pk==old['id']
    assert select_schedule(ctx,'salary_wht','general','2026-07-11').pk==new['id']
    assert select_schedule(ctx,'salary_wht','general','2026-07-11',override=old['id'],reason='Finalized older assessment requires its original schedule.').pk==old['id']
    with pytest.raises(ValidationError):select_schedule(ctx,'salary_wht','general','2026-07-11',override=old['id'],reason='short')
    with pytest.raises(ValidationError):select_schedule(ctx,'salary_wht','general','2026-07-11',currency_code='USD',override=old['id'],reason='Reviewed source and currency applicability.')
    member.permissions=['accounting.tax_view'];member.save()
    with pytest.raises(PermissionDenied):select_schedule(Context(user,biz),'salary_wht','general','2026-07-11',override=old['id'],reason='Reviewed tax exception.')
    member.permissions=['*'];member.save()
    competing=create(Context(user,biz),1,schedule_version='OVERLAP',effective_from='2026-07-01');confirm(Context(user,biz),competing,'confirm-overlap')
    with pytest.raises(ValidationError,match='overlap'):select_schedule(Context(user,biz),'salary_wht','general','2026-07-11')


@pytest.mark.parametrize('updates',[
    {'tax_type':[]},{'basis':{}},{'currency_code':[]},{'rounding_places':True},{'rounding_places':7},
    {'rounding_places':'2'},{'rate':'-1','brackets':[]},{'effective_to':'2025-01-01'},
    {'effective_from':'۱۴۰۵/۰۴/۲۰'},{'source_url':'http://example.com/rule'},
    {'source_url':'https://name:secret@example.com/rule'},{'source_url':'https://example.com/rule#private'},
    {'brackets':[{'lower':'1','rate':'0','fixed':'0'}]},
    {'brackets':[{'lower':'0','rate':'0','fixed':'0'},{'lower':'10000','rate':'10','fixed':'1'}]},
    {'brackets':[{'lower':'0','rate':'101','fixed':'0'}]},
    {'brackets':[{'lower':'0','rate':0.5,'fixed':'0'}]},
    {'brackets':[{'lower':'0','rate':'0','fixed':'0'},{'lower':'0','rate':'10','fixed':'0'}]},
    {'rate':'10'},{'rate':False},{'brackets':{}},{'supersedes':True},{'supersedes':'1'},
    {'requires_confirmation':False},{'source_retrieved_on':'2099-01-01'},{'name_fa':' '},
])
def test_bad_rules_are_rejected_without_partial_records(environment,updates):
    user,biz,*_=environment;before=unchanged()
    with pytest.raises(ValidationError):create(Context(user,biz),**updates)
    assert not TaxSchedule.objects.exists() and not TaxScheduleChange.objects.exists() and unchanged()==before


def test_rounding_is_explicit_no_float_and_no_precision_loss(environment):
    user,biz,*_=environment;ctx=Context(user,biz)
    created=create(ctx,2,schedule_version='ROUND-ZERO',rate='10',rounding_places=0)
    rule=TaxSchedule.objects.get(pk=created['id']);assert calculate(rule,'5',require_confirmed=False)['tax_amount']=='1'
    with pytest.raises(ValidationError):calculate(rule,10.5,require_confirmed=False)
    precise=create(ctx,2,schedule_version='ROUND-SIX',rate='0.123456',rounding_places=6)
    assert calculate(TaxSchedule.objects.get(pk=precise['id']),'100',require_confirmed=False)['tax_amount']=='0.123456'


def test_api_permissions_history_confirmation_and_localized_errors(environment):
    user,biz,member,loc,*_=environment;client=client_for(user,biz);before=unchanged()
    payload={'action':'create','rule':research()[1],'reason':'Source and applicability to be reviewed.'}
    response=client.post('/api/tax-schedules/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='tax-api-create')
    assert response.status_code==201,response.content;rule=response.json()['rule'];url=f"/api/tax-schedules/{rule['id']}/"
    preview=client.post(url,{'action':'preview','amount':'20000'},content_type='application/json')
    assert preview.status_code==200 and preview.json()['tax_amount']=='1000.00' and preview.json()['requires_confirmation']
    assert client.get('/api/tax-schedules/').json()['automatic_posting_enabled'] is False
    assert client.get(url).json()['history_total']==1
    member.permissions=['settings.manage'];member.save();assert client.get('/api/tax-schedules/').status_code==403
    member.permissions=['accounting.tax_view'];member.save();assert client.get(url).status_code==200
    assert client.post(url,{'action':'confirm','reason':'Reviewed and approved.','expected_revision':0},content_type='application/json',HTTP_IDEMPOTENCY_KEY='not-authorized').status_code==403
    member.permissions=['accounting.tax_manage'];member.all_locations=False;member.location_ids=[loc.pk];member.save()
    assert client.post('/api/tax-schedules/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='scope-denied').status_code==403
    member.permissions=['accounting.tax_confirm'];member.all_locations=True;member.save()
    for language in ['fa-AF','ps-AF']:
        denied=client.post(url,{'action':'confirm','reason':'short','expected_revision':0},content_type='application/json',HTTP_IDEMPOTENCY_KEY='short-reason-'+language,HTTP_ACCEPT_LANGUAGE=language)
        assert denied.status_code==400 and denied.json()['translation_complete'] is True
        assert denied['Content-Language']==language
    response=client.post(url,{'action':'confirm','reason':'Reviewed registration and applicability.','expected_revision':0},content_type='application/json',HTTP_IDEMPOTENCY_KEY='confirm-tax-api')
    assert response.status_code==200,response.content
    assert not response.json()['rule']['requires_confirmation']
    for offset in ['-1','not-a-number','999999999999999999999999999999']:
        assert client.get('/api/tax-schedules/',{'offset':offset}).status_code==400
        assert client.get(url,{'offset':offset}).status_code==400
    assert client.patch(url,{},content_type='application/json').status_code==405
    assert client.delete(url).status_code==405
    assert unchanged()==before


def test_other_tenant_refs_reads_and_database_guards(environment):
    user,biz,*_=environment;ctx=Context(user,biz);created=create(ctx)
    other=Business.objects.create(name='Other tax business',slug='other-tax')
    Membership.objects.create(user=user,business=other,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])
    second=create(Context(user,other));client=client_for(user,biz)
    assert {r['id'] for r in client.get('/api/tax-schedules/').json()['results']}=={created['id']}
    assert client.get(f"/api/tax-schedules/{second['id']}/").status_code==400
    with pytest.raises(ValidationError):create(ctx,schedule_version='FOREIGN-REV',supersedes=second['id'])
    with pytest.raises(DatabaseError),transaction.atomic():
        TaxSchedule.objects.filter(pk=created['id']).update(name_fa='Changed content')
    with pytest.raises(DatabaseError),transaction.atomic():
        TaxSchedule.objects.filter(pk=created['id']).update(requires_confirmation=False,verified_at=timezone.now(),confirmation_revision=1)
    with pytest.raises(DatabaseError),transaction.atomic():
        TaxSchedule.objects.filter(pk=created['id']).update(supersedes_id=second['id'])
    with pytest.raises(DatabaseError),transaction.atomic():
        TaxScheduleChange.objects.create(business=other,schedule_id=created['id'],actor=user,operation='create',reason='Wrong scope',request_key='cross-business',request_hash='0'*64)
    event=TaxScheduleChange.objects.get(schedule_id=created['id'])
    with pytest.raises(DatabaseError),transaction.atomic():TaxScheduleChange.objects.filter(pk=event.pk).update(reason='Rewrite')
    with pytest.raises(DatabaseError),transaction.atomic():TaxScheduleChange.objects.filter(pk=event.pk).delete()
    with pytest.raises(DatabaseError),transaction.atomic():
        # Raw DELETE avoids Django's PROTECT collector; the database also refuses deletion.
        from django.db import connection
        with connection.cursor() as cursor:cursor.execute('DELETE FROM erp_taxschedule WHERE id=%s',[created['id']])


def test_research_seed_is_explicit_unconfirmed_repeat_safe_and_nonposting(environment):
    user,biz,*_=environment;before=unchanged();output=StringIO()
    call_command('seed_tax_schedules',business=biz.slug,actor=user.username,stdout=output)
    assert json.loads(output.getvalue())['dry_run'] and not TaxSchedule.objects.exists()
    for _ in range(2):call_command('seed_tax_schedules',business=biz.slug,actor=user.username,apply=True,stdout=StringIO())
    assert TaxSchedule.objects.count()==5 and TaxScheduleChange.objects.count()==5
    assert not TaxSchedule.objects.filter(requires_confirmation=False).exists()
    assert not TaxSchedule.objects.filter(tax_type__in=['brt','vat','import_brt_advance']).exists()
    assert unchanged()==before


def test_permission_revoked_while_waiting_for_business_lock_is_rechecked(environment):
    user,biz,member,*_=environment;stale=Context(user,biz)
    member.permissions=['sales.view'];member.save()
    with pytest.raises(PermissionDenied):create(stale)
    assert not TaxSchedule.objects.exists() and not AuditEvent.objects.filter(action__startswith='tax.schedule.').exists()


def test_confirmation_state_changes_are_revisioned_and_old_decisions_cannot_be_replayed(environment):
    user,biz,*_=environment;ctx=Context(user,biz);draft=create(ctx);reviewed=confirm(ctx,draft)
    revoked=change(ctx,'revoke',{'expected_revision':reviewed['confirmation_revision'],'reason':'Tax evidence was withdrawn pending review.'},'revoke-for-race',draft['id'])
    with pytest.raises(ValidationError,match='changed'):confirm(ctx,draft,key='new-key-old-review')
    assert revoked['confirmation_revision']==2 and TaxSchedule.objects.get(pk=draft['id']).requires_confirmation
    current=confirm(ctx,revoked,key='confirm-reviewed-again');assert current['confirmation_revision']==3


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_version_and_idempotent_confirmation(environment):
    user,biz,*_=environment;created=create(Context(user,biz))
    def decide(_):
        close_old_connections()
        try:
            from django.contrib.auth import get_user_model
            actor=get_user_model().objects.get(pk=user.pk);business=Business.objects.get(pk=biz.pk)
            return confirm(Context(actor,business),created,'same-concurrent-confirm')
        finally:close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(decide,[0,1]))
    assert results[0]==results[1] and TaxScheduleChange.objects.filter(operation='confirm').count()==1
    assert TaxSchedule.objects.get(pk=created['id']).confirmation_revision==1
