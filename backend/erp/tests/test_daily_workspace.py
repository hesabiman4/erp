from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import DatabaseError,transaction
from django.test.utils import CaptureQueriesContext
from django.db import connection
from erp.tests.test_api import environment,client_for
from erp.tests.test_growth import growth_env,open_block
from erp.models import *
from erp.core import Context,create_draft,balance
from erp.daily_workspace import workspace,queue,select_persona
from erp.guidance import catalog,save_progress,GUIDES,PASHTO_STEPS


def test_every_authored_lesson_has_real_pashto_copy_without_changing_step_identifiers():
 # Missing bodies previously fell through to Dari even when Pashto was selected.
 assert {guide['id'] for guide in GUIDES}==set(PASHTO_STEPS)
 for guide in GUIDES:
  assert {step[0] for step in guide['steps']}==set(PASHTO_STEPS[guide['id']])
  for step in guide['steps']:
   title,body=PASHTO_STEPS[guide['id']][step[0]]
   assert title and len(body)>40
   assert body not in (step[2],step[4])
 assert '۹۷۸' in PASHTO_STEPS['sales']['measure'][1]
 assert '۱۵۰۰' in PASHTO_STEPS['sales']['collect'][1]
 assert '۵۰۰۰' in PASHTO_STEPS['payroll']['recover'][1]


def test_work_profiles_do_not_grant_permissions_and_preferences_are_actor_scoped(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 user=get_user_model().objects.create_user(username='warehouse-learning')
 m=Membership.objects.create(user=user,business=ctx.business,role='warehouse',permissions=['inventory.view'],all_locations=False,location_ids=[wh.location_id],product_lines=['sponge'])
 limited=Context(user,ctx.business)
 assert [p['id'] for p in workspace(limited)['personas']]==['warehouse','general']
 assert workspace(limited)['actions']==[]
 with pytest.raises(PermissionDenied):select_persona(limited,'owner')
 select_persona(limited,'warehouse');select_persona(ctx,'accountant')
 assert workspace(limited)['persona']=='warehouse' and workspace(ctx)['persona']=='accountant'
 m.permissions=[];m.save();assert workspace(Context(user,ctx.business))['persona']=='general'
 assert Document.objects.count()==0 and Entry.objects.count()==0


def test_learning_is_persistent_versioned_nonfinancial_and_current_permission_scoped(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 before=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
 assert len(catalog(ctx))>=7
 for topic in catalog(ctx):
  assert set(topic['steps_ps'])=={step[0] for step in topic['steps']}
  assert topic['version']==1
 save_progress(ctx,'sales',['measure','price'])
 assert next(t for t in catalog(ctx) if t['id']=='sales')['completed']==['measure','price']
 assert (Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())==before
 with pytest.raises(ValidationError):save_progress(ctx,'sales',['fake'])
 with pytest.raises(ValidationError):save_progress(ctx,'sales',['measure','measure'])
 ctx.membership.permissions=['inventory.view'];ctx.membership.save()
 assert [g['id'] for g in catalog(ctx)]==['warehouse']
 with pytest.raises(PermissionDenied):save_progress(ctx,'payroll',['terms'])
 assert GuideProgress.objects.get().completed==['measure','price']


def test_real_debt_queue_updates_after_collection_and_never_reposts(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 block=open_block(post,wh,sp)
 sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'100','unit_price':'500'}],'paid':'3500'})
 before=(Document.objects.count(),Entry.objects.count())
 rows=queue(ctx,'receivables')['results'];assert len(rows)==1 and rows[0]['balance']==Decimal('1500')
 assert (Document.objects.count(),Entry.objects.count())==before
 post('receipt',{'invoice':sale.id,'location':wh.location_id,'amount':'1500'})
 assert queue(ctx,'receivables')['results']==[]


def test_work_queue_filters_locations_mixed_lines_and_revoked_sources(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 block=open_block(post,wh,sp)
 sale=post('sale',{'warehouse':wh.id,'party':customer.id,'lines':[{'product':sp.id,'block':block.id,'thickness_mm':'100','unit_price':'500'}]})
 other=Location.objects.create(business=ctx.business,code='OTHER',name='Other')
 ctx.membership.all_locations=False;ctx.membership.location_ids=[other.id];ctx.membership.permissions=['sales.view'];ctx.membership.save()
 assert not queue(ctx,'receivables')['results']
 with pytest.raises(PermissionDenied):queue(ctx,'receivables',wh.location_id)
 ctx.membership.all_locations=True;ctx.membership.product_lines=['adhesive'];ctx.membership.save()
 assert not queue(ctx,'receivables')['results']
 ctx.membership.permissions=[];ctx.membership.save()
 with pytest.raises(PermissionDenied):queue(ctx,'receivables')


def test_workspace_api_and_learning_identity_are_business_safe(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 client=client_for(ctx.user,ctx.business)
 assert client.get('/api/workspace/',HTTP_X_BUSINESS_ID=str(ctx.business.id)).status_code==200
 response=client.patch('/api/guidance/',{'topic':'sales','completed':['measure']},content_type='application/json',HTTP_X_BUSINESS_ID=str(ctx.business.id));assert response.status_code==200,response.content
 other=Business.objects.create(name='Other workspace',slug='learning-other')
 with pytest.raises(DatabaseError),transaction.atomic():GuideProgress.objects.filter().update(business=other)
 assert GuideProgress.objects.get().business_id==ctx.business.id


def test_bounded_queue_cursor_and_query_work_do_not_expand_with_history(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 # Real ordinary draft documents, intentionally no stock/GL fixtures or fake
 # posted sales. Query work remains bounded even with a larger draft history.
 for i in range(95):create_draft(ctx,'sale',{'warehouse':wh.id,'lines':[]},f'learning-draft-{i}')
 with CaptureQueriesContext(connection) as captured:page=queue(ctx,'drafts')
 assert len(page['results'])==6 and page['next_cursor']
 next_page=queue(ctx,'drafts',before=page['next_cursor'])
 assert not {r['id'] for r in page['results']}&{r['id'] for r in next_page['results']}
 assert len(captured)<110,len(captured)
 assert Entry.objects.count()==0 and StockMovement.objects.count()==0


def test_shared_draft_service_has_exact_idempotency_and_no_financial_effect(growth_env):
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 draft=create_draft(ctx,'expense_post',{'location':wh.location_id,'amount':'100','expense_account':'EXPENSE'},'reviewed-expense-key')
 repeated=create_draft(ctx,'expense_post',draft.data,'reviewed-expense-key')
 assert repeated.pk==draft.pk and repeated._draft_replayed and draft.state=='draft'
 with pytest.raises(ValidationError):create_draft(ctx,'expense_post',{'amount':'200'},'reviewed-expense-key')
 assert Entry.objects.count()==0


def test_inventory_reconciliation_groups_history_without_per_pool_queries(growth_env):
 from erp.reports import report
 ctx,post,wh,sp,raw,customer,supplier=growth_env
 products=[Product.objects.create(business=ctx.business,code=f'PERF-{i}',name=f'Performance item{i}',unit='each',line='shared') for i in range(20)]
 post('stock_opening',{'warehouse':wh.pk,'lines':[{'product':p.pk,'quantity':'10','value':'30'} for p in products]})
 with CaptureQueriesContext(connection) as captured:result=report(ctx,'inventory_reconciliation',{'to':'2026-06-01'})
 assert result['totals']['difference']=='0.00' and result['totals']['stock_cost']=='600.00'
 assert len(result['rows'])==20 and all(r['quantity']=='10.000000' for r in result['rows'])
 assert len(captured)<=10,len(captured)
