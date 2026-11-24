from decimal import Decimal
from uuid import uuid4
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import DatabaseError,transaction
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.core import Context,execute,balance
from erp.models import *
from erp.cashier_shifts import expected,denominations


def setup_shift(ctx,post,wh,amount='5000'):
    if Decimal(amount):post('opening_cash',{'location':wh.location_id,'amount':amount,'reason':'Synthetic opening float.'})
    drawer_doc=post('cash_drawer',{'location':wh.location_id,'code':'COUNTER','name':'Main accountable cash','confirm_location_pool':True})
    drawer=CashDrawer.objects.get(pk=drawer_doc.result['drawer'])
    opened=post('cash_shift_open',{'drawer':drawer.id,'denominations':[{'value':amount,'count':'1'}] if Decimal(amount) else []})
    return drawer,CashShift.objects.get(pk=opened.result['shift'])


def test_shift_counts_and_handover_preserve_cash_gl_and_invoice_receipts(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    drawer,shift=setup_shift(ctx,post,wh)
    block=open_block(post,wh,sp)
    sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'10'}],'paid':'500'})
    assert expected(shift)==5500 and balance(ctx,'CASH',location=wh.location_id)==5500
    assert CashShiftEntry.objects.get(entry__document=sale,entry__account__code='CASH').shift_id==shift.id
    before=Entry.objects.count()
    counted=post('cash_shift_count',{'shift':shift.id,'denominations':[{'value':'500','count':'11'}],'note':'Cashier signed the full drawer count.'})
    assert counted.result['variance']=='0.00' and Entry.objects.count()==before
    with pytest.raises(ValidationError):post('opening_cash',{'location':wh.location_id,'amount':'1','reason':'Frozen drawer.'})
    closed=post('cash_shift_review',{'shift':shift.id,'reason':'Owner small-team exception: count verified.'})
    assert not Entry.objects.filter(document=closed).exists()
    handed=post('cash_handover',{'shift':shift.id,'receiver':ctx.membership.id,'note':'Signed handover to next shift.'})
    next_shift=post('cash_shift_open',{'drawer':drawer.id,'denominations':[{'value':'500','count':'11'}]})
    assert next_shift.result['handover']==handed.result['handover']
    assert balance(ctx,'CASH',location=wh.location_id)==5500
    assert CashShift.objects.get(pk=shift.id).state=='closed'
    assert CashShift.objects.get(pk=next_shift.result['shift']).opening_amount==5500
    assert Entry.objects.count()==before


def test_shortage_requires_explicit_supervisor_posting_never_employee_debt(growth_env):
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'1000')
    post('cash_shift_count',{'shift':shift.id,'denominations':[{'value':'100','count':'9'}],'note':'100 AFN shortage found.'})
    before=Entry.objects.count()
    with pytest.raises(ValidationError):post('cash_shift_review',{'shift':shift.id,'reason':'Cannot erase the shortage.'})
    assert Entry.objects.count()==before
    reviewed=post('cash_shift_review',{'shift':shift.id,'post_variance':True,'reason':'Owner reviewed documented 100 AFN physical shortage.'})
    assert Entry.objects.get(document=reviewed,account__code='CASH').credit==100
    assert Entry.objects.get(document=reviewed,account__code='EXPENSE').debit==100
    assert not Entry.objects.filter(document=reviewed,account__code='ADVANCES').exists()
    assert balance(ctx,'CASH',location=wh.location_id)==expected(shift)==900
    assert not reviewed.result['employee_debt_created']
    with pytest.raises(ValidationError):post('cash_shift_review',{'shift':shift.id,'reason':'Second review.'})


def test_overage_records_other_income_only_after_review(growth_env):
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'100')
    post('cash_shift_count',{'shift':shift.id,'denominations':[{'value':'20','count':'6'}],'note':'20 AFN excess counted.'})
    assert balance(ctx,'CASH',location=wh.location_id)==100
    review=post('cash_shift_review',{'shift':shift.id,'post_variance':True,'reason':'Unidentified excess reviewed as other income.'})
    assert Entry.objects.get(document=review,account__code='OTHER_INCOME').credit==20
    assert expected(shift)==balance(ctx,'CASH',location=wh.location_id)==120
    from erp.reports import cash_flow
    assert cash_flow(ctx,{'to':'2026-06-01'})['totals']['operating']=='20.00'


