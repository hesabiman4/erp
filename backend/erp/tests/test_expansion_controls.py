from decimal import Decimal
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env
from erp.core import get_obj
from erp.models import Membership,Product,ForeignExposure,BOM
from erp.reports import report

def test_recalled_pooled_product_cannot_bypass_hold_using_foreign_sale(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    product=Product.objects.create(business=ctx.business,code='ADH-FX',name='Adhesive',kind='finished',unit='kg',line='adhesive',price='70')
    post('stock_opening',{'warehouse':wh.id,'lines':[{'product':raw.id,'quantity':'100','value':'1000'}]})
    batch=post('production',{'warehouse':wh.id,'inputs':[{'product':raw.id,'quantity':'10'}],'outputs':[{'product':product.id,'quantity':'10'}]})
    post('quality_recall',{'batch':batch.id,'reason':'Pooled output must stay held across all sale entry points'})
    with pytest.raises(ValidationError,match='recall'):
        post('fx_sale',{'warehouse':wh.id,'party':customer.id,'foreign_currency':'USD','rate':'70','rate_reference':'Approved rate','lines':[{'product':product.id,'quantity':'1','foreign_unit_price':'1'}]})

def test_foreign_customer_cash_dashboard_includes_deposits_refunds_settlement_and_reversal(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    service=Product.objects.create(business=ctx.business,code='SERVICE-FX',name='Service',kind='service',unit='each',line='sponge',price='700')
    invoice=post('fx_sale',{'warehouse':wh.id,'party':customer.id,'foreign_currency':'USD','rate':'70','rate_reference':'Approved rate','lines':[{'product':service.id,'quantity':'1','foreign_unit_price':'10'}]})
    exposure=ForeignExposure.objects.get(invoice=invoice)
    settlement=post('fx_settle',{'exposure':exposure.id,'foreign_currency':'USD','foreign_amount':'5','rate':'70','rate_reference':'Approved rate','location':wh.location_id})
    assert report(ctx,'dashboard',{})['collections']=='350.00'
    post('fx_settlement_reverse',{'settlement':settlement.id,'reason':'Correct erroneous customer collection'})
    assert report(ctx,'dashboard',{})['collections']=='0.00'
    deposit=post('fx_deposit',{'party':customer.id,'side':'customer','classification':'refundable_monetary','location':wh.location_id,'foreign_currency':'USD','foreign_amount':'2','rate':'70','rate_reference':'Approved rate'})
    assert report(ctx,'dashboard',{})['collections']=='140.00'
    post('fx_refund',{'deposit':deposit.result['deposit'],'foreign_amount':'1','rate':'70','rate_reference':'Approved rate','reason':'Refund unused monetary credit'})
    assert report(ctx,'dashboard',{})['collections']=='70.00'

def test_job_bom_document_cannot_leak_recipe_to_general_project_reader(growth_env):
    ctx,post,wh,sp,raw,customer,*_=growth_env
    ctx.business.manufacturing_mode='bom';ctx.business.save(update_fields=['manufacturing_mode'])
    bom=BOM.objects.create(business=ctx.business,product=sp,name='Private recipe',version=1,approved=True,output_quantity='10',components=[{'product':raw.id,'quantity':'17'}])
    project=post('job_project',{'location':wh.location_id,'customer':customer.id,'code':'PRIVATE-JOB','name':'Private project'})
    plan=post('job_bom_plan',{'project':project.result['project'],'bom':bom.id,'quantity':'10'})
    member=Membership.objects.get(pk=ctx.membership.pk);member.permissions=['jobs.view','documents.view'];member.save()
    client=client_for(ctx.user,ctx.business)
    assert client.get(f'/api/documents/{plan.id}/').status_code==403
    result=client.get('/api/jobs/projects/').json()['results'][0]
    assert result['bom_plans']==[] and '17' not in str(result.get('bom_plans'))
