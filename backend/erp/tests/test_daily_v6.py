from decimal import Decimal
from uuid import uuid4
import pytest
from django.core.exceptions import PermissionDenied,ValidationError
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.models import *
from erp.core import Context,create_draft
from erp.draft_editing import view,save,undo
from erp.daily_v6 import timeline,trends,attention

def test_structured_draft_edit_undo_stale_and_no_financial_effect(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 draft=create_draft(ctx,'sale',{'date':'2026-06-01','warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'quantity':'2','unit_price':'100'}],'paid':'0'})
 original=view(ctx,draft.pk);assert original['fields'][0]['type']=='date'
 changed=save(ctx,draft.pk,{'paid':'12.34','lines':[{'product':sp.pk,'quantity':'3','unit_price':'120'}]},original['version'])
 draft.refresh_from_db();assert draft.data['paid']=='12.34' and draft.data['lines'][0]['quantity']=='3'
 assert Entry.objects.count()==0 and StockMovement.objects.count()==0
 with pytest.raises(ValidationError):save(ctx,draft.pk,{'paid':'20'},original['version'])
 restored=undo(ctx,draft.pk,changed['undo_event']);assert restored['data']['paid']=='0' and restored['data']['lines'][0]['quantity']=='2'
 with pytest.raises(ValidationError):undo(ctx,draft.pk,changed['undo_event'])
 assert 'before_encrypted' in AuditEvent.objects.get(pk=changed['undo_event']).details
 assert 'paid' not in AuditEvent.objects.get(pk=changed['undo_event']).details['before_encrypted']

def test_draft_field_references_tenant_and_converted_are_protected(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 draft=create_draft(ctx,'sale',{'warehouse':wh.pk,'lines':[{'product':sp.pk,'quantity':'2'}],'paid':'0'})
 other=Business.objects.create(name='Other',slug='draft-other');foreign=Product.objects.create(business=other,code='x',name='x')
 with pytest.raises((PermissionDenied,ValidationError)):save(ctx,draft.pk,{'lines':[{'product':foreign.pk,'quantity':'1'}]},view(ctx,draft.pk)['version'])
 draft.refresh_from_db();assert draft.data['lines'][0]['product']==sp.pk
 with pytest.raises(PermissionDenied):save(ctx,draft.pk,{'hidden':'value'},view(ctx,draft.pk)['version'])
 draft.state='converted';draft.save(update_fields=['state'])
 with pytest.raises(ValidationError):view(ctx,draft.pk)

def test_timeline_records_actual_print_and_collection_without_scope_leak(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env;block=open_block(post,wh,sp)
 sale=post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'20','sheet_count':'1','unit_price':'100'}],'paid':'0'})
 receipt=post('receipt',{'invoice':sale.pk,'amount':'100','location':wh.location_id,'cash_account':'CASH'})
 AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='document.print',target=str(sale.pk),details={'private':'secret'})
 result=timeline(ctx,sale.pk);assert {'created','posted','receipt','printed'}<={item['kind'] for item in result['results']}
 assert any(item['document']==receipt.pk for item in result['results'])
 assert 'secret' not in str(result)
 member=ctx.membership;member.permissions=['inventory.view'];member.save(update_fields=['permissions'])
 with pytest.raises(PermissionDenied):timeline(Context(ctx.user,ctx.business),sale.pk)