def test_control_activation_is_explicit_then_backdating_and_missing_shift_roll_back(growth_env):
    ctx,post,wh,*_=growth_env
    drawer_doc=post('cash_drawer',{'location':wh.location_id,'code':'C','name':'Counter','confirm_location_pool':True})
    post('opening_cash',{'location':wh.location_id,'amount':'1000','reason':'Before first accepted opening count.'})
    with pytest.raises(ValidationError):post('cash_shift_open',{'drawer':drawer_doc.result['drawer'],'denominations':[{'value':'100','count':'9'}]})
    opened=post('cash_shift_open',{'drawer':drawer_doc.result['drawer'],'denominations':[{'value':'100','count':'10'}]})
    shift=CashShift.objects.get(pk=opened.result['shift']);assert shift.drawer.activated_by_id==opened.id
    before=(Document.objects.count(),Entry.objects.count())
    with pytest.raises(ValidationError):post('opening_cash',{'date':'2026-05-31','location':wh.location_id,'amount':'10','reason':'Backdated custody bypass.'})
    with pytest.raises(ValidationError):post('expense_post',{'location':wh.location_id,'amount':'1001','cash_account':'CASH','expense_account':'EXPENSE'})
    assert before==(Document.objects.count(),Entry.objects.count()) and expected(shift)==1000


def test_separate_review_and_authorized_delegation_with_reason(growth_env):
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'1000')
    user=get_user_model().objects.create_user(username='cash-supervisor')
    member=Membership.objects.create(business=ctx.business,user=user,all_locations=True,product_lines=['sponge','adhesive','shared'],permissions=['cash_shifts.review','cash_shifts.delegate','finance.post'],approval_limit='10000')
    supervisor=Context(user,ctx.business)
    def by_supervisor(action,payload):return execute(supervisor,action,{'date':'2026-06-01',**payload},str(uuid4()))
    with pytest.raises(ValidationError):by_supervisor('expense_post',{'location':wh.location_id,'amount':'50','cash_account':'CASH'})
    payout=by_supervisor('expense_post',{'location':wh.location_id,'amount':'50','cash_account':'CASH','cash_reason':'Cashier paid an authorized shop expense in my presence.'})
    assert CashShiftEntry.objects.get(entry__document=payout).reason.startswith('Cashier paid')
    post('cash_shift_count',{'shift':shift.id,'denominations':[{'value':'50','count':'19'}],'note':'Full cash counted.'})
    ctx.membership.permissions=['cash_shifts.open','cash_shifts.review'];ctx.membership.save()
    with pytest.raises(PermissionDenied):post('cash_shift_review',{'shift':shift.id,'reason':'Cashier cannot self-review.'})
    reviewed=by_supervisor('cash_shift_review',{'shift':shift.id,'reason':'Independent supervisor signed the exact count.'})
    assert reviewed.result['actual_cash']=='950.00'


def test_recount_preserves_prior_evidence_and_receiving_cashier_accepts_handover(growth_env):
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'100')
    first=post('cash_shift_count',{'shift':shift.id,'denominations':[{'value':'10','count':'9'}],'note':'Initial observation.'})
    post('cash_shift_recount',{'shift':shift.id,'reason':'Recheck the missed banknote.'})
    second=post('cash_shift_count',{'shift':shift.id,'denominations':[{'value':'10','count':'10'}],'note':'Count corrected with both observers.'})
    assert CashShiftCount.objects.filter(shift=shift).count()==2
    post('cash_shift_review',{'shift':shift.id,'reason':'Final observation independently checked.'})
    user=get_user_model().objects.create_user(username='incoming-cashier');member=Membership.objects.create(business=ctx.business,user=user,permissions=['cash_shifts.open'],all_locations=True,product_lines=['sponge','adhesive','shared'])
    offered=post('cash_handover',{'shift':shift.id,'receiver':member.id,'note':'Signed physical count handed to incoming cashier.'})
    with pytest.raises(PermissionDenied):post('cash_shift_open',{'drawer':drawer.id,'denominations':[{'value':'10','count':'10'}]})
    accepted=execute(Context(user,ctx.business),'cash_shift_open',{'date':'2026-06-01','drawer':drawer.id,'denominations':[{'value':'10','count':'10'}]},str(uuid4()))
    assert CashHandover.objects.get(pk=offered.result['handover']).accepted_by_id==accepted.id
    assert first.result['count']!=second.result['count'] and balance(ctx,'CASH',location=wh.location_id)==100


