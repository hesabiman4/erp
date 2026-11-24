from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import DatabaseError,connections,transaction
from django.test import TestCase,TransactionTestCase
from erp.core import Context,D,balance,execute
from erp.models import Business,Block,CutPlan,Document,Membership,Party,OrderCutDemand,OrderCutSheet
from erp.order_cutting import preview,reserved_quantity,workspace_data
from erp.tests.test_manufacturing import Factory


class OrderCuttingTests(Factory,TestCase):
    def order(self,quantity='4.4',party=None,warehouse=None):
        return self.post('sales_order',party=(party or self.customer).id,warehouse=(warehouse or self.store).id,lines=[{'product':self.sponge.id,'quantity':quantity,'unit_price':'500','length_mm':'2000','width_mm':'1000'}])

    def plan(self,order,count=2,thickness='22',**extra):
        return self.post('cut_plan',warehouse=self.store.id,product=self.sponge.id,profile='2000.000x1000.000',lines=[{'order':order.id,'order_index':0,'thickness_mm':thickness,'sheet_count':count}],**extra)

    def sell_sheet(self,sheet,**extra):
        return self.post('sale',warehouse=self.store.id,lines=[{'product':self.sponge.id,'block':sheet.block_id,'thickness_mm':str(sheet.demand.thickness_mm),'sheet_count':1}],**extra)

    def test_multiple_customer_demands_reserve_across_blocks_then_invoice_identified_sheets_once(self):
        first=self.open_block(height='30',value='300');second=self.open_block(height='50',value='500')
        another=Party.objects.create(business=self.business,kind='customer',name='Second customer')
        a=self.order('4.4');b=self.order('2.2',party=another)
        initial=balance(Context(self.user,self.business),'FG')
        plan=self.post('cut_plan',warehouse=self.store.id,product=self.sponge.id,profile=first.profile,cutting_loss_mm='1',lines=[{'order':a.id,'order_index':0,'thickness_mm':'22','sheet_count':2},{'order':b.id,'order_index':0,'thickness_mm':'22','sheet_count':1}])
        self.assertFalse(plan.entries.exists());self.assertFalse(plan.movements.exists())
        self.assertEqual(OrderCutDemand.objects.count(),2)
        self.assertEqual(reserved_quantity(Context(self.user,self.business),a.id,0),D('4.4'))
        first.refresh_from_db();second.refresh_from_db()
        self.assertEqual(first.reserved_height_mm+second.reserved_height_mm,D('69'))
        done=self.post('cut_execute',plan=plan.result['plan'])
        self.assertEqual(len(done.result['blocks']),3)
        self.assertEqual(balance(Context(self.user,self.business),'FG'),initial)
        self.assertEqual(balance(Context(self.user,self.business),'SALES'),D('0'))
        held=list(OrderCutSheet.objects.select_related('demand').order_by('id'))
        for piece in held:
            self.assertEqual(piece.block.reserved_height_mm,D('22'))
            self.assertEqual(piece.block.remaining_height_mm,D('22'))
        parent_heights={piece.id:piece.remaining_height_mm for piece in Block.objects.filter(pk__in=[first.id,second.id])}
        sold=next(piece for piece in held if piece.demand.order_id==a.id)
        invoice=self.sell_sheet(sold,paid='500')
        self.assertEqual(invoice.result['order'],a.id);self.assertEqual(invoice.party_id,self.customer.id)
        self.assertEqual(invoice.result['lines'][0]['order_index'],0)
        self.assertEqual(invoice.amount,D('1100'))
        self.assertEqual({piece.id:piece.remaining_height_mm for piece in Block.objects.filter(pk__in=parent_heights)},parent_heights)
        sold.refresh_from_db();sold.block.refresh_from_db()
        self.assertEqual(sold.fulfilled_document_id,invoice.id);self.assertEqual(sold.block.remaining_height_mm,D('0'));self.assertEqual(sold.block.reserved_height_mm,D('0'))
        self.assertEqual(reserved_quantity(Context(self.user,self.business),a.id,0),D('2.2'))
        self.assert_journal_balanced(invoice)
        with self.assertRaises(ValidationError):self.sell_sheet(sold)

    def test_demand_cannot_be_reserved_twice_or_delivered_from_unallocated_stock(self):
        block=self.open_block();order=self.order('4.4');plan=self.plan(order)
        before=Document.objects.count()
        with self.assertRaises(ValidationError):self.plan(order,count=1)
        with self.assertRaisesMessage(ValidationError,'reserved for a cutting plan'):self.post('sale',warehouse=self.store.id,party=self.customer.id,order=order.id,lines=[{'product':self.sponge.id,'block':block.id,'thickness_mm':'22'}])
        self.assertEqual(Document.objects.count(),before)
        block.refresh_from_db();self.assertEqual(block.remaining_height_mm,D('1000'))
        self.post('cut_execute',plan=plan.result['plan'],cancel=True,reason='Customer changed requested size')
        self.assertEqual(reserved_quantity(Context(self.user,self.business),order.id,0),D('0'))
        block.refresh_from_db();self.assertEqual(block.reserved_height_mm,D('0'))
        self.plan(order,count=1)

    def test_closed_order_blocks_execution_but_planned_and_cut_reservations_can_be_released(self):
        block=self.open_block();quote=self.post('quotation',party=self.customer.id,warehouse=self.store.id,lines=[{'product':self.sponge.id,'quantity':'4.4','length_mm':'2000','width_mm':'1000'}])
        order=self.post('sales_order',quotation=quote.id,party=self.customer.id,warehouse=self.store.id,lines=[{'product':self.sponge.id,'quantity':'4.4','length_mm':'2000','width_mm':'1000'}])
        plan=self.plan(order)
        self.post('order_cancel',order=quote.id,reason='Demand closed before cutting')
        with self.assertRaises(ValidationError):self.post('cut_execute',plan=plan.result['plan'])
        self.post('cut_execute',plan=plan.result['plan'],cancel=True,reason='Release closed order')
        block.refresh_from_db();self.assertEqual(block.remaining_height_mm,D('1000'));self.assertEqual(block.reserved_height_mm,D('0'))
        second=self.order();secondplan=self.plan(second);self.post('cut_execute',plan=secondplan.result['plan'])
        sheets=list(OrderCutSheet.objects.filter(demand__order=second).select_related('demand','block'))
        self.post('order_cancel',order=second.id,reason='Closed after physical cutting')
        with self.assertRaises(ValidationError):self.sell_sheet(sheets[0])
        released=self.post('cut_execute',plan=secondplan.result['plan'],cancel=True,reason='Return unsold sheets to free inventory')
        self.assertFalse(released.entries.exists());self.assertFalse(released.movements.exists())
        self.assertEqual(set(released.result['released_blocks']),{piece.block_id for piece in sheets})
        for piece in sheets:piece.refresh_from_db();piece.block.refresh_from_db();self.assertEqual(piece.released_by_id,released.id);self.assertEqual(piece.block.reserved_height_mm,D('0'))
        free=self.sell_sheet(sheets[0],party=self.customer.id)
        self.assertIsNone(free.result['order'])

    def test_wrong_customer_partial_sheet_and_mixed_order_invoice_are_atomic_failures(self):
        self.open_block();another=Party.objects.create(business=self.business,name='Other buyer',kind='customer')
        a=self.order('2.2');b=self.order('2.2',party=another)
        plan=self.post('cut_plan',warehouse=self.store.id,product=self.sponge.id,profile='2000.000x1000.000',lines=[{'order':order.id,'thickness_mm':'22','sheet_count':1} for order in [a,b]])
        self.post('cut_execute',plan=plan.result['plan']);sheets=list(OrderCutSheet.objects.select_related('demand').order_by('id'))
        with self.assertRaises(ValidationError):self.sell_sheet(sheets[0],party=another.id)
        with self.assertRaises(ValidationError):self.post('sale',warehouse=self.store.id,lines=[{'product':self.sponge.id,'block':sheets[0].block_id,'thickness_mm':'11'}])
        with self.assertRaises(ValidationError):self.post('sale',warehouse=self.store.id,lines=[{'product':self.sponge.id,'block':piece.block_id,'thickness_mm':'22'} for piece in sheets])
        for piece in sheets:piece.refresh_from_db();piece.block.refresh_from_db();self.assertIsNone(piece.fulfilled_document_id);self.assertEqual(piece.block.reserved_height_mm,D('22'))

    def test_preview_is_read_only_rechecks_current_demand_and_rejects_unfeasible_geometry(self):
        block=self.open_block(height='30');order=self.order()
        payload={'warehouse':self.store.id,'product':self.sponge.id,'profile':block.profile,'lines':[{'order':order.id,'thickness_mm':'22','sheet_count':1}]}
        count=Document.objects.count();result=preview(Context(self.user,self.business),payload)
        self.assertEqual(result['demands'][0]['order'],order.id);self.assertEqual(Document.objects.count(),count)
        block.refresh_from_db();self.assertEqual(block.reserved_height_mm,D('0'))
        self.plan(order,count=1)
        with self.assertRaises(ValidationError):preview(Context(self.user,self.business),payload)
        with self.assertRaises(ValidationError):preview(Context(self.user,self.business),{**payload,'lines':[{'order':order.id,'thickness_mm':'22.0001'}]})
        with self.assertRaises(ValidationError):preview(Context(self.user,self.business),{**payload,'lines':[{'order':order.id,'thickness_mm':'22','sheet_count':'1.5'}]})
        with self.assertRaises(ValidationError):preview(Context(self.user,self.business),{**payload,'warehouse':self.branch.id})

    def test_data_and_actions_enforce_business_location_product_and_source_permissions(self):
        self.open_block();order=self.order();plan=self.plan(order)
        member=Membership.objects.get(user=self.user,business=self.business)
        member.permissions=['inventory.view','inventory.plan','inventory.post','sales.post'];member.all_locations=False;member.location_ids=[self.kabul.id];member.save()
        self.assertEqual(workspace_data(Context(self.user,self.business))['orders'],[])
        with self.assertRaises(PermissionDenied):self.post('cut_execute',plan=plan.result['plan'])
        member.all_locations=True;member.product_lines=['adhesive'];member.save()
        with self.assertRaises(PermissionDenied):self.plan(order)
        member.product_lines=['sponge','adhesive','shared'];member.permissions=['inventory.view'];member.save()
        payload={'warehouse':self.store.id,'product':self.sponge.id,'profile':'2000.000x1000.000','lines':[{'order':order.id,'thickness_mm':'22'}]}
        with self.assertRaises(PermissionDenied):preview(Context(self.user,self.business),payload)
        other=Business.objects.create(name='Other company',slug='other-cutting')
        Membership.objects.create(user=self.user,business=other,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])
        with self.assertRaises(ValidationError):execute(Context(self.user,other),'cut_execute',{'plan':plan.result['plan']},'cross-company-cut')

    def test_held_sheet_history_and_plan_dimensions_are_database_protected(self):
        self.open_block();order=self.order();plan=self.plan(order);self.post('cut_execute',plan=plan.result['plan'])
        demand=OrderCutDemand.objects.get(plan_id=plan.result['plan']);sheet=OrderCutSheet.objects.filter(demand=demand).first()
        for model,identifier,changes in [(OrderCutDemand,demand.id,{'quantity_cm':'999'}),(OrderCutSheet,sheet.id,{'quantity_cm':'999'}),(CutPlan,plan.result['plan'],{'allocations':[]}),(OrderCutDemand,demand.id,{'state':'planned'})]:
            with self.assertRaises(DatabaseError),transaction.atomic():model.objects.filter(pk=identifier).update(**changes)
        with self.assertRaises(DatabaseError),transaction.atomic():OrderCutSheet.objects.filter(pk=sheet.id).delete()
        sale=self.sell_sheet(sheet)
        with self.assertRaises(DatabaseError),transaction.atomic():OrderCutSheet.objects.filter(pk=sheet.id).update(fulfilled_document=None)
        self.assertEqual(OrderCutSheet.objects.get(pk=sheet.id).fulfilled_document_id,sale.id)

    def test_partial_release_preserves_other_customer_hold_and_prior_invoice(self):
        self.open_block();other=Party.objects.create(business=self.business,name='Another buyer',kind='customer');a=self.order();b=self.order(party=other)
        plan=self.post('cut_plan',warehouse=self.store.id,product=self.sponge.id,profile='2000.000x1000.000',lines=[{'order':source.id,'thickness_mm':'22','sheet_count':2} for source in [a,b]])
        self.post('cut_execute',plan=plan.result['plan']);sold=OrderCutSheet.objects.select_related('demand').filter(demand__order=a).first();invoice=self.sell_sheet(sold)
        released=self.post('cut_execute',plan=plan.result['plan'],cancel=True,release_order=a.id,reason='Release customer A remainder only')
        self.assertEqual(len(released.result['released_blocks']),1)
        self.assertEqual(reserved_quantity(Context(self.user,self.business),a.id,0),D('0'))
        self.assertEqual(reserved_quantity(Context(self.user,self.business),b.id,0),D('4.4'))
        sold.refresh_from_db();self.assertEqual(sold.fulfilled_document_id,invoice.id);self.assertIsNone(sold.released_by_id)


class ConcurrentOrderCuttingTests(Factory,TransactionTestCase):
    reset_sequences=True
    def test_two_planners_cannot_reserve_the_same_customer_demand(self):
        self.open_block();order=self.post('sales_order',warehouse=self.store.id,party=self.customer.id,lines=[{'product':self.sponge.id,'quantity':'2.2'}]);barrier=Barrier(2)
        def compete(key):
            try:
                user=get_user_model().objects.get(pk=self.user.pk);business=Business.objects.get(pk=self.business.pk);barrier.wait(timeout=15)
                execute(Context(user,business),'cut_plan',{'date':'2026-10-28','warehouse':self.store.id,'product':self.sponge.id,'profile':'2000.000x1000.000','lines':[{'order':order.id,'thickness_mm':'22'}]},key)
                return 'planned'
            except ValidationError:return 'already-reserved'
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(compete,['planner-a','planner-b']))
        self.assertCountEqual(result,['planned','already-reserved']);self.assertEqual(OrderCutDemand.objects.count(),1)
