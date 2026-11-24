from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from erp.core import Context, execute
from erp.models import Document, Membership, StockMovement
from erp.tests.test_manufacturing import Factory


D = Decimal


class StockCountTests(Factory, TestCase):
    def test_count_is_immutable_nonfinancial_evidence_then_shortage_adjustment(self):
        self.open_material("100", "1000")
        movements = StockMovement.objects.count()
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "97.5"}])
        self.assertFalse(count.entries.exists())
        self.assertFalse(count.movements.exists())
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("100"))
        self.assertEqual(StockMovement.objects.count(), movements)
        self.assertEqual(count.result["lines"][0]["variance"], "-2.500000")
        adjustment = self.post("stock_count_adjust", count=count.pk, reason="Approved physical shortage")
        self.assertEqual(adjustment.reference_id, count.pk)
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("97.5"))
        self.assertEqual(self.pool(self.raw, profile="").value, D("975"))
        self.assertEqual(adjustment.amount, D("25"))
        self.assert_journal_balanced(adjustment)
        count.refresh_from_db()
        self.assertEqual(count.result["lines"][0]["expected_quantity"], "100.000000")
        with self.assertRaises(ValidationError):
            self.post("stock_count_adjust", count=count.pk, reason="Cannot adjust twice")

    def test_surplus_uses_average_or_requires_value_for_an_empty_pool(self):
        self.open_material("100", "1000")
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "102"}])
        self.post("stock_count_adjust", count=count.pk, reason="Approved measured surplus")
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("102"))
        self.assertEqual(self.pool(self.raw, profile="").value, D("1020"))
        empty_count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.adhesive.pk, "counted_quantity": "5"}])
        with self.assertRaises(ValidationError):
            self.post("stock_count_adjust", count=empty_count.pk, reason="Found unrecorded finished stock")
        self.post("stock_count_adjust", count=empty_count.pk, reason="Approved independently valued found stock", values={"0": "100"})
        self.assertEqual(self.pool(self.adhesive, profile="").value, D("100"))

    def test_stock_event_after_observation_requires_recount(self):
        self.open_material("100", "1000")
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "99"}])
        self.post("material_issue", warehouse=self.store.pk, destination=self.floor.pk, lines=[{"product": self.raw.pk, "quantity": "10"}])
        before = StockMovement.objects.count()
        with self.assertRaises(ValidationError):
            self.post("stock_count_adjust", count=count.pk, reason="Stale count cannot overwrite movement")
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("90"))
        self.assertEqual(StockMovement.objects.count(), before)

    def test_block_count_preserves_quality_hold_and_original_measured_height(self):
        block = self.open_block()
        block.status = "inspection"
        block.save(update_fields=["status"])
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.sponge.pk, "block": block.pk, "counted_height_mm": "978"}])
        adjustment = self.post("stock_count_adjust", count=count.pk, reason="Confirmed measured block height")
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("978"))
        self.assertEqual(block.initial_height_mm, D("1000"))
        self.assertEqual(block.status, "inspection")
        self.assertEqual(self.pool().quantity, D("97.8"))
        self.assertEqual(self.pool().value, D("9780"))
        self.assert_journal_balanced(adjustment)

    def test_block_reservation_change_after_observation_invalidates_count(self):
        block = self.open_block()
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.sponge.pk, "block": block.pk, "counted_height_mm": "978"}])
        self.post("reserve", lines=[{"block": block.pk, "thickness_mm": "22"}])
        with self.assertRaises(ValidationError):
            self.post("stock_count_adjust", count=count.pk, reason="Reservations changed")
        block.refresh_from_db()
        self.assertEqual(block.remaining_height_mm, D("1000"))

    def test_multiple_block_variances_in_same_pool_reconcile_together(self):
        first, second = self.open_block(), self.open_block()
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.sponge.pk, "block": first.pk, "counted_height_mm": "990"}, {"product": self.sponge.pk, "block": second.pk, "counted_height_mm": "980"}])
        adjusted = self.post("stock_count_adjust", count=count.pk, reason="Two measured block variances")
        self.assertEqual(self.pool().quantity, D("197"))
        self.assertEqual(self.pool().value, D("19700"))
        self.assertEqual(adjusted.amount, D("300"))
        self.assert_journal_balanced(adjusted)

    def test_count_does_not_allow_fractional_pieces_or_duplicate_blocks(self):
        with self.assertRaises(ValidationError):
            self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.trim.pk, "counted_quantity": "1.5"}])
        block = self.open_block()
        with self.assertRaises(ValidationError):
            self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.sponge.pk, "block": block.pk, "counted_height_mm": "999"}, {"product": self.sponge.pk, "block": block.pk, "counted_height_mm": "998"}])

    def test_count_permissions_separate_observation_from_adjustment(self):
        self.open_material("100", "1000")
        Membership.objects.filter(user=self.user, business=self.business).update(permissions=["inventory.count","inventory.raw"])
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "99"}])
        with self.assertRaises(PermissionDenied):
            self.post("stock_count_adjust", count=count.pk, reason="Counter is not authorized to adjust")
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("100"))

    def test_no_variance_cannot_create_a_spurious_financial_document(self):
        self.open_material("100", "1000")
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "100"}])
        with self.assertRaises(ValidationError):
            self.post("stock_count_adjust", count=count.pk, reason="No adjustment required")
        self.assertEqual(Document.objects.filter(kind="stock_count_adjust").count(), 0)

    def test_stock_count_adjustment_retry_does_not_apply_variance_twice(self):
        self.open_material("100", "1000")
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "99"}])
        payload = {"date": "2026-10-28", "count": count.pk, "reason": "Approved discrepancy"}
        first = execute(Context(self.user, self.business), "stock_count_adjust", payload, "count-reconcile-once")
        retry = execute(Context(self.user, self.business), "stock_count_adjust", payload, "count-reconcile-once")
        self.assertEqual(first.pk, retry.pk)
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("99"))

    def test_late_adjustment_error_rolls_back_earlier_variance(self):
        self.open_material("100", "1000")
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "99"}, {"product": self.adhesive.pk, "counted_quantity": "5"}])
        movements = StockMovement.objects.count()
        with self.assertRaises(ValidationError):
            self.post("stock_count_adjust", count=count.pk, reason="Missing approved value for the second line")
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("100"))
        self.assertEqual(self.pool(self.raw, profile="").value, D("1000"))
        self.assertEqual(StockMovement.objects.count(), movements)
        self.assertEqual(Document.objects.filter(kind="stock_count_adjust").count(), 0)

    def test_same_balance_after_intervening_round_trip_still_requires_recount(self):
        self.open_material("100", "1000")
        count = self.post("stock_count", warehouse=self.store.pk, lines=[{"product": self.raw.pk, "counted_quantity": "99"}])
        self.post("material_issue", warehouse=self.store.pk, destination=self.floor.pk, lines=[{"product": self.raw.pk, "quantity": "10"}])
        self.post("material_return", warehouse=self.floor.pk, destination=self.store.pk, lines=[{"product": self.raw.pk, "quantity": "10"}])
        self.assertEqual(self.pool(self.raw, profile="").quantity, D("100"))
        self.assertEqual(self.pool(self.raw, profile="").value, D("1000"))
        with self.assertRaises(ValidationError):
            self.post("stock_count_adjust", count=count.pk, reason="Intervening movements invalidate evidence")