def test_drawer_scope_privacy_and_database_custody_immutability(growth_env):
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'100')
    user=get_user_model().objects.create_user(username='other-cashier');member=Membership.objects.create(business=ctx.business,user=user,permissions=['cash_shifts.open','documents.view'],all_locations=True,product_lines=['sponge','adhesive','shared'])
    client=client_for(user,ctx.business)
    assert client.get(f'/api/cashier/?shift={shift.id}').status_code==403
    assert client.get(f'/api/documents/{shift.source_id}/').status_code==403
    assert client.get(f'/api/documents/{shift.source_id}/print/').status_code==403
    row=client.get('/api/cashier/').json()['drawers'][0];assert row['recorded_cash'] is None and row['active_shift'] is None
    with pytest.raises(DatabaseError),transaction.atomic():CashShift.objects.filter(pk=shift.id).update(opening_amount=999)
    with pytest.raises(DatabaseError),transaction.atomic():CashDrawer.objects.filter(pk=drawer.id).update(activated_by=None)
    with pytest.raises(DatabaseError),transaction.atomic():CashShift.objects.filter(pk=shift.id).delete()
    member.product_lines=['sponge'];member.save()
    Product.objects.create(business=ctx.business,code='RESTRICTED-AD',name='Adhesive',unit='kg',kind='finished',line='adhesive')
    assert client.get('/api/cashier/').json()['drawers']==[]


def test_denominations_reject_fractional_notes_and_ambiguous_money():
    assert denominations([{'value':'۱۰۰','count':'۲'},{'value':'50','count':'1'}])[1]==250
    for rows in [[{'value':'100','count':'1.5'}],[{'value':'100','count':'-1'}],[{'value':'100','count':'1'},{'value':'100.00','count':'2'}],[{'value':'0.001','count':'1'}]]:
        with pytest.raises(ValidationError):denominations(rows)


def test_cash_count_retry_and_database_missing_link_are_safe(growth_env):
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'100')
    payload={'shift':shift.id,'denominations':[{'value':'100','count':'1'}],'note':'Idempotent signed count.'}
    first=post('cash_shift_count',payload,'count-once')
    assert post('cash_shift_count',payload,'count-once').id==first.id
    assert CashShiftCount.objects.filter(shift=shift).count()==1
    # An accidental future domain implementation cannot bypass the journal
    # custody hook by creating balanced entries and directly posting its doc.
    with pytest.raises(DatabaseError),transaction.atomic():
        doc=Document.objects.create(business=ctx.business,kind='journal_adjust',number='UNLINKED-CASH-TEST',date='2026-06-01',created_by=ctx.user)
        Entry.objects.create(document=doc,account=Account.objects.get(business=ctx.business,code='CASH'),location=wh.location,debit='1')
        Entry.objects.create(document=doc,account=Account.objects.get(business=ctx.business,code='EQUITY'),location=wh.location,credit='1')
        doc.state='posted';doc.save(update_fields=['state'])
    assert balance(ctx,'CASH',location=wh.location_id)==100


