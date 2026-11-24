from decimal import Decimal
import json
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client
from erp.core import Context, execute, outstanding
from erp.counter_sales import availability, repeat_sale, configure, shortcuts
from erp.models import Membership, Business, Product, Document, AuditEvent, Block
from erp.tests.test_manufacturing import Factory


class CounterSalesTests(Factory, TestCase):
    def ctx(self): return Context(self.user,self.business)

    def test_piece_filter_respects_actual_footprints_and_unreserved_height(self):
        small=self.open_block(height='100',length='1000',width='1000');large=self.open_block(height='1000')
        self.post('reserve',lines=[{'block':large.id,'thickness_mm':'22','sheet_count':'2'}])
        data=availability(self.ctx(),{'warehouse':self.store.id,'product':self.sponge.id,'thickness_mm':'220','sheet_count':'1'})
        self.assertEqual([b['id'] for b in data['blocks']],[large.id]);self.assertIsNone(data['available_quantity'])
        self.assertEqual(data['blocks'][0]['available_height_mm'],Decimal('956'))
        only_small=availability(self.ctx(),{'warehouse':self.store.id,'product':self.sponge.id,'profile':small.profile})
        self.assertEqual([b['id'] for b in only_small['blocks']],[small.id])
        self.assertNotIn('cost',str(data));self.assertNotIn('value',str(data))

    def test_nonblock_available_quantity_and_held_stock_are_honest(self):
        self.post('stock_opening',warehouse=self.store.id,lines=[{'product':self.adhesive.id,'quantity':'15.25','value':'1500'}])
        self.assertEqual(availability(self.ctx(),{'warehouse':self.store.id,'product':self.adhesive.id})['available_quantity'],Decimal('15.25'))
        block=self.open_block();block.status='hold';block.save(update_fields=['status'])
        self.business.settings={'require_inspection':True};self.business.save(update_fields=['settings'])
        preview=availability(self.ctx(),{'warehouse':self.store.id,'product':self.sponge.id})
        self.assertEqual(preview['blocks'],[]);self.assertTrue(preview['inspection_required']);self.assertFalse(preview['inspection_verified_by_preview'])
        with self.assertRaises(ValidationError):availability(self.ctx(),{'warehouse':self.store.id,'product':self.raw.id})

    def test_active_recall_excludes_pooled_product_availability(self):
        self.open_material()
        produced=self.post('production',warehouse=self.store.id,inputs=[{'product':self.raw.id,'quantity':'5'}],outputs=[{'product':self.adhesive.id,'quantity':'5'}])
        self.post('quality_recall',batch=produced.id,reason='Confirmed QA containment')
        result=availability(self.ctx(),{'warehouse':self.store.id,'product':self.adhesive.id})
        self.assertTrue(result['held']);self.assertEqual(result['available_quantity'],'0');self.assertEqual(result['blocks'],[])

    def test_repeat_is_nonfinancial_clears_stock_payment_order_and_uses_current_price(self):
        block=self.open_block();invoice=self.post('sale',warehouse=self.store.id,party=self.customer.id,paid='500',lines=[{'product':self.sponge.id,'block':block.id,'thickness_mm':'22','unit_price':'500'}])
        before=Document.objects.count();old_remaining=Block.objects.get(pk=block.id).remaining_height_mm
        self.sponge.price='600';self.sponge.save(update_fields=['price'])
        data=repeat_sale(self.ctx(),invoice.id)
        self.assertEqual(data['party'],self.customer.id);self.assertEqual(data['paid'],'0');self.assertIsNone(data['order'])
        self.assertEqual(data['lines'][0]['block'],'');self.assertEqual(data['lines'][0]['unit_price'],Decimal('600'))
        self.assertEqual(data['lines'][0]['thickness_mm'],'22');self.assertEqual(data['lines'][0]['source_profile'],block.profile)
        self.assertEqual(Document.objects.count(),before);self.assertEqual(Block.objects.get(pk=block.id).remaining_height_mm,old_remaining)
        self.assertEqual(outstanding(invoice),Decimal('600'))

    def test_repeat_rechecks_original_location_line_and_permission(self):
        block=self.open_block();invoice=self.post('sale',warehouse=self.store.id,party=self.customer.id,lines=[{'product':self.sponge.id,'block':block.id,'thickness_mm':'22'}])
        member=Membership.objects.get(user=self.user,business=self.business);member.permissions=['sales.post'];member.save()
        with self.assertRaises(PermissionDenied):repeat_sale(self.ctx(),invoice.id)
        member.permissions=['sales.post','sales.view'];member.product_lines=['adhesive'];member.save()
        with self.assertRaises(PermissionDenied):repeat_sale(self.ctx(),invoice.id)
        member.product_lines=['sponge'];member.all_locations=False;member.location_ids=[self.kabul.id];member.save()
        with self.assertRaises(PermissionDenied):repeat_sale(self.ctx(),invoice.id)

    def test_availability_rejects_cross_business_and_bounded_invalid_queries(self):
        other=Business.objects.create(name='Other',slug='counter-other');product=Product.objects.create(business=other,code='OTHER',name='Other product')
        with self.assertRaises(ValidationError):availability(self.ctx(),{'warehouse':self.store.id,'product':product.id})
        for query in [{'offset':'-1'},{'offset':'1000001'},{'thickness_mm':'-22'},{'thickness_mm':'22','sheet_count':'1.5'},{'thickness_mm':'22','cutting_loss_mm':'-1'}]:
            with self.assertRaises(ValidationError):availability(self.ctx(),{'warehouse':self.store.id,'product':self.sponge.id,**query})

    def test_scanner_text_checks_original_qr_identity_business_and_selected_product(self):
        block=self.open_block()
        label={'type':'erp-block','version':1,'business':self.business.id,'block':block.id,'code':block.code}
        for code in [json.dumps(label),f'/api/blocks/{block.id}/label/']:
            data=availability(self.ctx(),{'warehouse':self.store.id,'product':self.sponge.id,'code':code})
            self.assertEqual([row['id'] for row in data['blocks']],[block.id])
        for changed in [{'business':True},{'business':self.business.id+100},{'code':'forged-code'},{'version':2}]:
            with self.assertRaises(ValidationError):availability(self.ctx(),{'warehouse':self.store.id,'product':self.sponge.id,'code':json.dumps({**label,**changed})})
        with self.assertRaises(ValidationError):availability(self.ctx(),{'warehouse':self.store.id,'product':self.adhesive.id,'code':json.dumps(label)})

    def test_shortcuts_are_validated_business_configuration_with_audit(self):
        self.business.settings={'private_policy':'preserved'};self.business.save()
        self.assertEqual(configure(self.ctx(),{'thickness_mm':['۲۲','50']})['thickness_mm'],['22','50'])
        self.business.refresh_from_db();self.assertEqual(self.business.settings['private_policy'],'preserved')
        self.assertEqual(shortcuts(self.ctx()),['22','50']);self.assertEqual(AuditEvent.objects.filter(action='counter.thickness_shortcuts').count(),1)
        for values in [['22','۲۲'],['0'],['1.0001'],[22.5],None,list(map(str,range(1,14)))]:
            with self.assertRaises(ValidationError):configure(self.ctx(),{'thickness_mm':values})
        member=Membership.objects.get(user=self.user,business=self.business);member.permissions=['sales.post'];member.save()
        with self.assertRaises(PermissionDenied):configure(self.ctx(),{'thickness_mm':['22']})

    def test_counter_flow_posts_exact_existing_sale_with_partial_cash_and_idempotency(self):
        block=self.open_block();client=Client();client.force_login(self.user);client.defaults['HTTP_X_BUSINESS_ID']=str(self.business.id)
        response=client.get(f'/api/counter/availability/?warehouse={self.store.id}&product={self.sponge.id}&thickness_mm=22')
        self.assertEqual(response.status_code,200,response.content);self.assertNotIn('cost',response.json())
        payload={'date':'2026-10-28','warehouse':self.store.id,'party':self.customer.id,'paid':'500','lines':[{'product':self.sponge.id,'block':block.id,'thickness_mm':'22','sheet_count':'1','unit_price':'500'}]}
        for _ in range(2):
            response=client.post('/api/operations/sale/',payload,content_type='application/json',HTTP_IDEMPOTENCY_KEY='counter-partial-once')
            self.assertEqual(response.status_code,201,response.content)
        invoice=Document.objects.get(kind='sale');self.assertEqual(invoice.amount,Decimal('1100'));self.assertEqual(outstanding(invoice),Decimal('600'))
        self.assertEqual(invoice.result['lines'][0]['quantity'],'2.2');self.assertEqual(Block.objects.get(pk=block.id).remaining_height_mm,Decimal('978'))
        self.assert_journal_balanced(invoice)
        location_mismatch=client.get(f'/api/counter/availability/?warehouse={self.store.id}&product={self.sponge.id}',HTTP_X_LOCATION_ID=str(self.kabul.id))
        self.assertEqual(location_mismatch.status_code,400)
