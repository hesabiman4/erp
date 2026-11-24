from decimal import Decimal
import pytest
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env
from erp.models import Document,Entry,StockMovement,Block,Location,Membership
from erp.production_process import process_board


def test_process_stages_follow_original_postings_and_never_cosmetic_mutations(growth_env):
 ctx,post,wh,sp,raw,*_=growth_env
 post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':raw.pk,'quantity':'100','value':'1000'}]})
 batch=post('production_start',{'warehouse':wh.pk})
 assert process_board(ctx,{})['results'][0]['stage']=='materials'
 post('production_consume',{'batch':batch.pk,'inputs':[{'product':raw.pk,'quantity':'10'}]})
 row=process_board(ctx,{})['results'][0];assert row['stage']=='output' and row['initial']['batch']==batch.pk and row['wip_remaining']==100
 output=post('production_complete',{'batch':batch.pk,'outputs':[{'product':sp.pk,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000','status':'inspection'}]}]})
 row=process_board(ctx,{})['results'][0];assert row['stage']=='quality' and row['held_blocks']==1 and not row['can_consume']
 before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
 assert process_board(ctx,{})['results'][0]['stage']=='quality'
 assert (Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())==before
 block=Block.objects.get(batch=output)
 post('quality_release',{'block':block.pk,'reason':'Measured and inspected synthetic output approved.'})
 assert process_board(ctx,{})['results'][0]['stage']=='ready'
 client=client_for(ctx.user,ctx.business)
 assert client.post('/api/production-process/',{},content_type='application/json').status_code==405


def test_process_cost_input_and_location_scopes_are_preserved(growth_env):
 ctx,post,wh,sp,raw,*_=growth_env
 post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':raw.pk,'quantity':'100','value':'1000'}]})
 batch=post('production_start',{'warehouse':wh.pk})
 post('production_consume',{'batch':batch.pk,'inputs':[{'product':raw.pk,'quantity':'10'}]})
 ctx.membership.permissions=['production.view'];ctx.membership.save()
 row=process_board(ctx,{})['results'][0]
 assert 'wip_remaining' not in row and 'inputs' not in row and 'cost' not in row
 ctx.membership.product_lines=['adhesive'];ctx.membership.save()
 assert process_board(ctx,{})['results']==[]
 ctx.membership.product_lines=['sponge'];ctx.membership.all_locations=False;ctx.membership.location_ids=[];ctx.membership.save()
 assert process_board(ctx,{})['results']==[]


def test_full_document_related_links_are_original_and_permission_checked(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 quotation=post('quotation',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':'5','unit_price':'100'}]})
 order=post('sales_order',{'warehouse':wh.pk,'party':customer.pk,'quotation':quotation.pk,'lines':[{'product':sp.pk,'quantity':'5','unit_price':'100','source_line':0}]})
 client=client_for(ctx.user,ctx.business)
 data=client.get(f'/api/documents/{quotation.pk}/').json()
 assert order.pk in {r['id'] for r in data['related_documents']}
 assert client.get('/api/documents/?kind=quotation&state=posted').json()['results'][0]['id']==quotation.pk
 assert client.get('/api/documents/?state=invalid').status_code==400
 ctx.membership.product_lines=['adhesive'];ctx.membership.permissions=['sales.view'];ctx.membership.save()
 assert client.get(f'/api/documents/{quotation.pk}/').status_code==403
