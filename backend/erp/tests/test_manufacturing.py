from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connections
from django.db.models import Sum
from django.test import TestCase, TransactionTestCase

from erp.core import Context, execute, outstanding, profile_for
from erp.models import (
    Account, Block, BOM, Business, Document, Entry, Location,
    Membership, Party, Product, StockMovement, StockPool, TaxRule, Warehouse,
)


D = Decimal


class Factory:
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="manufacturing-owner", password="test-only-complex-236!")
        self.business = Business.objects.create(name="Sponge demo", slug="sponge-tests")
        Membership.objects.create(business=self.business, user=self.user, permissions=["*"], all_locations=True, product_lines=["sponge", "adhesive", "shared"])
        self.location = Location.objects.create(business=self.business, code="FACTORY", name="Factory")
        self.kabul = Location.objects.create(business=self.business, code="KABUL", name="Kabul")
        self.store = Warehouse.objects.create(business=self.business, location=self.location, name="Stores")
        self.floor = Warehouse.objects.create(business=self.business, location=self.location, name="Production floor", kind="floor")
        self.branch = Warehouse.objects.create(business=self.business, location=self.kabul, name="Branch store")
        for code in ["RAW", "FG", "TRIM", "TRANSIT", "WIP", "GRNI", "AP", "AR", "CASH", "BANK", "DEPOSITS", "COGS", "SALES", "WASTE", "EQUITY", "EXPENSE", "COST_CLEARING", "LABOR_CLEARING", "SUPPLIER_DEPOSITS", "TAX"]:
            Account.objects.create(business=self.business, code=code, name=code, category="asset")
        self.sponge = Product.objects.create(business=self.business, code="S45", name="اسفنج 45 کیلو گرام", unit="cm", kind="finished", line="sponge", price="500")
        self.raw = Product.objects.create(business=self.business, code="TDI", name="تی دی آی", unit="kg", kind="raw", line="sponge")
        self.trim = Product.objects.create(business=self.business, code="TOP45", name="سربلوک 45", unit="each", kind="trim", line="sponge", price="100")
        self.bottom = Product.objects.create(business=self.business, code="BOTTOM45", name="کف بلوک 45", unit="each", kind="trim", line="sponge", price="100")
        self.adhesive = Product.objects.create(business=self.business, code="ADH", name="چسپ", unit="kg", kind="finished", line="adhesive", price="100")
        self.supplier = Party.objects.create(business=self.business, name="Synthetic supplier", kind="supplier")
        self.customer = Party.objects.create(business=self.business, name="Synthetic customer", kind="customer")
        self.key = 0

    def post(self, action, **payload):
        self.key += 1
        payload.setdefault("date", "2026-10-28")
        return execute(Context(self.user, self.business), action, payload, f"manufacturing-{self.key}")

    def open_material(self, quantity="1000", value="100000", warehouse=None):
        return self.post("stock_opening", warehouse=(warehouse or self.store).id, lines=[{"product": self.raw.id, "quantity": quantity, "value": value}])

    def open_block(self, height="1000", value="10000", length="2000", width="1000", warehouse=None):
        doc = self.post("stock_opening", warehouse=(warehouse or self.store).id, lines=[{"product": self.sponge.id, "value": value, "blocks": [{"length_mm": length, "width_mm": width, "height_mm": height}]}])
        return Block.objects.get(pk=doc.result["lines"][0]["blocks"][0])

    def pool(self, product=None, warehouse=None, profile=None):
        return StockPool.objects.get(business=self.business, product=product or self.sponge, warehouse=warehouse or self.store, profile=profile if profile is not None else profile_for("2000", "1000"))

    def assert_journal_balanced(self, doc):
        amounts = doc.entries.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        self.assertEqual(amounts["debit"] or D("0"), amounts["credit"] or D("0"))


