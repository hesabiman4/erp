from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase
from rest_framework.test import APIClient
from erp.core import Context, execute
from erp.models import Business, Membership, Party, Document, StockMovement, MaterialLot, LotMovement
from erp.procurement import receipt_match
from erp.procurement_models import SupplierClaim, CycleCountSession, WeighingDevice, WeightMeasurement
from erp.tests.test_manufacturing import Factory

D = Decimal


class ProcurementCountTests(Factory, TestCase):
    def counter(self):
        user = get_user_model().objects.create_user(username='assigned-counter', password='test-only-counter-769!')
        membership = Membership.objects.create(business=self.business, user=user, permissions=['inventory.count_record','inventory.raw'], all_locations=False, location_ids=[self.location.pk], product_lines=['sponge','adhesive'])
        return user, membership

    def receipt(self, quantity='10', cost='10', **extra):
        return self.post('purchase_receive', warehouse=self.store.pk, supplier=self.supplier.pk, lines=[{'product': self.raw.pk, 'quantity': quantity, 'unit_cost': cost}], **extra)

    def assignment(self, member, product=None, **extra):
        return self.post('cycle_count_assign', warehouse=self.store.pk, assignee=member.pk, due_date='2026-10-30', lines=[{'product': (product or self.raw).pk}], **extra)

    def observe(self, user, session, quantity='99'):
        return execute(Context(user, self.business), 'cycle_count_record', {'date':'2026-10-28','session':session,'lines':[{'product':self.raw.pk,'counted_quantity':quantity}]}, f'observe-{session}')

    def test_three_way_match_reports_quantities_and_base_price_difference_without_posting(self):
        order = self.post('purchase_order', warehouse=self.store.pk, supplier=self.supplier.pk, lines=[{'product': self.raw.pk,'quantity':'20','unit_cost':'10'}])
        receipt = self.receipt(cost='12', order=order.pk)
        self.post('purchase_bill', receipt=receipt.pk, supplier_reference='Match-1', lines=[{'index':0,'quantity':'4'}])
        before = (Document.objects.count(), StockMovement.objects.count())
        matched = receipt_match(Context(self.user, self.business), receipt)
        line = matched['lines'][0]
        self.assertEqual(D(line['ordered']), D('20'))
        self.assertEqual(D(line['order_outstanding']), D('10'))
        self.assertEqual(D(line['billed']), D('4'))
        self.assertEqual(D(line['unit_price_variance']), D('2'))
        self.assertIn('purchase_price_difference', line['flags'])
        self.assertEqual(before, (Document.objects.count(), StockMovement.objects.count()))
        Membership.objects.filter(user=self.user).update(permissions=['purchases.view','inventory.raw'])
        safe = receipt_match(Context(self.user, self.business), receipt)['lines'][0]
        self.assertNotIn('received_unit_cost', safe)
        self.assertNotIn('unit_price_variance', safe)
        self.assertNotIn('purchase_price_difference', safe['flags'])

    def test_supplier_reference_normalizes_case_separators_and_afghan_digits(self):
        first = self.receipt()
        self.post('purchase_bill', receipt=first.pk, supplier_reference=' INV-۰۰۱ ')
        second = self.receipt()
        with self.assertRaises(ValidationError): self.post('purchase_bill', receipt=second.pk, supplier_reference='inv 001')
        self.assertEqual(Document.objects.filter(kind='purchase_bill').count(), 1)
        other = Party.objects.create(business=self.business, kind='supplier', name='Different supplier')
        third = self.post('purchase_receive', warehouse=self.store.pk, supplier=other.pk, lines=[{'product':self.raw.pk,'quantity':'1','unit_cost':'10'}])
        self.post('purchase_bill', receipt=third.pk, supplier_reference='inv 001')
        self.assertEqual(Document.objects.filter(kind='purchase_bill').count(), 2)

    def test_supplier_claim_resolution_links_actual_return_without_second_credit(self):
        receipt = self.receipt()
        bill = self.post('purchase_bill', receipt=receipt.pk, supplier_reference='claim-1')
        claim_doc = self.post('supplier_claim', document=receipt.pk, index=0, quantity='2', reason='damage', description='Two sealed containers damaged at unloading')
        self.assertFalse(claim_doc.entries.exists()); self.assertFalse(claim_doc.movements.exists())
        with self.assertRaises(ValidationError): self.post('supplier_claim_resolve', claim=claim_doc.result['claim'], outcome='returned_credit', note='No actual return yet', financial_document=bill.pk)
        actual = self.post('purchase_return', receipt=receipt.pk, bill=bill.pk, lines=[{'index':0,'quantity':'2'}])
        before = StockMovement.objects.count()
        resolved = self.post('supplier_claim_resolve', claim=claim_doc.result['claim'], outcome='returned_credit', note='Supplier accepted actual returned quantity', financial_document=actual.pk)
        self.assertFalse(resolved.entries.exists()); self.assertEqual(before, StockMovement.objects.count())
        self.assertEqual(SupplierClaim.objects.get(pk=claim_doc.result['claim']).state, 'resolved')
        with self.assertRaises(ValidationError): self.post('supplier_claim_resolve', claim=claim_doc.result['claim'], outcome='cancelled', note='Cannot resolve twice')

    def test_order_shortage_claim_cannot_exceed_remaining_undelivered_quantity(self):
        order = self.post('purchase_order', warehouse=self.store.pk, supplier=self.supplier.pk, lines=[{'product':self.raw.pk,'quantity':'20','unit_price':'10'}])
        self.receipt(order=order.pk)
        with self.assertRaises(ValidationError): self.post('supplier_claim', document=order.pk,index=0,quantity='11',reason='shortage',description='Too much')
        claim = self.post('supplier_claim', document=order.pk,index=0,quantity='6',reason='shortage',description='Missing from delivery')
        with self.assertRaises(ValidationError): self.post('supplier_claim', document=order.pk,index=0,quantity='5',reason='shortage',description='Duplicate claim amount')
        self.post('supplier_claim_resolve', claim=claim.result['claim'], outcome='cancelled', note='Supplier will complete the original order')
        self.post('supplier_claim', document=order.pk,index=0,quantity='10',reason='shortage',description='Revised evidence')

    def test_blind_counter_api_and_generic_documents_never_reveal_book_quantities(self):
        self.open_material('100','1000')
        user, member = self.counter()
        assignment = self.assignment(member)
        count = self.observe(user, assignment.result['session'], '99')
        self.assertIn('expected_quantity', str(count.result))
        session = CycleCountSession.objects.get(pk=assignment.result['session'])
        client = APIClient();client.force_login(user)
        headers = {'HTTP_X_BUSINESS_ID':str(self.business.pk)}
        response = client.get('/api/procurement/counts/', **headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('expected_quantity', str(response.json()))
        self.assertNotIn('observation', response.json()['results'][0])
        direct = client.get(f'/api/documents/{session.observation_id}/', **headers)
        self.assertEqual(direct.status_code, 200); self.assertNotIn('expected_quantity', str(direct.json())); self.assertNotIn('pool_snapshot', str(direct.json())); self.assertNotIn('variance', str(direct.json()))
        printed = client.get(f'/api/documents/{session.observation_id}/print/', **headers)
        self.assertEqual(printed.status_code, 403); self.assertNotIn(b'expected_quantity', printed.content); self.assertNotIn(b'pool_snapshot', printed.content)
        self.assertEqual(client.post('/api/operations/stock_count/', {'warehouse':self.store.pk,'lines':[{'product':self.raw.pk,'counted_quantity':'99'}]}, format='json', HTTP_IDEMPOTENCY_KEY='cannot-probe-book-quantity', **headers).status_code, 403)
        self.assertEqual(client.get('/api/stock/', **headers).status_code, 403)
        self.assertEqual(self.pool(self.raw, profile='').quantity, D('100'))

    def test_separate_reviewer_posts_one_supported_count_adjustment_and_retry_is_safe(self):
        self.open_material('100','1000');user,member=self.counter()
        assigned=self.assignment(member);self.observe(user,assigned.result['session'],'97.5')
        session=CycleCountSession.objects.get(pk=assigned.result['session'])
        with self.assertRaises(ValidationError): self.post('stock_count_adjust',count=session.observation_id,reason='Direct adjustment cannot bypass the assigned review')
        reviewed=self.post('cycle_count_review',session=session.pk,outcome='adjust',reason='Independent recount confirms 2.5 kg shortage')
        session.refresh_from_db()
        self.assertEqual(session.state,'closed');self.assertEqual(self.pool(self.raw,profile='').quantity,D('97.5'))
        self.assertEqual(self.pool(self.raw,profile='').value,D('975'))
        self.assertFalse(reviewed.entries.exists());self.assert_journal_balanced(session.adjustment)
        with self.assertRaises(ValidationError):self.post('cycle_count_review',session=session.pk,outcome='adjust',reason='Duplicate review')
        self.assertEqual(Document.objects.filter(kind='stock_count_adjust').count(),1)

    def test_wrong_counter_and_self_review_without_separate_exception_are_denied(self):
        self.open_material('100','1000');user,member=self.counter();assigned=self.assignment(member)
        with self.assertRaises(PermissionDenied):self.post('cycle_count_record',session=assigned.result['session'],lines=[{'product':self.raw.pk,'counted_quantity':'99'}])
        self.observe(user,assigned.result['session'],'99')
        member.permissions=['inventory.count_record','inventory.raw','inventory.count_review','inventory.adjust'];member.save(update_fields=['permissions'])
        with self.assertRaises(PermissionDenied):execute(Context(user,self.business),'cycle_count_review',{'date':'2026-10-28','session':assigned.result['session'],'reason':'Self review','outcome':'adjust'},'self-review-denied')

    def test_stale_counts_require_recount_instead_of_overwriting_later_stock(self):
        self.open_material('100','1000');user,member=self.counter();assigned=self.assignment(member);self.observe(user,assigned.result['session'],'99')
        self.post('material_issue',warehouse=self.store.pk,destination=self.floor.pk,lines=[{'product':self.raw.pk,'quantity':'10'}])
        with self.assertRaises(ValidationError):self.post('cycle_count_review',session=assigned.result['session'],outcome='adjust',reason='Stale evidence')
        session=CycleCountSession.objects.get(pk=assigned.result['session']);self.assertEqual(session.state,'observed')
        self.post('cycle_count_review',session=session.pk,outcome='recount',reason='Stock moved after observation')
        self.assertEqual(self.pool(self.raw,profile='').quantity,D('90'))

    def test_no_difference_acceptance_is_nonfinancial_and_stale_zero_variance_rejected(self):
        self.open_material('100','1000');user,member=self.counter();assigned=self.assignment(member);self.observe(user,assigned.result['session'],'100')
        accepted=self.post('cycle_count_review',session=assigned.result['session'],outcome='accept_no_difference',reason='Independent no-difference confirmation')
        self.assertFalse(accepted.entries.exists());self.assertFalse(accepted.movements.exists())
        second=self.assignment(member);self.observe(user,second.result['session'],'100')
        self.post('material_issue',warehouse=self.store.pk,destination=self.floor.pk,lines=[{'product':self.raw.pk,'quantity':'1'}])
        with self.assertRaises(ValidationError):self.post('cycle_count_review',session=second.result['session'],outcome='accept_no_difference',reason='Cannot sign off stale quantities')

    def test_confirmed_net_weight_requires_calibration_and_receives_goods_once(self):
        device=self.post('weighing_device',warehouse=self.store.pk,code='SCALE-1',name='Receiving scale',capacity_kg='1000')
        readings={'device':device.result['device'],'product':self.raw.pk,'gross_kg':'105.5','tare_kg':'5.5','container_count':2,'confirmed':True}
        with self.assertRaises(ValidationError):self.post('weight_measure',**readings)
        self.post('scale_calibrate',device=device.result['device'],next_due='2027-10-01',reference='Synthetic certificate TEST-1',note='Operator documented external calibration evidence')
        measurement=self.post('weight_measure',**readings)
        self.assertEqual(D(measurement.result['net_kg']),D('100'))
        self.assertFalse(measurement.entries.exists());self.assertFalse(measurement.movements.exists())
        received=self.post('measured_receive',measurement=measurement.result['measurement'],supplier=self.supplier.pk,unit_cost='10')
        self.assertFalse(received.entries.exists());self.assertEqual(self.pool(self.raw,profile='').quantity,D('100'))
        self.assertEqual(self.pool(self.raw,profile='').value,D('1000'))
        self.assertEqual(Document.objects.filter(kind='purchase_receive').count(),1)
        with self.assertRaises(ValidationError):self.post('measured_receive',measurement=measurement.result['measurement'],supplier=self.supplier.pk,unit_cost='10')
        with self.assertRaises(ValidationError):self.post('purchase_receive',warehouse=self.store.pk,supplier=self.supplier.pk,lines=[{'product':self.raw.pk,'quantity':'99','unit_cost':'10','measurement':measurement.result['measurement']}])

    def test_expired_unconfirmed_and_overcapacity_weights_reject_without_stock(self):
        device=self.post('weighing_device',warehouse=self.store.pk,code='SCALE-1',name='Receiving scale',capacity_kg='100')
        self.post('scale_calibrate',device=device.result['device'],next_due='2026-10-29',reference='TEST-2',note='Calibration evidence')
        data={'device':device.result['device'],'product':self.raw.pk,'gross_kg':'50','tare_kg':'2','confirmed':False}
        with self.assertRaises(ValidationError):self.post('weight_measure',**data)
        data.update(confirmed=True,gross_kg='101')
        with self.assertRaises(ValidationError):self.post('weight_measure',**data)
        data.update(gross_kg='50',date='2026-10-30')
        with self.assertRaises(ValidationError):self.post('weight_measure',**data)
        self.assertEqual(WeightMeasurement.objects.count(),0);self.assertEqual(StockMovement.objects.count(),0)

    def test_cross_business_and_posted_evidence_guards(self):
        self.open_material('100','1000');user,member=self.counter();assigned=self.assignment(member)
        other=Business.objects.create(name='Other',slug='other-procurement')
        outsider=get_user_model().objects.create_user(username='other-counter')
        foreign=Membership.objects.create(business=other,user=outsider,permissions=['inventory.count'],all_locations=True,product_lines=['sponge'])
        with self.assertRaises(ValidationError):self.assignment(foreign)
        session=CycleCountSession.objects.get(pk=assigned.result['session'])
        with self.assertRaises(DatabaseError),transaction.atomic():CycleCountSession.objects.filter(pk=session.pk).update(targets=[])
        device=self.post('weighing_device',warehouse=self.store.pk,code='SCALE-1',name='Receiving scale',capacity_kg='100')
        with self.assertRaises(DatabaseError),transaction.atomic():WeighingDevice.objects.filter(pk=device.result['device']).update(capacity_kg='999')

    def test_calibration_and_count_review_cannot_precede_their_source_events(self):
        device=self.post('weighing_device',date='2026-10-29',warehouse=self.store.pk,code='SCALE-FUTURE',name='Later registered scale',capacity_kg='100')
        with self.assertRaises(ValidationError):self.post('scale_calibrate',date='2026-10-28',device=device.result['device'],next_due='2027-10-01',reference='Backdated certificate',note='Cannot precede device registration')
        self.assertEqual(device.reference_id,None)
        self.open_material('100','1000');user,member=self.counter();assigned=self.assignment(member)
        execute(Context(user,self.business),'cycle_count_record',{'date':'2026-10-29','session':assigned.result['session'],'lines':[{'product':self.raw.pk,'counted_quantity':'100'}]},'later-observation')
        with self.assertRaises(ValidationError):self.post('cycle_count_review',date='2026-10-28',session=assigned.result['session'],outcome='accept_no_difference',reason='Cannot review before observation')
        with self.assertRaises(ValidationError):self.post('cycle_count_review',date='2026-10-28',session=assigned.result['session'],outcome='recount',reason='Cannot request an earlier recount')

    def test_measured_receipt_preserves_strict_material_lot_tracking(self):
        self.business.settings={'lot_tracking':True};self.business.save(update_fields=['settings'])
        device=self.post('weighing_device',warehouse=self.store.pk,code='SCALE-LOT',name='Lot receiving scale',capacity_kg='1000')
        self.post('scale_calibrate',device=device.result['device'],next_due='2027-10-01',reference='TEST-LOT',note='Documented calibration')
        measured=self.post('weight_measure',device=device.result['device'],product=self.raw.pk,gross_kg='105',tare_kg='5',confirmed=True)
        with self.assertRaises(ValidationError):self.post('measured_receive',measurement=measured.result['measurement'],supplier=self.supplier.pk,unit_cost='10')
        lot=MaterialLot.objects.create(business=self.business,code='MEASURED-LOT-1',product=self.raw,supplier=self.supplier,state='released')
        received=self.post('measured_receive',measurement=measured.result['measurement'],supplier=self.supplier.pk,unit_cost='10',lot=lot.pk)
        self.assertEqual(LotMovement.objects.get(document_id=received.result['receipt'],lot=lot).quantity,D('100'))
        self.assertEqual(self.pool(self.raw,profile='').quantity,D('100'))

    def test_generic_weight_and_count_documents_respect_raw_quantity_authority(self):
        device=self.post('weighing_device',warehouse=self.store.pk,code='SCALE-PRIVATE',name='Private material scale',capacity_kg='1000')
        self.post('scale_calibrate',device=device.result['device'],next_due='2027-10-01',reference='PRIVATE-TEST',note='Calibration evidence')
        measured=self.post('weight_measure',device=device.result['device'],product=self.raw.pk,gross_kg='105',tare_kg='5',confirmed=True)
        received=self.post('measured_receive',measurement=measured.result['measurement'],supplier=self.supplier.pk,unit_cost='10')
        count=self.post('stock_count',warehouse=self.store.pk,lines=[{'product':self.raw.pk,'counted_quantity':'100'}])
        Membership.objects.filter(user=self.user,business=self.business).update(permissions=['inventory.measure','inventory.count','purchases.post','documents.view','documents.print'])
        client=APIClient();client.force_login(self.user);headers={'HTTP_X_BUSINESS_ID':str(self.business.pk)}
        for source in [measured,received,count]:
            self.assertEqual(client.get(f'/api/documents/{source.pk}/',**headers).status_code,403)
            self.assertEqual(client.get(f'/api/documents/{source.pk}/print/',**headers).status_code,403)