def test_owner_trends_independent_exact_sales_inventory_and_output(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env;block=open_block(post,wh,sp)
 post('sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':sp.pk,'block':block.pk,'thickness_mm':'20','sheet_count':'1','unit_price':'100'}],'paid':'0'})
 result=trends(ctx,{'to':'2026-06-01','days':'7'})
 assert result['sales'][-1]['amount']=='200.00';assert result['inventory'][-1]['amount']=='9800.00'
 assert result['aging']['current']=='200.00';assert result['production']==[]
 with pytest.raises(ValidationError):trends(ctx,{'days':'100000'})
 post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':raw.pk,'quantity':'100','value':'1000'}]})
 post('production',{'warehouse':wh.pk,'inputs':[{'product':raw.pk,'quantity':'10'}],'outputs':[{'product':sp.pk,'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'100'}]}]})
 adhesive=Product.objects.create(business=ctx.business,code='TREND-AD',name='Measured adhesive',kind='finished',unit='kg',line='adhesive')
 post('production',{'warehouse':wh.pk,'inputs':[{'product':raw.pk,'quantity':'5'}],'outputs':[{'product':adhesive.pk,'quantity':'3'}]})
 measured=trends(ctx,{'to':'2026-06-01','days':'7'})['production']
 assert {row['unit'] for row in measured}=={'cm','kg'}
 assert {row['product']:Decimal(row['points'][-1]['quantity']) for row in measured}=={sp.pk:Decimal('10'),adhesive.pk:Decimal('3')}

def test_posted_timeline_links_original_approval_without_disclosing_payload(growth_env):
 from django.contrib.auth.models import User
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 post('opening_cash',{'location':wh.location_id,'amount':'1000','reason':'Reviewed opening'})
 client=client_for(ctx.user,ctx.business)
 requested=client.post('/api/approvals/',{'kind':'expense_post','data':{'date':'2026-06-01','location':wh.location_id,'amount':'100','expense_account':'EXPENSE','notes':'Private approval evidence'}},content_type='application/json')
 assert requested.status_code==201,requested.content
 request_id=requested.json()['document']['id']
 reviewer=User.objects.create_user(username='timeline-reviewer')
 Membership.objects.create(user=reviewer,business=ctx.business,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])
 approved=client_for(reviewer,ctx.business).post(f'/api/approvals/{request_id}/',{},content_type='application/json')
 assert approved.status_code==201,approved.content
 posted=approved.json()['document']['id']
 events=timeline(ctx,posted)['results']
 assert {'approval_requested','approved'}<={event['kind'] for event in events}
 assert any(event['kind']=='approved' and event['document']==request_id for event in events)
 assert any(event['document']==posted for event in timeline(ctx,request_id)['results'])
 assert 'Private approval evidence' not in str(events)

def test_attention_and_bulk_are_scoped_and_atomic(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 draft=create_draft(ctx,'sale',{'warehouse':wh.pk,'lines':[{'product':sp.pk,'quantity':'1'}]})
 assert not any(g['results'] for g in attention(ctx)['groups'] if g['key']!='system')
 client=client_for(ctx.user,ctx.business)
 other=Business.objects.create(name='Foreign',slug='bulk-foreign');p=Product.objects.create(business=other,code='o',name='other')
 result=client.post('/api/catalog-bulk/',{'resource':'products','action':'deactivate','ids':[sp.pk,p.pk]},content_type='application/json');assert result.status_code in (400,403)
 sp.refresh_from_db();assert sp.active
 result=client.post('/api/catalog-bulk/',{'resource':'products','action':'deactivate','ids':[sp.pk]},content_type='application/json');assert result.status_code==200
 sp.refresh_from_db();assert not sp.active and Entry.objects.count()==0

def test_backup_settings_host_boundary_and_write_probe(environment,tmp_path,settings):
 from erp.backup_settings import write_json,operators_path,tag
 user,biz,member,loc,wh,sp=environment;settings.ROOT_DIR=tmp_path
 client=client_for(user,biz);assert client.get('/api/backup-settings/').status_code==403
 write_json(operators_path(),{'databases':{tag():[user.pk]}})
 destination=tmp_path/'external-fixture';destination.mkdir()
 result=client.post('/api/backup-settings/',{'action':'save','destination':str(destination),'interval_hours':12},content_type='application/json');assert result.status_code==200 and result.json()['write_tested']
 assert not list(destination.iterdir())
 assert client.get('/api/backup-settings/').json()['destination']==str(destination.resolve())
 result=client.get('/api/backup-settings/',REMOTE_ADDR='192.168.1.10');assert result.status_code==403
 assert Entry.objects.count()==0