class ManufacturingTests(Factory, TestCase):
    def test_exact_cut_is_height_not_product_label_mass(self):
        block = self.open_block()
        self.assertEqual(block.remaining_height_mm, D("1000"))
        self.assertEqual(self.pool().quantity, D("100"))
        invoice = self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}], paid="1100")
        block.refresh_from_db()
        self.assertEqual(invoice.amount, D("1100.00"))
        self.assertEqual(invoice.result["lines"][0]["quantity"], "2.2")
        self.assertEqual(block.remaining_height_mm, D("978"))
        self.assertEqual(self.pool().quantity, D("97.8"))
        self.assertEqual(outstanding(invoice), D("0"))
        self.assertEqual(invoice.result["lines"][0]["cost"], "220.00")
        self.assert_journal_balanced(invoice)

    def test_multiple_sheets_and_configured_per_cut_loss(self):
        block = self.open_block()
        invoice = self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22", "sheet_count": "3", "cutting_loss_mm": "1", "loss_policy": "per_cut"}])
        block.refresh_from_db()
        self.assertEqual(invoice.amount, D("3300"))
        self.assertEqual(block.remaining_height_mm, D("931"))
        self.assertEqual(self.pool().quantity, D("93.1"))
        self.assertEqual(invoice.result["lines"][0]["loss_mm"], "3")
        self.assertEqual(invoice.result["lines"][0]["cost"], "690.00")

    def test_partial_footprint_is_rejected_without_stock_change(self):
        block = self.open_block()
        before = Document.objects.count()
        with self.assertRaises(ValidationError):
            self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22", "partial_width_mm": "500"}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("1000"))
        self.assertEqual(Document.objects.count(), before)

    def test_fragmented_stock_cannot_fulfill_thick_sheet(self):
        blocks = [self.open_block(height="100", value="1000") for _ in range(10)]
        self.assertEqual(self.pool().quantity, D("100"))
        with self.assertRaises(ValidationError):
            self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": blocks[0].id, "thickness_mm": "220"}])
        self.assertEqual(self.pool().quantity, D("100"))

    def test_unlike_footprints_have_separate_pools(self):
        self.open_block()
        self.open_block(length="1000", width="1000")
        pools = StockPool.objects.filter(product=self.sponge, warehouse=self.store)
        self.assertEqual(pools.count(), 2)
        self.assertEqual({p.profile for p in pools}, {"2000.000x1000.000", "1000.000x1000.000"})
        self.assertEqual({p.quantity for p in pools}, {D("100")})

    def test_reservation_prevents_another_sale_and_consumes_once(self):
        block = self.open_block(height="30", value="300")
        reservation = self.post("reserve", lines=[{"block": block.id, "thickness_mm": "22"}])
        with self.assertRaises(ValidationError):
            self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}])
        invoice = self.post("sale", warehouse=self.store.id, reservation=reservation.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("8"))
        self.assertEqual(block.reserved_height_mm, D("0"))
        with self.assertRaises(ValidationError):
            self.post("reservation_release", reservation=reservation.id)
        self.assert_journal_balanced(invoice)

    def test_cut_held_for_collection_has_no_revenue_and_normal_loss_absorbed(self):
        block = self.open_block()
        doc = self.post("cut", warehouse=self.store.id, product=self.sponge.id, block=block.id, thickness_mm="22", cutting_loss_mm="1")
        block.refresh_from_db()
        child = Block.objects.get(pk=doc.result["blocks"][0])
        self.assertEqual(block.remaining_height_mm, D("977"))
        self.assertEqual(child.remaining_height_mm, D("22"))
        self.assertEqual(child.parent_id, block.id)
        self.assertEqual(self.pool().quantity, D("99.9"))
        self.assertEqual(self.pool().value, D("10000"))
        self.assertFalse(doc.entries.exists())

    def test_actual_production_cost_conservation_main_trim_loss_and_sale(self):
        self.open_material()
        source = self.post("expense_post", location=self.location.id, supplier=self.supplier.id, production_cost=True, expense_account="COST_CLEARING", amount="30000", line="sponge")
        batch = self.post("production", warehouse=self.store.id, inputs=[{"product": self.raw.id, "quantity": "1000"}], labor_cost="20000", overhead_cost="10000", conversion_sources=[source.id], abnormal_loss="5000", outputs=[{"product": self.sponge.id, "cost": "120000", "blocks": [{"length_mm": "2000", "width_mm": "1000", "height_mm": "1000"} for _ in range(10)]}, {"product": self.trim.id, "quantity": "50", "cost": "5000"}])
        self.assertFalse(BOM.objects.exists())
        self.assertEqual(batch.result["total_cost"], "130000.00")
        self.assertEqual(self.pool().quantity, D("1000"))
        self.assertEqual(self.pool().value, D("120000"))
        block = Block.objects.get(pk=batch.result["outputs"][0]["blocks"][0])
        invoice = self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "500", "unit_price": "100"}])
        self.assertEqual(invoice.result["lines"][0]["cost"], "6000.00")
        self.assertEqual(self.pool().quantity, D("950"))
        self.assertEqual(self.pool().value, D("114000"))
        self.assertEqual(self.pool(product=self.trim, profile="").value, D("5000"))
        self.assertEqual(D("114000") + D(invoice.result["lines"][0]["cost"]) + D("5000") + D(batch.result["abnormal_loss"]), D("130000"))
        self.assert_journal_balanced(batch)
        self.assert_journal_balanced(invoice)

    def test_conversion_costs_require_backing_and_cannot_be_absorbed_twice(self):
        self.open_material("10", "100")
        with self.assertRaises(ValidationError):
            self.post("production", warehouse=self.store.id, inputs=[{"product": self.raw.id, "quantity": "1"}], labor_cost="10", outputs=[{"product": self.adhesive.id, "quantity": "1"}])
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("10"))
        source = self.post("expense_post", location=self.location.id, supplier=self.supplier.id, production_cost=True, expense_account="COST_CLEARING", amount="10", line="sponge")
        self.post("production", warehouse=self.store.id, inputs=[{"product": self.raw.id, "quantity": "1"}], labor_cost="10", conversion_sources=[source.id], outputs=[{"product": self.adhesive.id, "quantity": "1"}])
        with self.assertRaises(ValidationError):
            self.post("production", warehouse=self.store.id, inputs=[{"product": self.raw.id, "quantity": "1"}], labor_cost="10", conversion_sources=[source.id], outputs=[{"product": self.adhesive.id, "quantity": "1"}])
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("9"))

    def test_material_issue_consumption_unused_return_and_wip_completion(self):
        self.open_material("120", "1200")
        self.post("material_issue", warehouse=self.store.id, destination=self.floor.id, lines=[{"product": self.raw.id, "quantity": "120"}])
        batch = self.post("production_start", warehouse=self.floor.id)
        consume = self.post("production_consume", batch=batch.id, inputs=[{"product": self.raw.id, "quantity": "100"}])
        self.post("material_return", warehouse=self.floor.id, destination=self.store.id, lines=[{"product": self.raw.id, "quantity": "15"}])
        self.assertEqual(self.pool(self.raw, self.floor, "").quantity, D("5"))
        self.assertEqual(self.pool(self.raw, self.store, "").quantity, D("15"))
        self.assertEqual(consume.result["wip_in"], "1000.00")
        finish = self.post("production_complete", batch=batch.id, warehouse=self.store.id, outputs=[{"product": self.adhesive.id, "quantity": "250.750"}])
        self.assertEqual(finish.result["wip_remaining"], "0.00")
        with self.assertRaises(ValidationError):
            self.post("production_consume", batch=batch.id, inputs=[{"product": self.raw.id, "quantity": "1"}])
        self.assert_journal_balanced(finish)

    def test_wip_material_return_is_distinct_from_unused_floor_move(self):
        self.open_material("100", "1000")
        batch = self.post("production_start", warehouse=self.store.id)
        consume = self.post("production_consume", batch=batch.id, inputs=[{"product": self.raw.id, "quantity": "100"}])
        returned = self.post("production_material_return", consumption=consume.id, lines=[{"index": 0, "quantity": "5"}])
        self.assertEqual(returned.result["wip_out"], "50.00")
        self.assertEqual(self.pool(self.raw, self.store, "").quantity, D("5"))
        finish = self.post("production_complete", batch=batch.id, outputs=[{"product": self.adhesive.id, "quantity": "95"}])
        self.assertEqual(finish.result["outputs"][0]["cost"], "950.00")

    def test_trim_geometry_and_cost_conservation_then_trim_sale(self):
        block = self.open_block(height="1060", value="10600")
        doc = self.post("trim", block=block.id, main_height_mm="1000", top_height_mm="30", bottom_height_mm="20", loss_mm="10", outputs=[{"product": self.trim.id, "quantity": "1", "cost": "300"}, {"product": self.bottom.id, "quantity": "1", "cost": "200"}])
        block.refresh_from_db()
        self.assertEqual(block.initial_height_mm, D("1060"))
        self.assertEqual(block.remaining_height_mm, D("1000"))
        self.assertEqual(self.pool().quantity, D("100"))
        self.assertEqual(self.pool().value, D("10100"))
        self.assertEqual(self.pool(self.trim, profile="").value, D("300"))
        self.post("sale", warehouse=self.store.id, lines=[{"product": self.trim.id, "quantity": "1"}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("1000"))
        self.assert_journal_balanced(doc)

    def test_bad_trim_rolls_back_block_stock_and_document(self):
        block = self.open_block(height="1060", value="10600")
        before = StockMovement.objects.count()
        with self.assertRaises(ValidationError):
            self.post("trim", block=block.id, main_height_mm="1000", top_height_mm="30", bottom_height_mm="20", loss_mm="5", outputs=[{"product": self.trim.id, "quantity": "1", "cost": "300"}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("1060"))
        self.assertEqual(StockMovement.objects.count(), before)

    def test_adhesive_exact_kg_and_return_original_cost(self):
        self.open_material("250.750", "50150")
        self.post("production", warehouse=self.store.id, inputs=[{"product": self.raw.id, "quantity": "250.750"}], outputs=[{"product": self.adhesive.id, "quantity": "250.750"}])
        invoice = self.post("sale", warehouse=self.store.id, lines=[{"product": self.adhesive.id, "quantity": "12.500"}])
        self.assertEqual(self.pool(self.adhesive, profile="").quantity, D("238.250"))
        returned = self.post("sales_return", invoice=invoice.id, lines=[{"index": 0, "quantity": "12.500"}])
        self.assertEqual(self.pool(self.adhesive, profile="").quantity, D("250.750"))
        self.assertEqual(returned.result["cost"], "2500.00")
        self.assertEqual(outstanding(invoice), D("0"))

    def test_return_sheet_is_separate_inspected_piece_not_parent_height(self):
        block = self.open_block()
        invoice = self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}], paid="1100")
        returned = self.post("sales_return", invoice=invoice.id, lines=[{"index": 0, "sheet_count": "1"}])
        block.refresh_from_db()
        child = Block.objects.get(pk=returned.result["lines"][0]["blocks"][0])
        self.assertEqual(block.remaining_height_mm, D("978"))
        self.assertEqual(child.remaining_height_mm, D("22"))
        self.assertEqual(child.status, "inspection")
        self.assertEqual(child.parent_id, block.id)
        self.assertEqual(returned.result["cost"], "220.00")
        self.assertEqual(returned.result["deposit_amount"], "1100.00")
        with self.assertRaises(ValidationError):
            self.post("sales_return", invoice=invoice.id, lines=[{"index": 0, "sheet_count": "1"}])

    def test_purchase_receipt_then_partial_bill_no_double_stock(self):
        receipt = self.post("purchase_receive", warehouse=self.store.id, supplier=self.supplier.id, lines=[{"product": self.raw.id, "quantity": "100", "unit_cost": "10"}])
        bill = self.post("purchase_bill", receipt=receipt.id, supplier_reference="TEST-001", lines=[{"index": 0, "quantity": "60"}])
        self.assertEqual(bill.amount, D("600"))
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("100"))
        self.assertEqual(self.pool(self.raw, profile="").value, D("1000"))
        with self.assertRaises(ValidationError):
            self.post("purchase_bill", receipt=receipt.id, supplier_reference="TEST-001", lines=[{"index": 0, "quantity": "40"}])
        self.post("purchase_bill", receipt=receipt.id, lines=[{"index": 0, "quantity": "40"}])
        with self.assertRaises(ValidationError):
            self.post("purchase_bill", receipt=receipt.id)

    def test_purchase_return_credit_and_unbilled_return(self):
        receipt = self.post("purchase_receive", warehouse=self.store.id, supplier=self.supplier.id, lines=[{"product": self.raw.id, "quantity": "100", "unit_cost": "10"}])
        bill = self.post("purchase_bill", receipt=receipt.id, lines=[{"index": 0, "quantity": "60"}])
        credited = self.post("purchase_return", receipt=receipt.id, bill=bill.id, lines=[{"index": 0, "quantity": "10"}])
        self.assertEqual(outstanding(bill), D("500"))
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("90"))
        self.assert_journal_balanced(credited)
        self.post("purchase_return", receipt=receipt.id, lines=[{"index": 0, "quantity": "40"}])
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("50"))
        with self.assertRaises(ValidationError):
            self.post("purchase_bill", receipt=receipt.id, lines=[{"index": 0, "quantity": "1"}])

    def test_transfer_partial_receive_damage_and_return_preserve_cost(self):
        self.open_material("100", "2000")
        transfer = self.post("transfer_dispatch", warehouse=self.store.id, destination=self.branch.id, internal_charge="3000", lines=[{"product": self.raw.id, "quantity": "100"}])
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("0"))
        self.post("transfer_receive", transfer=transfer.id, lines=[{"index": 0, "quantity": "60"}])
        self.post("transfer_resolve", transfer=transfer.id, resolution="damage", reason="Inspection confirmed transport damage", lines=[{"index": 0, "quantity": "10"}])
        self.post("transfer_resolve", transfer=transfer.id, resolution="return", reason="Unneeded shipment returned", lines=[{"index": 0, "quantity": "30"}])
        self.assertEqual(self.pool(self.raw, self.branch, "").quantity, D("60"))
        self.assertEqual(self.pool(self.raw, self.branch, "").value, D("1200"))
        self.assertEqual(self.pool(self.raw, self.store, "").value, D("600"))
        transit = StockPool.objects.get(warehouse_id=transfer.result["transit"], product=self.raw)
        self.assertEqual(transit.quantity, D("0"))
        self.assertEqual(transit.value, D("0"))
        self.assertFalse(Entry.objects.filter(document=transfer, account__code__in=["SALES", "AR", "COGS"]).exists())
        self.assert_journal_balanced(transfer)
        with self.assertRaises(ValidationError):
            self.post("transfer_receive", transfer=transfer.id)

    def test_transfer_preserves_partially_sold_block_dimensions(self):
        block = self.open_block(value="2000")
        self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}])
        transfer = self.post("transfer_dispatch", warehouse=self.store.id, destination=self.branch.id, lines=[{"product": self.sponge.id, "block": block.id}])
        block.refresh_from_db()
        self.assertEqual(block.status, "in_transit")
        with self.assertRaises(ValidationError):
            self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}])
        self.post("transfer_receive", transfer=transfer.id)
        block.refresh_from_db()
        self.assertEqual(block.warehouse_id, self.branch.id)
        self.assertEqual(block.remaining_height_mm, D("978"))
        self.assertEqual(self.pool(self.sponge, self.branch).value, D("1956"))

    def test_transfer_into_different_average_cost_pool(self):
        self.open_material("10", "100", self.store)
        self.open_material("10", "200", self.branch)
        transfer = self.post("transfer_dispatch", warehouse=self.store.id, destination=self.branch.id, lines=[{"product": self.raw.id, "quantity": "5"}])
        self.post("transfer_receive", transfer=transfer.id)
        self.assertEqual(self.pool(self.raw, self.branch, "").quantity, D("15"))
        self.assertEqual(self.pool(self.raw, self.branch, "").value, D("250"))
        self.assertEqual(self.pool(self.raw, self.store, "").value, D("50"))

    def test_kabul_only_storekeeper_can_receive_incoming_transfer(self):
        self.open_material("10", "100")
        transfer = self.post("transfer_dispatch", warehouse=self.store.id, destination=self.branch.id, lines=[{"product": self.raw.id, "quantity": "10"}])
        Membership.objects.filter(user=self.user, business=self.business).update(all_locations=False, location_ids=[self.kabul.id], permissions=["transfers.post", "inventory.view", "inventory.raw"],approval_limit=D('1000'))
        from erp.operations import manufacturing_report
        incoming = manufacturing_report(Context(self.user, self.business), "transfer_status", {"warehouse": str(self.branch.id)})
        self.assertEqual([row["id"] for row in incoming["rows"]], [transfer.id])
        self.assertNotIn("cost", incoming["rows"][0]["lines"][0])
        self.assertEqual(incoming["rows"][0]["lines"][0]["outstanding_quantity"], "10")
        receipt = self.post("transfer_receive", transfer=transfer.id)
        self.assertEqual(receipt.location_id, self.kabul.id)
        self.assertEqual(StockPool.objects.get(product=self.raw, warehouse=self.branch).quantity, D("10"))
        from erp.core import get_warehouse
        with self.assertRaises(PermissionDenied):
            get_warehouse(Context(self.user, self.business), self.store.id)

    def test_internal_charge_adjustment_preserves_company_accounts(self):
        self.open_material("100", "2000")
        transfer = self.post("transfer_dispatch", warehouse=self.store.pk, destination=self.branch.pk, internal_charge="3000", lines=[{"product":self.raw.pk,"quantity":"100"}])
        from erp.operations import internal_charge_total
        adjustment = self.post("internal_charge_adjust", transfer=transfer.pk, amount="-500", reason="Returned or repriced goods approved")
        self.assertEqual(internal_charge_total(transfer),D("2500"))
        self.assertFalse(Entry.objects.filter(document=adjustment).exists())
        self.assertFalse(StockMovement.objects.filter(document=adjustment).exists())
        self.assertEqual(D(adjustment.result["remaining_internal_charge"]),D("2500"))
        with self.assertRaises(ValidationError):
            self.post("internal_charge_adjust", transfer=transfer.pk, amount="-3000", reason="Cannot make negative internal debt")
        self.assertEqual(internal_charge_total(transfer),D("2500"))

    def test_bom_snapshot_optional_only_in_enabled_business(self):
        self.open_material("10", "100")
        bom = BOM.objects.create(business=self.business, product=self.adhesive, name="Synthetic BOM", version=1, approved=True, output_quantity="10", components=[{"product": self.raw.id, "quantity": "2"}])
        with self.assertRaises(ValidationError):
            self.post("production_bom", warehouse=self.store.id, bom=bom.id, outputs=[{"product": self.adhesive.id, "quantity": "10"}], inputs=[{"product": self.raw.id, "quantity": "2"}])
        self.business.manufacturing_mode = "bom"
        self.business.save(update_fields=["manufacturing_mode"])
        batch = self.post("production_bom", warehouse=self.store.id, bom=bom.id, planned_quantity="20", inputs=[{"product": self.raw.id, "quantity": "5"}], outputs=[{"product": self.adhesive.id, "quantity": "20"}])
        self.assertEqual(D(batch.result["bom"]["expected"][0]["quantity"]), D("4"))
        self.assertEqual(D(batch.result["inputs"][0]["quantity"]), D("5"))
        bom.components = [{"product": self.raw.id, "quantity": "3"}]
        bom.save()
        batch.refresh_from_db()
        self.assertEqual(D(batch.result["bom"]["expected"][0]["quantity"]), D("4"))

    def test_idempotency_and_conflicting_retries(self):
        block = self.open_block()
        payload = {"warehouse": self.store.id, "lines": [{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}]}
        first = execute(Context(self.user, self.business), "sale", payload, "specific-immutable-key")
        second = execute(Context(self.user, self.business), "sale", payload, "specific-immutable-key")
        self.assertEqual(first.id, second.id)
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("978"))
        with self.assertRaises(ValidationError):
            execute(Context(self.user, self.business), "sale", {**payload, "paid": "1"}, "specific-immutable-key")

    def test_failure_late_in_sale_rolls_back_earlier_cut_and_new_customer(self):
        block = self.open_block()
        docs, movements, parties = Document.objects.count(), StockMovement.objects.count(), Party.objects.count()
        with self.assertRaises(ValidationError):
            self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}, {"product": self.adhesive.id, "quantity": "999"}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("1000"))
        self.assertEqual(Document.objects.count(), docs)
        self.assertEqual(StockMovement.objects.count(), movements)
        self.assertEqual(Party.objects.count(), parties)

    def test_cross_business_product_reference_rejected(self):
        other = Business.objects.create(name="Furniture", slug="furniture-test")
        foreign = Product.objects.create(business=other, code="FURN", name="Chair", kind="finished", unit="each")
        with self.assertRaises(ValidationError):
            self.post("stock_opening", warehouse=self.store.id, lines=[{"product": foreign.id, "quantity": "1", "value": "100"}])

    def test_unapproved_price_override_denies_and_rolls_back_stock(self):
        block = self.open_block()
        Membership.objects.filter(user=self.user, business=self.business).update(permissions=["sales.post", "sales.credit"])
        with self.assertRaises(PermissionDenied):
            self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22", "unit_price": "100"}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("1000"))

    def test_tax_is_effective_dated_snapshot_and_posted_documents_immutable(self):
        block = self.open_block()
        rule = TaxRule.objects.create(business=self.business, name="Synthetic 10 percent", rate="10", effective_from=date(2026, 1, 1))
        invoice = self.post("sale", warehouse=self.store.id, tax_rule=rule.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}])
        self.assertEqual(invoice.amount, D("1210"))
        rule.rate = D("20")
        rule.save()
        invoice.refresh_from_db()
        self.assertEqual(invoice.result["tax"]["rate"], "10.000000")
        invoice.amount = D("1")
        with self.assertRaises(ValidationError):
            invoice.save()
        self.assert_journal_balanced(invoice)

    def test_stock_backdating_rejected(self):
        self.open_material()
        with self.assertRaises(ValidationError):
            self.post("stock_adjust", date="2026-10-27", warehouse=self.store.id, product=self.raw.id, quantity="-1", reason="Synthetic correction")
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("1000"))

    def test_operational_reports_redact_cost_and_consumption(self):
        from erp.operations import manufacturing_report
        self.open_material("10", "100")
        self.post("production", warehouse=self.store.id, inputs=[{"product": self.raw.id, "quantity": "5"}], outputs=[{"product": self.adhesive.id, "quantity": "5"}])
        Membership.objects.filter(user=self.user, business=self.business).update(permissions=["production.view", "inventory.view"])
        ctx = Context(self.user, self.business)
        report = manufacturing_report(ctx, "production_batches")
        self.assertEqual(len(report["rows"]), 1)
        self.assertNotIn("inputs", report["rows"][0])
        self.assertNotIn("total_cost", report["rows"][0])
        self.assertNotIn("cost", report["rows"][0]["outputs"][0])
        movements = manufacturing_report(ctx, "stock_movements")
        self.assertTrue(movements["rows"])
        self.assertTrue(all(row["product"] != self.raw.id for row in movements["rows"]))
        self.assertTrue(all("value" not in row for row in movements["rows"]))

    def test_fractional_mm_precision_and_negative_loss_fail_without_mutation(self):
        block = self.open_block()
        for thickness, loss in [("22.0001", "0"), ("22", "0.0001"), ("22", "-1")]:
            with self.assertRaises(ValidationError):
                self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": thickness, "cutting_loss_mm": loss}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("1000"))

    def test_cm_entry_and_persian_numerals_are_exact(self):
        block = self.open_block()
        invoice = self.post("sale", warehouse=self.store.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_cm": "۲٫۲"}])
        self.assertEqual(invoice.amount, D("1100"))
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("978"))

    def test_purchase_order_partially_received_with_no_order_stock_posting(self):
        order = self.post("purchase_order", warehouse=self.store.id, supplier=self.supplier.id, lines=[{"product": self.raw.id, "quantity": "10", "unit_cost": "10"}])
        self.assertEqual(order.amount, D("100"))
        self.assertFalse(order.movements.exists())
        self.assertFalse(order.entries.exists())
        self.post("purchase_receive", warehouse=self.store.id, supplier=self.supplier.id, order=order.id, lines=[{"product": self.raw.id, "quantity": "4", "unit_cost": "10"}])
        self.post("purchase_receive", warehouse=self.store.id, supplier=self.supplier.id, order=order.id, lines=[{"product": self.raw.id, "quantity": "6", "unit_cost": "10"}])
        with self.assertRaises(ValidationError):
            self.post("purchase_receive", warehouse=self.store.id, supplier=self.supplier.id, order=order.id, lines=[{"product": self.raw.id, "quantity": "1", "unit_cost": "10"}])
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("10"))

    def test_sales_order_partial_delivery_and_remaining_cancellation(self):
        block = self.open_block()
        quote = self.post("quotation", warehouse=self.store.id, party=self.customer.id, lines=[{"product": self.sponge.id, "quantity": "5"}])
        order = self.post("sales_order", warehouse=self.store.id, party=self.customer.id, quotation=quote.id, lines=[{"product": self.sponge.id, "quantity": "5"}])
        self.assertFalse(order.entries.exists())
        invoice = self.post("sale", warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}])
        self.assertEqual(invoice.result["order"], order.id)
        self.assertEqual(invoice.result["lines"][0]["order_index"], 0)
        self.post("order_cancel", order=order.id, reason="Customer cancelled the unfulfilled remainder")
        with self.assertRaises(ValidationError):
            self.post("sale", warehouse=self.store.id, party=self.customer.id, order=order.id, lines=[{"product": self.sponge.id, "block": block.id, "thickness_mm": "28"}])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("978"))


class ConcurrentManufacturingTests(Factory, TransactionTestCase):
    reset_sequences = True

    def test_two_cashiers_cannot_sell_the_same_22_mm(self):
        block = self.open_block(height="30", value="300")
        barrier = Barrier(2)

        def compete(key):
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                business = Business.objects.get(pk=self.business.pk)
                barrier.wait(timeout=10)
                execute(Context(user, business), "sale", {"date": "2026-10-28", "warehouse": self.store.id, "lines": [{"product": self.sponge.id, "block": block.id, "thickness_mm": "22"}]}, key)
                return "success"
            except ValidationError:
                return "insufficient"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            result = list(executor.map(compete, ["concurrent-a", "concurrent-b"]))
        self.assertCountEqual(result, ["success", "insufficient"])
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("8"))
        self.assertEqual(Document.objects.filter(kind="sale", state="posted").count(), 1)
