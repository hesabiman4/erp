from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from erp.core import Context
from erp.labels import block_label
from erp.models import Business, Membership, Product,UserPreference
from erp.tests.test_manufacturing import Factory


class BlockLabelTests(Factory, TestCase):
    def test_label_has_exact_geometry_and_grade_is_only_a_name(self):
        block = self.open_block()
        self.post("sale", warehouse=self.store.pk, lines=[{"product": self.sponge.pk, "block": block.pk, "thickness_mm": "22"}])
        html = block_label(Context(self.user, self.business), block.pk)
        self.assertIn("اسفنج 45 کیلو گرام", html)
        self.assertIn("2000 × 1000 × 1000 mm", html)
        self.assertIn("978 mm = 97.8 cm", html)
        self.assertIn('data-field="available-height">97.8 cm', html)
        self.assertIn("<svg", html)
        self.assertIn("<path", html)
        self.assertNotIn("45 kg", html)
        self.assertNotIn("Actual weight", html)
        self.assertNotIn("COGS", html)
        self.assertIn(self.store.name, html)
        self.assertIn(block.code, html)

    def test_all_label_text_is_html_escaped(self):
        block = self.open_block()
        block.code = '<script>alert("bad")</script>'
        block.save(update_fields=["code"])
        self.sponge.name = '<img src=x onerror="bad()">'
        self.sponge.save(update_fields=["name"])
        self.store.name = '<iframe src="bad"></iframe>'
        self.store.save(update_fields=["name"])
        html = block_label(Context(self.user, self.business), block.pk)
        self.assertNotIn("<script", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<iframe", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;img", html)
        self.assertIn("&lt;iframe", html)

    def test_label_requires_inventory_view_permission(self):
        block = self.open_block()
        Membership.objects.filter(user=self.user, business=self.business).update(permissions=["sales.post"])
        with self.assertRaises(PermissionDenied):
            block_label(Context(self.user, self.business), block.pk)

    def test_label_denies_other_business_and_location(self):
        block = self.open_block()
        other = Business.objects.create(name="Furniture", slug="labels-furniture")
        Membership.objects.create(business=other, user=self.user, permissions=["inventory.view"], all_locations=True, product_lines=["sponge", "adhesive", "shared"])
        with self.assertRaises(ValidationError):
            block_label(Context(self.user, other), block.pk)
        Membership.objects.filter(user=self.user, business=self.business).update(all_locations=False, location_ids=[self.kabul.pk])
        with self.assertRaises(PermissionDenied):
            block_label(Context(self.user, self.business), block.pk)

    def test_product_line_scope_is_checked_for_block_label(self):
        block = self.open_block()
        Membership.objects.filter(user=self.user, business=self.business).update(product_lines=["adhesive"])
        with self.assertRaises(PermissionDenied):
            block_label(Context(self.user, self.business), block.pk)

    def test_held_or_reserved_stock_never_prints_false_available_height(self):
        block = self.open_block()
        self.post("reserve", lines=[{"block": block.pk, "thickness_mm": "22"}])
        html = block_label(Context(self.user, self.business), block.pk)
        self.assertIn('data-field="available-height">97.8 cm', html)
        block.refresh_from_db()
        block.status = "inspection"
        block.save(update_fields=["status"])
        html = block_label(Context(self.user, self.business), block.pk)
        self.assertIn('data-field="available-height">0 cm', html)

    def test_curing_label_explains_physical_height_without_releasing_stock(self):
        block=self.open_block()
        block.status='curing';block.save(update_fields=['status'])
        html=block_label(Context(self.user,self.business),block.pk)
        self.assertIn('1000 mm = 100 cm',html)
        self.assertIn('data-field="available-height">0 cm',html)
        self.assertIn('data-field="availability-reason"',html)
        self.assertIn('آزادسازی',html)
        block.refresh_from_db();self.assertEqual(block.status,'curing')
        with self.assertRaises(ValidationError):
            self.post('sale',warehouse=self.store.pk,lines=[{'product':self.sponge.pk,'block':block.pk,'thickness_mm':'22'}])

    def test_translated_warehouse_name_is_escaped_and_not_concatenated(self):
        block=self.open_block()
        self.store.name_fa='گدام اصلی';self.store.name_en='Main <warehouse>';self.store.save()
        html=block_label(Context(self.user,self.business),block.pk,'en')
        self.assertIn('Main &lt;warehouse&gt;',html)
        self.assertNotIn('Main <warehouse>',html)
        UserPreference.objects.update_or_create(user=self.user,defaults={'language':'fa','calendar':'jalali'})
        self.client.force_login(self.user)
        response=self.client.get(f'/api/blocks/{block.pk}/label/',HTTP_X_BUSINESS_ID=str(self.business.pk),HTTP_ACCEPT_LANGUAGE='en-US')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'گدام اصلی')
        self.assertNotContains(response,'Main &lt;warehouse&gt;')

    def test_qr_payload_contains_identifier_only_not_cost_or_formula(self):
        block = self.open_block()
        import qrcode
        original = qrcode.QRCode.add_data
        captured = []
        def record(instance, data, *args, **kwargs):
            captured.append(data)
            return original(instance, data, *args, **kwargs)
        with patch("erp.labels.qrcode.QRCode.add_data", record):
            block_label(Context(self.user, self.business), block.pk)
        import json
        payload = json.loads(captured[0])
        self.assertEqual(payload, {"type": "erp-block", "version": 1, "business": self.business.pk, "block": block.pk, "code": block.code})
        self.assertNotIn("cost", payload)
        self.assertNotIn("inputs", payload)