def test_pending_handover_reassignment_preserves_original_receiver_and_audit(growth_env):
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'100')
    post('cash_shift_count',{'shift':shift.id,'denominations':[{'value':'100','count':'1'}],'note':'Count signed.'})
    post('cash_shift_review',{'shift':shift.id,'reason':'Count independently verified.'})
    user=get_user_model().objects.create_user(username='departing-receiver');receiver=Membership.objects.create(business=ctx.business,user=user,permissions=['cash_shifts.open'],all_locations=True,product_lines=['sponge','adhesive','shared'])
    offered=post('cash_handover',{'shift':shift.id,'receiver':receiver.id,'note':'Originally assigned receiving cashier.'})
    receiver.active=False;receiver.save(update_fields=['active'])
    redirected=post('cash_handover_redirect',{'handover':offered.result['handover'],'receiver':ctx.membership.id,'reason':'Original receiving employee left; owner accepts custody after recount.'})
    item=CashHandover.objects.get(pk=offered.result['handover'])
    assert item.receiver_id==receiver.id and redirected.result['previous_receiver']==receiver.id
    opened=post('cash_shift_open',{'drawer':drawer.id,'denominations':[{'value':'100','count':'1'}]})
    item.refresh_from_db();assert item.accepted_by_id==opened.id
    with pytest.raises(ValidationError):post('cash_handover_redirect',{'handover':item.id,'receiver':receiver.id,'reason':'Cannot rewrite accepted history.'})
    assert balance(ctx,'CASH',location=wh.location_id)==100


def test_nested_draft_cash_cannot_be_spent_twice(growth_env,monkeypatch):
    from erp import core
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'1000')
    original=core.registry
    def handler(local,p,doc):
        core.journal(local,doc,[{'account':'CASH','credit':'600','location':wh.location_id},{'account':'EXPENSE','debit':'600','location':wh.location_id}])
        execute(local,'expense_post',{'date':'2026-06-01','location':wh.location_id,'amount':'600','cash_account':'CASH'},'nested-child-cash')
        return {}
    monkeypatch.setattr(core,'registry',lambda:{**original(),'nested_cash_test':('finance.post',handler)})
    before=(Document.objects.count(),Entry.objects.count(),CashShiftEntry.objects.count())
    with pytest.raises(ValidationError):post('nested_cash_test',{})
    assert before==(Document.objects.count(),Entry.objects.count(),CashShiftEntry.objects.count())
    assert expected(shift)==balance(ctx,'CASH',location=wh.location_id)==1000


def test_dari_delegation_reason_is_decoded_and_preserved(growth_env):
    from urllib.parse import quote
    ctx,post,wh,*_=growth_env;drawer,shift=setup_shift(ctx,post,wh,'1000')
    user=get_user_model().objects.create_user(username='dari-cash-supervisor');Membership.objects.create(business=ctx.business,user=user,permissions=['finance.post','cash_shifts.delegate'],all_locations=True,product_lines=['sponge','adhesive','shared'],approval_limit='10000')
    client=client_for(user,ctx.business);reason='پرداخت مصرف دکان در حضور مسئول صندوق'
    r=client.post('/api/operations/expense_post/',{'date':'2026-06-01','location':wh.location_id,'amount':'50','cash_account':'CASH'},content_type='application/json',HTTP_IDEMPOTENCY_KEY='dari-reason',HTTP_X_CASH_REASON=quote(reason))
    assert r.status_code==201,r.content
    assert CashShiftEntry.objects.get(entry__document_id=r.json()['document']['id']).reason==reason


@pytest.mark.django_db(transaction=True)
def test_competing_opening_counts_create_only_one_active_cashier(growth_env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import connections
    ctx,post,wh,*_=growth_env
    post('opening_cash',{'location':wh.location_id,'amount':'100','reason':'Synthetic concurrency float.'})
    drawer=post('cash_drawer',{'location':wh.location_id,'code':'ONE','name':'One accountable pool','confirm_location_pool':True}).result['drawer']
    ready=Barrier(2)
    def attempt(key):
        connections.close_all()
        try:
            local=Context(ctx.user,ctx.business);ready.wait(timeout=15)
            execute(local,'cash_shift_open',{'date':'2026-06-01','drawer':drawer,'denominations':[{'value':'100','count':'1'}]},key)
            return 'opened'
        except ValidationError:return 'occupied'
        finally:connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(attempt,['cash-open-a','cash-open-b']))
    assert sorted(results)==['occupied','opened']
    assert CashShift.objects.count()==1 and Document.objects.filter(kind='cash_shift_open').count()==1
