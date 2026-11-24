from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from erp.core import Context, execute
from erp.models import Attachment, Block, Business, Document, Entry, Membership, StockMovement
from erp.dispatch_models import DeliveryLoad, DeliveryTrip, CustomerQualityClaim, RecallCampaign
from erp.tests.test_manufacturing import Factory

D = Decimal


class DispatchTests(Factory, TestCase):
    def invoice(self, thickness='22'):
        block = self.open_block()
        invoice = self.post('sale', warehouse=self.store.pk, party=self.customer.pk, lines=[{'product': self.sponge.pk, 'block': block.pk, 'thickness_mm': thickness}])
        return invoice, block

    def trip(self):
        vehicle = self.post('transport_vehicle', warehouse=self.store.pk, plate='TEST-123', description='Synthetic truck')
        driver = self.post('transport_driver', warehouse=self.store.pk, name='Synthetic driver', phone='000000')
        trip = self.post('delivery_trip', warehouse=self.store.pk, vehicle=vehicle.result['vehicle'], driver=driver.result['driver'], destination='Synthetic customer address', scheduled_date='2026-10-28')
        return trip.result['trip']

    def loaded_trip(self):
        invoice, block = self.invoice()
        trip = self.trip()
        load = self.post('delivery_load', trip=trip, lines=[{'document': invoice.pk, 'index': 0, 'quantity': '2.2'}])
        self.post('delivery_depart', trip=trip)
        return trip, load.result['lines'][0]['load'], invoice, block

    def test_delivery_partial_acknowledgements_never_repeat_stock_or_revenue(self):
        trip, load, invoice, block = self.loaded_trip()
        entries, movements = Entry.objects.count(), StockMovement.objects.count()
        first = self.post('delivery_acknowledge', load=load, accepted='1', disputed='0', recipient='Customer')
        self.assertEqual(D(first.result['unacknowledged']), D('1.2'))
        self.post('delivery_acknowledge', load=load, accepted='1.2', disputed='0', recipient='Customer')
        self.post('delivery_close', trip=trip)
        self.assertEqual(DeliveryTrip.objects.get(pk=trip).state, 'completed')
        self.assertEqual(Entry.objects.count(), entries)
        self.assertEqual(StockMovement.objects.count(), movements)
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D('978'))
        with self.assertRaises(ValidationError):
            self.post('delivery_acknowledge', load=load, accepted='0.1', disputed='0', recipient='Customer')

    def test_duplicate_loading_and_legacy_confirmation_cannot_duplicate_evidence(self):
        trip, load, invoice, _ = self.loaded_trip()
        with self.assertRaises(ValidationError):
            self.post('delivery_confirm', invoice=invoice.pk, recipient='Customer')
        another = self.post('delivery_trip', warehouse=self.store.pk, vehicle=DeliveryTrip.objects.get(pk=trip).vehicle_id, driver=DeliveryTrip.objects.get(pk=trip).driver_id, destination='Another trip')
        with self.assertRaises(ValidationError):
            self.post('delivery_load', trip=another.result['trip'], lines=[{'document': invoice.pk, 'index': 0, 'quantity': '0.1'}])

    def test_disputed_delivery_requires_resolution_before_trip_close(self):
        trip, load, invoice, _ = self.loaded_trip()
        ack = self.post('delivery_acknowledge', load=load, accepted='1', disputed='1.2', recipient='Customer', note='Measured damage recorded')
        with self.assertRaises(ValidationError):
            self.post('delivery_close', trip=trip)
        self.post('delivery_dispute_resolve', acknowledgement=ack.result['acknowledgement'], outcome='accepted_after_review', note='Customer inspected and accepted the remaining pieces')
        self.post('delivery_close', trip=trip)
        with self.assertRaises(ValidationError):
            self.post('delivery_dispute_resolve', acknowledgement=ack.result['acknowledgement'], outcome='accepted_after_review', note='Duplicate review')

    def test_linked_delivery_return_is_validated_against_actual_original_invoice(self):
        trip, load, invoice, _ = self.loaded_trip()
        ack = self.post('delivery_acknowledge', load=load, accepted='0', disputed='2.2', recipient='Customer', note='Return requested')
        other, _ = self.invoice()
        unrelated = self.post('sales_return', invoice=other.pk, lines=[{'index': 0, 'sheet_count': '1'}])
        with self.assertRaises(ValidationError):
            self.post('delivery_dispute_resolve', acknowledgement=ack.result['acknowledgement'], outcome='linked_return', financial_document=unrelated.pk, note='Wrong invoice')
        returned = self.post('sales_return', invoice=invoice.pk, lines=[{'index': 0, 'sheet_count': '1'}])
        entries, movements = Entry.objects.count(), StockMovement.objects.count()
        self.post('delivery_dispute_resolve', acknowledgement=ack.result['acknowledgement'], outcome='linked_return', financial_document=returned.pk, note='Return already posted through normal workflow')
        self.assertEqual(Entry.objects.count(), entries)
        self.assertEqual(StockMovement.objects.count(), movements)

    def test_load_and_ack_retry_is_idempotent(self):
        trip, load, invoice, _ = self.loaded_trip()
        payload = {'date': '2026-10-28', 'load': load, 'accepted': '2.2', 'recipient': 'Customer'}
        first = execute(Context(self.user, self.business), 'delivery_acknowledge', payload, 'dispatch-ack-retry')
        retry = execute(Context(self.user, self.business), 'delivery_acknowledge', payload, 'dispatch-ack-retry')
        self.assertEqual(first.pk, retry.pk)
        self.assertEqual(DeliveryLoad.objects.get(pk=load).acknowledgements.count(), 1)

    def test_cancelled_planned_load_can_be_reassigned_without_stock_posting(self):
        invoice, _ = self.invoice()
        trip = self.trip()
        self.post('delivery_load', trip=trip, lines=[{'document': invoice.pk, 'index': 0, 'quantity': '2.2'}])
        self.post('delivery_cancel', trip=trip, reason='Truck unavailable before departure')
        self.assertEqual(DeliveryTrip.objects.get(pk=trip).state, 'cancelled')
        replacement = self.post('delivery_trip', warehouse=self.store.pk, vehicle=DeliveryTrip.objects.get(pk=trip).vehicle_id, driver=DeliveryTrip.objects.get(pk=trip).driver_id, destination='Rescheduled delivery')
        self.post('delivery_load', trip=replacement.result['trip'], lines=[{'document': invoice.pk, 'index': 0, 'quantity': '2.2'}])

    def test_claim_inspection_and_close_only_links_existing_return(self):
        invoice, block = self.invoice()
        claim = self.post('quality_claim', invoice=invoice.pk, index=0, quantity='2.2', reason='dimension', description='Thickness measurement questioned')
        self.assertEqual(claim.result['block'], block.pk)
        self.post('quality_claim_review', claim=claim.result['claim'], disposition='return', note='Physical inspection confirms issue')
        with self.assertRaises(ValidationError):
            self.post('quality_claim_close', claim=claim.result['claim'], note='Cannot create a credit implicitly')
        returned = self.post('sales_return', invoice=invoice.pk, lines=[{'index': 0, 'sheet_count': '1'}])
        before = Entry.objects.count(), StockMovement.objects.count()
        closed = self.post('quality_claim_close', claim=claim.result['claim'], return_document=returned.pk, note='Existing return verified')
        self.assertEqual((Entry.objects.count(), StockMovement.objects.count()), before)
        self.assertFalse(closed.result['financial_posting'])
        self.assertEqual(CustomerQualityClaim.objects.get(pk=claim.result['claim']).state, 'closed')

    def test_claim_quantity_and_wrong_block_are_rejected(self):
        invoice, block = self.invoice()
        other = self.open_block()
        with self.assertRaises(ValidationError):
            self.post('quality_claim', invoice=invoice.pk, index=0, block=other.pk, quantity='2.2', reason='damage', description='Incorrect block')
        self.post('quality_claim', invoice=invoice.pk, index=0, quantity='2.2', reason='damage', description='Whole sheet claim')
        with self.assertRaises(ValidationError):
            self.post('quality_claim', invoice=invoice.pk, index=0, quantity='0.1', reason='damage', description='Duplicate claimed quantity')

    def test_attachment_references_cannot_cross_case_or_business(self):
        trip, load, invoice, _ = self.loaded_trip()
        unrelated = self.open_material()
        attachment = Attachment.objects.create(business=self.business, document=unrelated, filename='synthetic.jpg', file='private/synthetic.jpg', uploaded_by=self.user)
        with self.assertRaises(ValidationError):
            self.post('delivery_acknowledge', load=load, accepted='2.2', recipient='Customer', attachments=[attachment.pk])
        self.assertEqual(DeliveryLoad.objects.get(pk=load).acknowledgements.count(), 0)

    def test_location_and_business_isolation(self):
        trip, load, invoice, _ = self.loaded_trip()
        Membership.objects.filter(user=self.user, business=self.business).update(all_locations=False, location_ids=[self.kabul.pk])
        with self.assertRaises(PermissionDenied):
            self.post('delivery_acknowledge', load=load, accepted='2.2', recipient='Customer')
        client = APIClient(); client.force_authenticate(self.user)
        response = client.get('/api/dispatch/trips/', HTTP_X_BUSINESS_ID=str(self.business.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'], [])
        other = Business.objects.create(name='Isolated furniture', slug='dispatch-other')
        Membership.objects.create(user=self.user, business=other, permissions=['*'], all_locations=True, product_lines=['sponge', 'adhesive', 'shared'])
        with self.assertRaises(ValidationError):
            execute(Context(self.user, other), 'quality_claim', {'date': '2026-10-28', 'invoice': invoice.pk, 'index': 0, 'quantity': '1', 'reason': 'other', 'description': 'Cross-tenant attempt'}, 'cross-tenant-claim')

    def produced_block(self):
        self.open_material('100', '1000')
        produced = self.post('production', warehouse=self.store.pk, inputs=[{'product': self.raw.pk, 'quantity': '100'}], outputs=[{'product': self.sponge.pk, 'blocks': [{'length_mm': '2000', 'width_mm': '1000', 'height_mm': '1000'}]}])
        return produced, Block.objects.get(pk=produced.result['outputs'][0]['blocks'][0])

    def test_recall_hold_blocks_sale_transfer_release_and_preserves_existing_quality_hold(self):
        produced, block = self.produced_block()
        block.status = 'inspection'; block.save(update_fields=['status'])
        recall = self.post('quality_recall', batch=produced.pk, reason='Confirmed production issue needs containment')
        with self.assertRaises(ValidationError):
            self.post('quality_release', block=block.pk, reason='Cannot bypass active recall')
        with self.assertRaises(ValidationError):
            self.post('sale', warehouse=self.store.pk, party=self.customer.pk, lines=[{'product': self.sponge.pk, 'block': block.pk, 'thickness_mm': '22'}])
        with self.assertRaises(ValidationError):
            self.post('transfer_dispatch', warehouse=self.store.pk, destination=self.branch.pk, lines=[{'product': self.sponge.pk, 'block': block.pk}])
        self.post('quality_recall_close', campaign=recall.result['campaign'], reason='Root cause reviewed; separate passing inspection remains necessary')
        block.refresh_from_db()
        self.assertEqual(block.status, 'inspection')
        self.assertEqual(self.pool().quantity, D('100'))

    def test_scoped_quality_user_cannot_open_business_wide_recall(self):
        produced, block = self.produced_block()
        Membership.objects.filter(user=self.user, business=self.business).update(all_locations=False, location_ids=[self.location.pk])
        with self.assertRaises(PermissionDenied):
            self.post('quality_recall', batch=produced.pk, reason='Incomplete branch access')
        self.assertEqual(RecallCampaign.objects.count(), 0)
        block.refresh_from_db(); self.assertEqual(block.status, 'ready')

    def test_recall_of_weight_output_conservatively_blocks_entire_product(self):
        self.open_material('100', '1000')
        produced = self.post('production', warehouse=self.store.pk, inputs=[{'product': self.raw.pk, 'quantity': '100'}], outputs=[{'product': self.adhesive.pk, 'quantity': '100'}])
        recall = self.post('quality_recall', batch=produced.pk, reason='Pooled product precaution')
        self.assertEqual(recall.result['conservatively_held_products'], [self.adhesive.pk])
        with self.assertRaises(ValidationError):
            self.post('sale', warehouse=self.store.pk, party=self.customer.pk, lines=[{'product': self.adhesive.pk, 'quantity': '1'}])
        self.assertEqual(self.pool(self.adhesive, profile='').quantity, D('100'))

    def test_claim_view_has_no_cost_input_or_unrelated_customer_data(self):
        invoice, block = self.invoice()
        self.post('quality_claim', invoice=invoice.pk, index=0, quantity='2.2', reason='appearance', description='Surface issue')
        Membership.objects.filter(user=self.user, business=self.business).update(permissions=['quality.view'], product_lines=['sponge'])
        client = APIClient(); client.force_authenticate(self.user)
        response = client.get('/api/dispatch/claims/', HTTP_X_BUSINESS_ID=str(self.business.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertNotIn('cost', str(response.data))
        self.assertNotIn('inputs', str(response.data))
