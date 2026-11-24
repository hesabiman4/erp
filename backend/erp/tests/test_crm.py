from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.db import connection
from django.test.utils import CaptureQueriesContext
from erp.core import Context, execute
from erp.models import Business, Location, Warehouse, Membership, Document, Entry, StockMovement, Party
from erp.crm_models import CRMOpportunity, CRMEvent, CRMActivity
from erp.crm import opportunity_for, state
from erp.crm_api import detail
from erp.api import doc_permission
from erp.tests.test_growth import growth_env
from erp.tests.test_api import environment, client_for


def lead(ctx,post,wh,**extra):
    return post('crm_create',{'title':'Furniture maker needs grade45 sheets','location':wh.location_id,'prospect_name':'Prospect shop','phone':'0701234567','product_lines':['sponge'],'expected_amount':'10000','expected_date':'2026-06-10',**extra})


def member(ctx,name,permissions=None,lines=None,location_ids=None):
    user=get_user_model().objects.create_user(username=name)
    membership=Membership.objects.create(user=user,business=ctx.business,permissions=permissions or ['crm.view','crm.post','sales.post','sales.view'],product_lines=lines or ['sponge'],all_locations=location_ids is None,location_ids=location_ids or [],approval_limit='100000')
    return Context(user,ctx.business,membership)


