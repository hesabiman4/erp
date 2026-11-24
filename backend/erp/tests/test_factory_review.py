from decimal import Decimal
from django.core.exceptions import PermissionDenied,ValidationError
import pytest
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env
from erp.core import Context
from erp.models import Document,Entry,StockMovement,Product,Block,Location,Warehouse,Business,Membership
from erp.factory_review import review

def produce(ctx,post,wh,sp,raw):
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':raw.pk,'quantity':'100','value':'1000'}]})
    batch=post('production',{'warehouse':wh.pk,'inputs':[{'product':raw.pk,'quantity':'10'}],'outputs':[{'product':sp.pk,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1060'}]}]})
    return batch,Block.objects.get(batch=batch)

def test_measured_output_trim_and_inputs_are_separate_from_current_stock_and_formula(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env;batch,block=produce(ctx,post,wh,sp,raw)
    trim=Product.objects.create(business=ctx.business,code='TRIM',name='Measured trim',kind='trim',unit='kg',line='sponge')
    post('trim',{'block':block.pk,'main_height_mm':'1000','top_height_mm':'30','bottom_height_mm':'20','loss_mm':'10','outputs':[{'product':trim.pk,'quantity':'2','cost':'5'}]})
    post('sale',{'warehouse':wh.pk,'customer_name':'Training counter','lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'22'}],'paid':'1100'})
    before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    result=review(ctx,{'from':'2026-06-01','to':'2026-06-01'})
    assert len(result['outputs'])==1 and result['outputs'][0]['quantity']==106 and result['outputs'][0]['blocks']==1
    assert result['outputs'][0]['carrying_value']==100 and result['inputs'][0]['quantity']==10
    assert result['trims'][0]['loss_mm']==10 and result['trims'][0]['main_mm']==1000
    assert abs(result['trims'][0]['loss_percent']-Decimal('0.9433962264150943396226415094'))<Decimal('.00000001')
    block.refresh_from_db();assert block.remaining_height_mm==978
    assert not result['financial_posting'] and before==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
    assert 'formula' not in str(result['inputs'])

def test_partial_staged_period_counts_consumption_returns_and_completion_on_effective_dates(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env
    post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':raw.pk,'quantity':'100','value':'1000'}]})
    start=post('production_start',{'warehouse':wh.pk})
    consume=post('production_consume',{'batch':start.pk,'warehouse':wh.pk,'inputs':[{'product':raw.pk,'quantity':'20'}]})
    post('production_material_return',{'date':'2026-06-02','consumption':consume.pk,'lines':[{'index':0,'quantity':'5'}]})
    completed=post('production_complete',{'date':'2026-06-03','batch':start.pk,'warehouse':wh.pk,'outputs':[{'product':sp.pk,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'}]}]})
    first=review(ctx,{'from':'2026-06-01','to':'2026-06-01'});assert first['batch_starts']==1 and first['outputs']==[] and first['inputs'][0]['quantity']==20
    returns=review(ctx,{'from':'2026-06-02','to':'2026-06-02'});assert returns['inputs'][0]['quantity']==-5
    whole=review(ctx,{'from':'2026-06-01','to':'2026-06-03'});assert whole['output_events']==1 and whole['outputs'][0]['quantity']==100 and whole['inputs'][0]['quantity']==15

def test_job_minutes_and_maintenance_downtime_are_measured_without_payroll(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env
    center=post('work_center',{'location':wh.location_id,'name':'Mixing','daily_minutes':480})
    work=post('work_order',{'warehouse':wh.pk,'product':sp.pk,'work_center':center.result['work_center'],'planned_quantity':'100','planned_minutes':120,'scheduled_date':'2026-06-01'})
    post('job_card',{'work_order':work.result['work_order'],'operation':'Measured mixing','minutes':90})
    equipment=post('equipment_create',{'work_center':center.result['work_center'],'name':'Training mixer','next_service':'2026-06-01'})
    job=post('maintenance_open',{'equipment':equipment.result['equipment'],'due_date':'2026-06-01','reason':'Reviewed repair'})
    post('maintenance_complete',{'maintenance':job.result['maintenance'],'downtime_minutes':35,'lines':[]})
    result=review(ctx,{'from':'2026-06-01','to':'2026-06-01'})
    assert result['job_time'][0]['minutes']==90 and result['downtime'][0]['minutes']==35
    assert not Entry.objects.filter(document__business=ctx.business,account__code='SALARY_PAYABLE').exists()

def test_factory_review_redacts_consumption_costs_maintenance_and_other_scope(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env;produce(ctx,post,wh,sp,raw)
    member=ctx.membership;member.permissions=['production.view'];member.save()
    result=review(Context(ctx.user,ctx.business),{'from':'2026-06-01','to':'2026-06-01'})
    assert 'inputs' not in result and 'costs' not in result and 'carrying_value' not in result['outputs'][0] and result['downtime'] is None
    member.product_lines=['adhesive'];member.save();assert review(Context(ctx.user,ctx.business),{'from':'2026-06-01','to':'2026-06-01'})['outputs']==[]
    member.permissions=['sales.view'];member.save()
    with pytest.raises(PermissionDenied):review(Context(ctx.user,ctx.business),{})

def test_factory_review_rejects_inverted_and_unbounded_dates(growth_env):
    ctx,*_=growth_env
    for params in [{'from':'2026-06-02','to':'2026-06-01'},{'from':'2024-01-01','to':'2026-06-01'}]:
        with pytest.raises(ValidationError):review(ctx,params)

def test_trim_review_preserves_source_warehouse_after_the_block_moves_branch(growth_env):
    ctx,post,wh,sp,raw,*_=growth_env;batch,block=produce(ctx,post,wh,sp,raw)
    post('trim',{'block':block.pk,'main_height_mm':'1050','loss_mm':'10'})
    location=Location.objects.create(business=ctx.business,name='Kabul',code='K')
    target=Warehouse.objects.create(business=ctx.business,location=location,name='Kabul stock')
    dispatch=post('transfer_dispatch',{'warehouse':wh.pk,'destination':target.pk,'lines':[{'product':sp.pk,'block':block.pk}]})
    post('transfer_receive',{'transfer':dispatch.pk})
    block.refresh_from_db();assert block.warehouse_id==target.pk
    ctx.membership.all_locations=False;ctx.membership.location_ids=[wh.location_id];ctx.membership.save()
    result=review(Context(ctx.user,ctx.business),{'from':'2026-06-01','to':'2026-06-01'})
    assert len(result['trims'])==1 and result['trims'][0]['warehouse_name']==wh.name and result['trims'][0]['loss_mm']==10
