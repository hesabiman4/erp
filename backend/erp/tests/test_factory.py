from decimal import Decimal
from erp.tests.test_growth import growth_env
from erp.tests.test_api import client_for,environment
from erp.models import Membership,Document

def test_factory_board_tracks_actual_work_and_staged_output_without_revealing_cost(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env
    post('stock_opening',{'warehouse':wh.id,'lines':[{'product':raw.id,'quantity':'100','value':'1000'}]})
    center=post('work_center',{'name':'Mixing','location':wh.location_id})
    work=post('work_order',{'work_center':center.result['work_center'],'warehouse':wh.id,'product':sp.id,'scheduled_date':'2026-06-01','planned_quantity':'10','planned_minutes':90})
    batch=post('production_start',{'warehouse':wh.id,'work_order':work.result['work_order']})
    post('production_consume',{'batch':batch.id,'inputs':[{'product':raw.id,'quantity':'10'}]})
    post('job_card',{'work_order':work.result['work_order'],'operation':'Mixing','minutes':20})
    client=client_for(ctx.user,ctx.business)
    row=client.get('/api/factory/').json()['results'][0]
    assert row['actual_quantity']=='0' and row['actual_minutes']==20
    assert row['batches'][0]['can_consume'] and row['batches'][0]['wip_remaining']=='100.00'
    post('production_complete',{'batch':batch.id,'warehouse':wh.id,'outputs':[{'product':sp.id,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'100'}]}]})
    row=client.get('/api/factory/').json()['results'][0]
    assert Decimal(row['actual_quantity'])==10 and not row['batches'][0]['can_consume']
    member=Membership.objects.get(pk=ctx.membership.pk);member.permissions=['production.view'];member.save()
    row=client.get('/api/factory/').json()['results'][0]
    assert 'wip_remaining' not in row['batches'][0] and 'inputs' not in str(row)
    member.all_locations=False;member.location_ids=[];member.save()
    assert client.get('/api/factory/').json()['results']==[]
    member.permissions=[];member.save()
    assert client.get('/api/factory/').status_code==403

def test_offline_review_retries_create_one_server_draft_and_reject_changed_content(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    client=client_for(ctx.user,ctx.business)
    data={'kind':'quotation','data':{'date':'2026-06-01','warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'quantity':'2'}]}}
    first=client.post('/api/documents/',data,content_type='application/json',HTTP_IDEMPOTENCY_KEY='offline-draft-test')
    second=client.post('/api/documents/',data,content_type='application/json',HTTP_IDEMPOTENCY_KEY='offline-draft-test')
    assert first.status_code==201 and second.status_code==200
    assert first.json()['id']==second.json()['id']
    draft=Document.objects.get(pk=first.json()['id']);assert not draft.entries.exists() and not draft.movements.exists()
    data['data']['notes']='Changed'
    assert client.post('/api/documents/',data,content_type='application/json',HTTP_IDEMPOTENCY_KEY='offline-draft-test').status_code==400