def linked(post,op,wh,sp,customer,**extra):
    return post('crm_quote',{'opportunity':op.result['opportunity'],'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'quantity':'5','length_mm':'2000','width_mm':'1000','unit_price':str(sp.price)}],**extra})


def test_opportunity_activity_quotation_and_won_keep_expected_separate_from_revenue(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    before=Entry.objects.count(),StockMovement.objects.count()
    op=lead(ctx,post,wh,party=customer.id)
    todo=post('crm_activity',{'opportunity':op.result['opportunity'],'task':'Call customer and confirm sheet sizes','due_date':'2026-06-01'})
    value=detail(ctx,CRMOpportunity.objects.get(pk=op.result['opportunity']),date(2026,6,2))
    assert value['expected_amount']==Decimal('10000') and value['next_action']['overdue']
    quoted=linked(post,op,wh,sp,customer)
    quote=Document.objects.get(pk=quoted.result['quotation'])
    assert quote.kind=='quotation' and quote.data['crm_opportunity']==op.result['opportunity']
    assert quote.result['lines'][0]['quantity']=='5' and quote.result['lines'][0]['profile']=='2000.000x1000.000'
    post('crm_transition',{'opportunity':op.result['opportunity'],'stage':'quoted','reason':'Issued a priced full-face quotation.'})
    post('crm_activity_done',{'activity':todo.result['activity'],'reason':'Customer accepted the quoted size; delivery date pending.'})
    post('crm_transition',{'opportunity':op.result['opportunity'],'stage':'won','reason':'Customer gave a recorded commercial acceptance.'})
    result=detail(ctx,CRMOpportunity.objects.get(pk=op.result['opportunity']),date(2026,6,2))
    assert result['stage']=='won' and result['pending_activities']==0 and result['activities'][0]['outcome'].startswith('Customer accepted')
    assert result['quotations'][0]['amount']==sp.price*5
    assert before==(Entry.objects.count(),StockMovement.objects.count())
    with pytest.raises(ValidationError):post('crm_activity',{'opportunity':op.result['opportunity'],'task':'No silent reopen','due_date':'2026-06-02'})


def test_lost_reason_preserves_quote_and_does_not_cancel_it_or_writeoff_anything(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;op=lead(ctx,post,wh);quoted=linked(post,op,wh,sp,customer)
    with pytest.raises(ValidationError):post('crm_transition',{'opportunity':op.result['opportunity'],'stage':'lost','reason':''})
    lost=post('crm_transition',{'opportunity':op.result['opportunity'],'stage':'lost','reason':'Customer chose another delivery date.'})
    assert lost.result['quotation_cancellation_required_separately'] is True
    assert Document.objects.get(pk=quoted.result['quotation']).state=='posted'
    assert not Document.objects.filter(kind='order_cancel').exists() and not Entry.objects.exists()
    post('crm_note',{'opportunity':op.result['opportunity'],'note':'Historical follow-up note remains possible.'})


def test_assignment_and_activity_authority_are_scoped_and_do_not_rewrite_history(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    a=member(ctx,'crm-seller-a');b=member(ctx,'crm-seller-b')
    op=lead(ctx,post,wh,assigned=a.membership.id);item=CRMOpportunity.objects.get(pk=op.result['opportunity'])
    with pytest.raises(PermissionDenied):opportunity_for(b,item.id)
    with pytest.raises(PermissionDenied):execute(a,'crm_assign',{'date':'2026-06-01','opportunity':item.id,'assigned':b.membership.id,'reason':'Cannot self-delegate.'},str(uuid4()))
    activity=post('crm_activity',{'opportunity':item.id,'assigned':b.membership.id,'task':'Second salesperson checks customer dimensions','due_date':'2026-06-02'})
    assert opportunity_for(b,item.id).id==item.id
    with pytest.raises(PermissionDenied):execute(b,'crm_note',{'date':'2026-06-01','opportunity':item.id,'note':'Activity access does not grant opportunity edit.'},str(uuid4()))
    execute(b,'crm_activity_done',{'date':'2026-06-01','activity':activity.result['activity'],'reason':'Measured requested footprint.'},str(uuid4()))
    post('crm_assign',{'opportunity':item.id,'assigned':b.membership.id,'reason':'Reviewed workload handover.'})
    item.refresh_from_db();assert item.assigned_id==a.membership.id and state(item)[1]==b.membership.id
    assert CRMEvent.objects.filter(opportunity=item,kind='assignment').count()==1


def test_other_business_location_lines_and_inactive_assignee_are_rejected(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    op=lead(ctx,post,wh,product_lines=['sponge','adhesive']);only=member(ctx,'crm-only-sponge')
    with pytest.raises(PermissionDenied):opportunity_for(only,op.result['opportunity'])
    foreign=Business.objects.create(name='Isolated CRM business',slug='isolated-crm')
    party=Party.objects.create(business=foreign,name='Private foreign customer',kind='customer')
    with pytest.raises(ValidationError):lead(ctx,post,wh,party=party.id)
    invalid=member(ctx,'crm-inactive');invalid.membership.active=False;invalid.membership.save()
    with pytest.raises(ValidationError):lead(ctx,post,wh,assigned=invalid.membership.id)
    otherloc=Location.objects.create(business=ctx.business,name='Private branch',code='CRM-PRIVATE')
    limited=member(ctx,'crm-other-location',location_ids=[otherloc.id])
    with pytest.raises(PermissionDenied):opportunity_for(limited,op.result['opportunity'])
    with pytest.raises(DatabaseError),transaction.atomic():
        CRMOpportunity.objects.filter(pk=op.result['opportunity']).update(party=party)


def test_quote_product_scope_customer_consistency_live_quote_and_conversion_guards(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;op=lead(ctx,post,wh)
    with pytest.raises(ValidationError):linked(post,op,wh,raw,customer)
    with pytest.raises(ValidationError):post('crm_transition',{'opportunity':op.result['opportunity'],'stage':'won','reason':'Cannot declare a win before a real quotation.'})
    quoted=linked(post,op,wh,sp,customer);quote=Document.objects.get(pk=quoted.result['quotation'])
    other=Party.objects.create(business=ctx.business,kind='customer',name='Another customer')
    with pytest.raises(ValidationError):linked(post,op,wh,sp,other)
    with pytest.raises(ValidationError):post('quotation',{'warehouse':wh.id,'party':customer.id,'crm_opportunity':op.result['opportunity'],'lines':quote.data['lines']})
    user=member(ctx,'crm-unassigned-converter')
    with pytest.raises(PermissionDenied):execute(user,'sales_order',{'date':'2026-06-01','quotation':quote.id,'warehouse':wh.id,'party':customer.id,'lines':quote.data['lines']},str(uuid4()))
    post('order_cancel',{'order':quote.id,'reason':'Actual quote closure is a separate approved commercial action.'})
    with pytest.raises(ValidationError):post('crm_transition',{'opportunity':op.result['opportunity'],'stage':'won','reason':'Cancelled quotations cannot support this win.'})


def test_event_idempotency_chronology_and_database_immutability(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;op=lead(ctx,post,wh);item=CRMOpportunity.objects.get(pk=op.result['opportunity'])
    data={'opportunity':item.id,'task':'Obtain preferred delivery date','due_date':'2026-06-05'}
    first=post('crm_activity',data,'one-follow-up');assert post('crm_activity',data,'one-follow-up').id==first.id
    with pytest.raises(ValidationError):post('crm_activity',{**data,'task':'Different task'},'one-follow-up')
    event=post('crm_note',{'date':'2026-06-03','opportunity':item.id,'note':'Prospect spoke on June3.'})
    with pytest.raises(ValidationError):post('crm_transition',{'opportunity':item.id,'stage':'qualified','reason':'Cannot rewrite the prior timeline.'})
    for model,pk,field,value in [(CRMOpportunity,item.id,'title','Rewritten'),(CRMEvent,event.result['event'],'reason','Changed'),(CRMActivity,first.result['activity'],'task','Changed')]:
        with pytest.raises(DatabaseError),transaction.atomic():model.objects.filter(pk=pk).update(**{field:value})
    completed=post('crm_activity_done',{'date':'2026-06-03','activity':first.result['activity'],'reason':'Actual completed outcome.'})
    with pytest.raises(DatabaseError),transaction.atomic():CRMActivity.objects.filter(pk=first.result['activity']).update(completed_by=None)
    with pytest.raises(ValidationError):post('crm_activity_done',{'date':'2026-06-03','activity':first.result['activity'],'reason':'No second completion.'})


def test_private_opportunity_and_generated_quote_json_and_print_deny_unassigned_reader(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env;op=lead(ctx,post,wh);quoted=linked(post,op,wh,sp,customer)
    other=member(ctx,'crm-private-reader',permissions=['crm.view','sales.view','documents.view'])
    client=client_for(other.user,ctx.business)
    headers={'HTTP_X_BUSINESS_ID':str(ctx.business.id)}
    listing=client.get('/api/crm/',**headers)
    assert listing.status_code==200 and listing.json()['count']==0
    for path in [f'/api/crm/?opportunity={op.result["opportunity"]}',f'/api/documents/{op.id}/',f'/api/documents/{quoted.result["quotation"]}/',f'/api/documents/{quoted.result["quotation"]}/print/']:
        assert client.get(path,**headers).status_code==403
    own=client_for(ctx.user,ctx.business)
    data=own.get('/api/crm/?stage=new&limit=1',**headers)
    assert data.status_code==200 and data.json()['count']==1 and len(data.json()['results'])==1
    assert data.json()['results'][0]['expected_amount']=='10000.00'
    assert own.get('/api/crm/?limit=500',**headers).status_code==400


def test_pipeline_counts_and_page_loading_keep_database_queries_bounded(growth_env):
    ctx,post,wh,sp,raw,customer,supplier=growth_env
    lead(ctx,post,wh)
    client=client_for(ctx.user,ctx.business)
    with CaptureQueriesContext(connection) as first:
        response=client.get('/api/crm/?limit=1')
    assert response.status_code==200 and response.json()['count']==1
    for index in range(10):lead(ctx,post,wh,title=f'Additional commercial opportunity {index}')
    with CaptureQueriesContext(connection) as second:
        response=client.get('/api/crm/?limit=1')
    result=response.json()
    assert response.status_code==200 and result['count']==11 and result['stage_counts']['new']==11
    assert len(result['results'])==1 and result['next_offset']==1
    assert len(second)<=len(first)+2, (len(first),len(second))
