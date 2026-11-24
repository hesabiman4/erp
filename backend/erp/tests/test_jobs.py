from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from erp.core import Context
from erp.models import Account, BOM, Business, Entry, Membership, Product, StockMovement, Warehouse
from erp.jobs import actuals
from erp.jobs_models import CostingProject, ProjectDocument, ProjectBOMPlan, SubcontractJob
from erp.tests.test_manufacturing import Factory

D = Decimal


class JobCostingTests(Factory, TestCase):
    def project(self, code='SOFA-1'):
        result = self.post('job_project', location=self.location.pk, customer=self.customer.pk, code=code, name='Synthetic furniture order', description='Custom furniture job')
        return CostingProject.objects.get(pk=result.result['project'])

    def tag(self, project, document):
        return self.post('job_document', project=project.pk, document=document.pk, note='Dedicated whole-document actual job source')

    def test_estimate_is_separate_from_actual_financials_and_unique_tag_does_not_post(self):
        Account.objects.filter(business=self.business, code='SALES').update(category='income')
        Account.objects.filter(business=self.business, code__in=['COGS', 'EXPENSE', 'WASTE']).update(category='expense')
        project = self.project()
        self.post('job_estimate', project=project.pk, estimated_revenue='2000', lines=[{'category': 'materials', 'description': 'Estimated materials', 'quantity': '100', 'unit_cost': '9'}, {'category': 'labor', 'description': 'Estimated labor', 'quantity': '1', 'unit_cost': '200'}])
        self.open_material('100', '1000')
        produced = self.post('production', warehouse=self.store.pk, inputs=[{'product': self.raw.pk, 'quantity': '100'}], outputs=[{'product': self.adhesive.pk, 'quantity': '2'}])
        invoice = self.post('sale', warehouse=self.store.pk, party=self.customer.pk, lines=[{'product': self.adhesive.pk, 'quantity': '1', 'unit_price': '900'}])
        before = Entry.objects.count(), StockMovement.objects.count()
        self.tag(project, produced); self.tag(project, invoice)
        self.assertEqual((Entry.objects.count(), StockMovement.objects.count()), before)
        report = actuals(Context(self.user, self.business), project)
        self.assertEqual(D(report['revenue']), D('900'))
        self.assertEqual(D(report['recognized_cost']), D('500'))
        self.assertEqual(D(report['profit']), D('400'))
        self.assertEqual(D(report['material_consumption_analysis']), D('1000'))
        self.assertEqual(D(report['wip_balance']), D('0'))
        self.assertEqual(project.estimates.get().estimated_cost, D('1100'))

    def test_document_cannot_be_counted_in_two_projects(self):
        first, second = self.project(), self.project('SOFA-2')
        self.open_material('10', '100')
        produced = self.post('production', warehouse=self.store.pk, inputs=[{'product': self.raw.pk, 'quantity': '10'}], outputs=[{'product': self.adhesive.pk, 'quantity': '2'}])
        self.tag(first, produced)
        with self.assertRaises(ValidationError): self.tag(second, produced)
        self.assertEqual(ProjectDocument.objects.filter(document=produced).count(), 1)

    def test_nested_bom_approved_snapshot_and_no_actual_company_recipe(self):
        project = self.project()
        intermediate = Product.objects.create(business=self.business, code='INTERMEDIATE', name='Subassembly', kind='finished', unit='kg')
        child = BOM.objects.create(business=self.business, product=intermediate, name='Approved child', version=1, approved=True, output_quantity='5', components=[{'product': self.raw.pk, 'quantity': '2'}])
        parent = BOM.objects.create(business=self.business, product=self.adhesive, name='Approved parent', version=1, approved=True, output_quantity='10', components=[{'product': intermediate.pk, 'quantity': '5', 'bom': child.pk}, {'product': self.raw.pk, 'quantity': '3'}])
        with self.assertRaises(ValidationError):
            self.post('job_bom_plan', project=project.pk, bom=parent.pk, quantity='20')
        self.business.manufacturing_mode = 'bom'; self.business.save(update_fields=['manufacturing_mode'])
        plan = self.post('job_bom_plan', project=project.pk, bom=parent.pk, quantity='20')
        frozen = ProjectBOMPlan.objects.get(pk=plan.result['plan'])
        self.assertEqual(D(frozen.snapshot['leaves'][0]['quantity']), D('10'))
        self.assertFalse(plan.entries.exists()); self.assertFalse(plan.movements.exists())
        child.components = [{'product': self.raw.pk, 'quantity': '4'}]; child.save()
        frozen.refresh_from_db()
        self.assertEqual(D(frozen.snapshot['leaves'][0]['quantity']), D('10'))

    def test_nested_bom_cycle_is_rejected_without_a_plan(self):
        project = self.project()
        self.business.manufacturing_mode = 'bom'; self.business.save(update_fields=['manufacturing_mode'])
        parent = BOM.objects.create(business=self.business, product=self.adhesive, name='Cycle parent', approved=True, output_quantity='1', components=[])
        child = BOM.objects.create(business=self.business, product=self.raw, name='Cycle child', approved=True, output_quantity='1', components=[{'product': self.adhesive.pk, 'quantity': '1', 'bom': parent.pk}])
        parent.components = [{'product': self.raw.pk, 'quantity': '1', 'bom': child.pk}]; parent.save()
        with self.assertRaises(ValidationError): self.post('job_bom_plan', project=project.pk, bom=parent.pk, quantity='1')
        self.assertEqual(ProjectBOMPlan.objects.count(), 0)

    def test_subcontract_owned_stock_uses_actual_supplier_cost_and_real_production(self):
        project = self.project()
        vendor = Warehouse.objects.create(business=self.business, location=self.location, name='Company-owned stock at subcontractor')
        order_doc = self.post('job_subcontract', project=project.pk, supplier=self.supplier.pk, warehouse=vendor.pk, product=self.adhesive.pk, quantity='10', instructions='Process company-owned materials')
        order = order_doc.result['subcontract']
        self.open_material('100', '1000')
        dispatch = self.post('transfer_dispatch', warehouse=self.store.pk, destination=vendor.pk, lines=[{'product': self.raw.pk, 'quantity': '100'}])
        self.post('job_subcontract_link', subcontract=order, kind='send', document=dispatch.pk, note='Actual material shipment')
        receipt = self.post('transfer_receive', transfer=dispatch.pk)
        self.post('job_subcontract_link', subcontract=order, kind='vendor_receipt', document=receipt.pk, note='Vendor acknowledges company-owned stock')
        bill = self.post('expense_post', location=self.location.pk, supplier=self.supplier.pk, amount='200', production_cost=True, expense_account='COST_CLEARING', line='adhesive')
        produced = self.post('production', warehouse=vendor.pk, inputs=[{'product': self.raw.pk, 'quantity': '100'}], overhead_cost='200', conversion_sources=[bill.pk], outputs=[{'product': self.adhesive.pk, 'quantity': '10'}])
        before = Entry.objects.count(), StockMovement.objects.count()
        self.post('job_subcontract_link', subcontract=order, kind='production', document=produced.pk, processing_bill=bill.pk, note='Actual materials and supplier processing cost verified')
        self.assertEqual((Entry.objects.count(), StockMovement.objects.count()), before)
        self.assertEqual(self.pool(self.adhesive, vendor, '').value, D('1200'))
        finished_dispatch = self.post('transfer_dispatch', warehouse=vendor.pk, destination=self.store.pk, lines=[{'product': self.adhesive.pk, 'quantity': '10'}])
        finished_receipt = self.post('transfer_receive', transfer=finished_dispatch.pk)
        self.post('job_subcontract_link', subcontract=order, kind='finished_receipt', document=finished_receipt.pk, note='Finished owned stock received back')
        self.post('job_subcontract_close', subcontract=order, note='Production and all finished receipts reconciled')
        self.assertEqual(SubcontractJob.objects.get(pk=order).state, 'completed')
        self.assertEqual(self.pool(self.adhesive, self.store, '').quantity, D('10'))
        self.assertEqual(self.pool(self.adhesive, self.store, '').value, D('1200'))

    def test_job_scope_and_financial_field_permissions(self):
        project = self.project()
        self.post('job_estimate', project=project.pk, estimated_revenue='2000', lines=[{'category': 'materials', 'description': 'Private estimate', 'quantity': '1', 'unit_cost': '1000'}])
        Membership.objects.filter(user=self.user, business=self.business).update(permissions=['jobs.view'])
        client = APIClient(); client.force_authenticate(self.user)
        response = client.get('/api/jobs/projects/', HTTP_X_BUSINESS_ID=str(self.business.pk))
        self.assertEqual(response.status_code, 200)
        row = response.data['results'][0]
        self.assertTrue(row['financials_restricted'])
        self.assertEqual(row['estimates'], [])
        self.assertNotIn('actuals', row)
        Membership.objects.filter(user=self.user, business=self.business).update(all_locations=False, location_ids=[self.kabul.pk])
        response = client.get('/api/jobs/projects/', HTTP_X_BUSINESS_ID=str(self.business.pk))
        self.assertEqual(response.data['results'], [])

    def test_closed_project_cannot_receive_new_unreviewed_cost_tags(self):
        project = self.project()
        self.post('job_close', project=project.pk, note='Delivery and job records reviewed')
        with self.assertRaises(ValidationError):
            self.post('job_estimate', project=project.pk, estimated_revenue='1', lines=[{'category': 'other', 'description': 'Late unreviewed estimate', 'quantity': '1', 'unit_cost': '1'}])
