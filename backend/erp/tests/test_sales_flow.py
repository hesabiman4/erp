from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client
from erp.core import Context, execute, outstanding
from erp.models import Business, Document, Membership
from erp.tests.test_manufacturing import Factory


class SalesFlowTests(Factory, TestCase):
    def draft_quote(self):
        client=Client();client.force_login(self.user);client.defaults['HTTP_X_BUSINESS_ID']=str(self.business.id)
        payload={'date':'2026-10-28','warehouse':self.store.id,'party':self.customer.id,'notes':'Retain the original quotation proposal','lines':[{'product':self.sponge.id,'quantity':'5','unit_price':'500','length_mm':'2000','width_mm':'1000'}]}
        response=client.post('/api/documents/',{'kind':'quotation','data':payload},content_type='application/json')
        self.assertEqual(response.status_code,201,response.content)
        return Document.objects.get(pk=response.json()['id']),client,payload

    def quote(self, **changes):
        return self.post('quotation', warehouse=self.store.id, party=self.customer.id, lines=[{'product': self.sponge.id, 'quantity': '5', 'length_mm': '2000', 'width_mm': '1000', **changes}])

    def order(self, quote, **changes):
        return self.post('sales_order', warehouse=self.store.id, party=self.customer.id, quotation=quote.id, lines=[{'product': self.sponge.id, 'quantity': '5', 'length_mm': '2000', 'width_mm': '1000', **changes}])

    def data(self, doc):
        client = Client(); client.force_login(self.user)
        response = client.get(f'/api/documents/{doc.id}/', HTTP_X_BUSINESS_ID=str(self.business.id))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_partial_conversion_maps_lines_and_prevents_duplicate_or_wrong_size_orders(self):
        quote = self.quote()
        first = self.order(quote, quantity='2')
        self.assertEqual(first.result['lines'][0]['quotation_index'], 0)
        self.assertEqual(first.result['lines'][0]['length_mm'], '2000')
        self.assertFalse(first.entries.exists()); self.assertFalse(first.movements.exists())
        with self.assertRaises(ValidationError): self.order(quote, quantity='4')
        with self.assertRaises(ValidationError): self.order(quote, quantity='1', width_mm='500')
        second = self.order(quote, quantity='3')
        self.assertEqual(self.data(quote)['sales_flow']['status'], 'ordered')
        with self.assertRaises(ValidationError): self.order(quote, quantity='1')
        self.assertEqual(Document.objects.filter(kind='sales_order').count(), 2)
        self.assertFalse(second.entries.exists())

    def test_quote_cancel_at_invoice_stage_stops_only_unfinished_work_preserving_books(self):
        block = self.open_block(); quote = self.quote(); order = self.order(quote)
        invoice = self.post('sale', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '22'}])
        receipt = self.post('receipt', invoice=invoice.id, location=self.location.id, amount='500', cash_account='CASH')
        original = self.data(invoice); balance = outstanding(invoice)
        close = self.post('order_cancel', order=quote.id, reason='Customer closed the remaining work')
        self.assertEqual(close.product_lines, ['sponge'])
        self.assertTrue(close.result['linked_orders_stopped'])
        self.assertFalse(close.entries.exists()); self.assertFalse(close.movements.exists())
        with self.assertRaises(ValidationError): self.order(quote, quantity='1')
        with self.assertRaises(ValidationError): self.post('sale', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '28'}])
        self.assertEqual(outstanding(invoice), balance)
        self.assertEqual(self.data(invoice)['result'], original['result'])
        self.assertEqual(self.data(order)['sales_flow']['status'], 'cancelled')
        block.refresh_from_db(); self.assertEqual(block.remaining_height_mm, Decimal('978'))
        self.assert_journal_balanced(invoice); self.assert_journal_balanced(receipt)
        with self.assertRaises(ValidationError): self.post('order_cancel', order=quote.id, reason='Repeated')
        member=Membership.objects.get(user=self.user,business=self.business);member.permissions=['sales.view'];member.save()
        readonly=self.data(quote)['sales_flow']
        self.assertEqual(readonly['status'],'cancelled');self.assertIsNone(readonly['closure'])
        self.assertNotIn(close.id,[row['id'] for row in readonly['related']])

    def test_source_prices_can_flow_without_granting_arbitrary_price_override(self):
        block = self.open_block(); quote = self.quote(unit_price='450')
        membership = Membership.objects.get(user=self.user, business=self.business)
        membership.permissions = ['sales.post', 'sales.credit']; membership.approval_limit = Decimal('1000000'); membership.save()
        order = self.order(quote, unit_price='450')
        invoice = self.post('sale', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '22', 'unit_price': '450'}])
        self.assertEqual(invoice.amount, Decimal('990'))
        with self.assertRaises(PermissionDenied): self.order(quote, quantity='1', unit_price='440')
        with self.assertRaises(PermissionDenied): self.post('sale', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '22', 'unit_price': '440'}])
        block.refresh_from_db(); self.assertEqual(block.remaining_height_mm, Decimal('978'))

    def test_linked_flow_tracks_remaining_and_receipts_without_duplicate_revenue(self):
        block = self.open_block(); quote = self.quote(); order = self.order(quote)
        invoice = self.post('sale', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '22'}], paid='100')
        order_flow = self.data(order)['sales_flow']
        self.assertEqual(order_flow['status'], 'partial')
        self.assertEqual(Decimal(order_flow['lines'][0]['remaining_quantity']), Decimal('2.8'))
        payment = self.post('receipt', invoice=invoice.id, location=self.location.id, amount='1000', cash_account='CASH')
        flow = self.data(invoice)['sales_flow']
        self.assertEqual(flow['status'], 'paid')
        self.assertIn(payment.id, [row['id'] for row in flow['related']])
        self.assertEqual(outstanding(invoice), Decimal('0'))
        self.assertFalse(payment.entries.filter(account__code='SALES').exists())
        quote.refresh_from_db(); self.assertEqual(quote.result['status'], 'open')

    def test_cross_business_cancel_and_hidden_linked_documents_are_denied_or_omitted(self):
        quote = self.quote(); order = self.order(quote)
        block = self.open_block()
        invoice = self.post('sale', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '22'}])
        payment = self.post('receipt', location=self.kabul.id, invoice=invoice.id, amount='100', cash_account='CASH')
        # Use a separate business to verify source IDs cannot cross the boundary.
        other = Business.objects.create(name='Other private business', slug='other-private')
        Membership.objects.create(user=self.user, business=other, permissions=['*'], all_locations=True, product_lines=['sponge','adhesive','shared'])
        with self.assertRaises(ValidationError): execute(Context(self.user, other), 'order_cancel', {'order': quote.id, 'reason': 'Wrong business'}, 'wrong-business-close')
        membership = Membership.objects.get(user=self.user, business=self.business)
        membership.permissions = ['sales.view', 'finance.view']; membership.product_lines = ['sponge']; membership.all_locations = False; membership.location_ids = [self.location.id]; membership.save()
        flow = self.data(order)['sales_flow']
        self.assertIn(invoice.id, [row['id'] for row in flow['related']])
        invoice_flow = self.data(invoice)['sales_flow']
        self.assertNotIn(payment.id, [row['id'] for row in invoice_flow['related']])
        with self.assertRaises(PermissionDenied): self.post('order_cancel', order=quote.id, reason='Read only')

    def test_invalid_source_index_and_backdated_cancellation_roll_back(self):
        block = self.open_block(); quote = self.quote(); order = self.order(quote)
        before = Document.objects.count()
        with self.assertRaises(ValidationError): self.order(quote, quotation_index='0.5')
        with self.assertRaises(ValidationError): self.post('sale', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '22', 'order_index':'not-an-index'}])
        self.assertEqual(Document.objects.count(), before)
        self.post('sale', date='2026-10-29', warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{'product': self.sponge.id, 'block': block.id, 'thickness_mm': '22'}])
        with self.assertRaises(ValidationError): self.post('order_cancel', date='2026-10-28', order=quote.id, reason='Before the delivered sale')
        with self.assertRaises(ValidationError): self.post('order_cancel', date='2026-10-29', order=quote.id, reason='   ')
        with self.assertRaises(ValidationError): self.post('order_cancel', date='2026-10-29', order=quote.id, reason=None)

    def test_quote_closure_stops_new_work_but_existing_costed_wip_can_be_completed(self):
        self.open_material(quantity='20', value='2000')
        quote = self.quote(); order = self.order(quote)
        center = self.post('work_center', name='Sales-linked production', location=self.location.id, daily_minutes=480)
        payload = {'work_center': center.result['work_center'], 'warehouse': self.store.id, 'product': self.sponge.id, 'planned_quantity': '5', 'scheduled_date': '2026-10-28', 'planned_minutes': 120, 'order': order.id}
        work = self.post('work_order', **payload)
        batch = self.post('production_start', warehouse=self.store.id, work_order=work.result['work_order'])
        self.post('production_consume', batch=batch.id, inputs=[{'product': self.raw.id, 'quantity': '10'}])
        self.post('order_cancel', order=quote.id, reason='Customer closed remainder after mixing started')
        with self.assertRaises(ValidationError): self.post('work_order', **payload)
        with self.assertRaises(ValidationError): self.post('job_card', work_order=work.result['work_order'], operation='Start another task', minutes=10)
        with self.assertRaises(ValidationError): self.post('production_start', warehouse=self.store.id, work_order=work.result['work_order'])
        with self.assertRaisesMessage(ValidationError, 'New linked production is blocked'): self.post('production_consume', batch=batch.id, inputs=[{'product': self.raw.id, 'quantity': '1'}])
        self.post('work_close', work_order=work.result['work_order'], state='cancelled', reason='Closed commercial demand; retain costed WIP')
        completed = self.post('production_complete', batch=batch.id, outputs=[{'product': self.sponge.id, 'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'50'}]}])
        self.assertEqual(completed.result['work_order'], work.result['work_order'])
        self.assertEqual(Decimal(completed.result['wip_remaining']), Decimal('0'))
        self.assertFalse(completed.entries.filter(account__code='SALES').exists())
        from erp.models import WorkOrder
        self.assertEqual(WorkOrder.objects.get(pk=work.result['work_order']).state, 'cancelled')
        self.assert_journal_balanced(completed)

    def test_legacy_hidden_child_conversion_does_not_leak_progress_or_allow_cascade(self):
        from django.utils import timezone
        quote=self.quote()
        # Reproduce a nonfinancial legacy conversion accepted before warehouse
        # equality was enforced. New source conversions cannot create this.
        child=Document.objects.create(business=self.business,kind='sales_order',number='LEGACY-KABUL-ORDER',state='posted',date=quote.date,warehouse=self.branch,location=self.kabul,party=self.customer,reference=quote,amount='1000',data={},result={'lines':[{**quote.result['lines'][0],'quantity':'2','quotation_index':0}],'status':'open'},product_lines=['sponge'],idempotency_key='legacy-hidden-order',request_hash='legacy',created_by=self.user,posted_at=timezone.now())
        member=Membership.objects.get(user=self.user,business=self.business)
        member.permissions=['sales.view','sales.post','documents.cancel'];member.approval_limit=Decimal('1000000');member.all_locations=False;member.location_ids=[self.location.id];member.save()
        flow=self.data(quote)['sales_flow']
        self.assertEqual(flow['status'],'restricted');self.assertEqual(flow['lines'],[])
        self.assertFalse(flow['can_continue']);self.assertFalse(flow['can_cancel'])
        self.assertNotIn(child.id,[row['id'] for row in flow['related']])
        with self.assertRaises(PermissionDenied):self.post('order_cancel',order=quote.id,reason='Cannot close hidden branch work')

    def test_draft_quote_closure_preserves_proposal_and_cannot_post_edit_or_convert(self):
        from erp.models import AuditEvent
        quote,client,payload=self.draft_quote()
        self.assertTrue(self.data(quote)['sales_flow']['can_cancel'])
        with self.assertRaises(ValidationError):self.post('order_cancel',date='2026-10-27',order=quote.id,reason='Before the proposal date')
        close=self.post('order_cancel',order=quote.id,reason='Abandoned before approval')
        quote.refresh_from_db()
        self.assertEqual(quote.state,'cancelled');self.assertEqual(quote.data,payload)
        self.assertTrue(close.result['draft_quotation_closed'])
        self.assertFalse(quote.entries.exists());self.assertFalse(close.entries.exists())
        self.assertFalse(quote.movements.exists());self.assertFalse(close.movements.exists())
        self.assertTrue(AuditEvent.objects.filter(business=self.business,action='draft.cancel',target=str(quote.id),details__cancellation_document=close.id).exists())
        closed=self.data(quote)['sales_flow'];self.assertEqual(closed['status'],'cancelled')
        printed=client.get(f'/api/documents/{quote.id}/print/').content.decode()
        self.assertIn('cancelled before posting',printed)
        self.assertIn(self.sponge.name,printed)
        self.assertNotIn('DRAFT -',printed)
        self.assertFalse(closed['can_continue']);self.assertFalse(closed['can_cancel'])
        self.assertEqual(client.post(f'/api/documents/{quote.id}/post/',{},content_type='application/json').status_code,400)
        self.assertEqual(client.patch(f'/api/documents/{quote.id}/',{'data':{'notes':'Forbidden edit'}},content_type='application/json').status_code,400)
        with self.assertRaises(ValidationError):self.order(quote)
        with self.assertRaises(ValidationError):self.post('order_cancel',order=quote.id,reason='Repeated closure')
        quote.refresh_from_db();self.assertEqual(quote.data,payload)
        self.assertEqual(Document.objects.filter(kind='quotation',state='posted').count(),0)

    def test_draft_quote_closure_enforces_cancel_sales_location_product_and_business_permissions(self):
        quote,_,payload=self.draft_quote()
        member=Membership.objects.get(user=self.user,business=self.business)
        for permissions in (['sales.post','drafts.create'],['documents.cancel']):
            member.permissions=permissions;member.save()
            with self.assertRaises(PermissionDenied):self.post('order_cancel',order=quote.id,reason='Missing permission')
        member.permissions=['documents.cancel','sales.post'];member.all_locations=False;member.location_ids=[self.kabul.id];member.save()
        with self.assertRaises(PermissionDenied):self.post('order_cancel',order=quote.id,reason='Wrong location')
        member.all_locations=True;member.product_lines=['adhesive'];member.save()
        with self.assertRaises(PermissionDenied):self.post('order_cancel',order=quote.id,reason='Wrong product line')
        other=Business.objects.create(name='Another isolated business',slug='draft-isolation')
        Membership.objects.create(user=self.user,business=other,permissions=['*'],all_locations=True,product_lines=['sponge','adhesive','shared'])
        with self.assertRaises(ValidationError):execute(Context(self.user,other),'order_cancel',{'date':'2026-10-28','order':quote.id,'reason':'Wrong business'},'cross-business-draft-close')
        quote.refresh_from_db();self.assertEqual(quote.state,'draft');self.assertEqual(quote.data,payload)
        self.assertFalse(Document.objects.filter(kind='order_cancel').exists())
