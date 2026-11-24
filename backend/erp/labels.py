"""Private, printable physical-block labels with locally generated SVG QR codes.

The QR contains an inventory identifier, never a public download URL or an
authorization token. Its decoded content still requires normal business access.
"""
import json
from decimal import Decimal

import qrcode
from qrcode.image.svg import SvgPathImage
from django.utils.html import escape

from .core import get_obj, get_product, get_warehouse
from .models import Block


def number(value):
    """Keep exact measurements legible without changing their numeric meaning."""
    formatted = format(Decimal(value), "f")
    return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted


def block_label(ctx, block_id, language='fa'):
    ctx.require("inventory.view")
    block = get_obj(ctx, Block, block_id)
    product = get_product(ctx, block.product_id)
    warehouse = get_warehouse(ctx, block.warehouse_id)
    # Printing an inventory label permits the batch reference, not production
    # inputs or the source batch's confidential financial document.
    batch_number = block.batch.number if block.batch_id and block.batch.business_id == ctx.business.pk else "—"
    payload = json.dumps({"type": "erp-block", "version": 1, "business": ctx.business.pk, "block": block.pk, "code": block.code}, ensure_ascii=False, separators=(",", ":"))
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=8, image_factory=SvgPathImage)
    qr.add_data(payload)
    qr.make(fit=True)
    # SVG is produced entirely by the trusted library. Every user-controlled
    # visible field below is escaped separately; QR payload is encoded modules.
    svg = qr.make_image().to_string(encoding="unicode")
    statuses = {
        "ready": "آماده / Ready", "reserved": "رزرو / Reserved",
        "curing": "مرحله استراحت / Curing", "inspection": "بررسی / Inspection",
        "in_transit": "در مسیر / In transit", "exhausted": "تمام شده / Exhausted",
        "damaged": "آسیب دیده / Damaged",
    }
    e = lambda value: str(escape(str(value)))
    unreserved = max(Decimal("0"), block.remaining_height_mm - block.reserved_height_mm) / 10
    available = unreserved if block.status in ("ready", "reserved") else Decimal("0")
    reasons={
        'curing':'بلوک در حال عمل‌آوری است؛ پس از تکمیل عمل‌آوری، بررسی کیفیت و اصلاح لازم، آزادسازی مجاز را ثبت کنید. / Curing: complete physical curing, required trimming and authorized quality release before sale.',
        'inspection':'بلوک تحت بررسی کیفیت است؛ تأیید مجاز کیفیت لازم است. / Quality inspection: authorized release is required.',
        'hold':'بلوک تحت نگهداشت کیفیت است؛ تأیید مجاز کیفیت لازم است. / Quality hold: authorized release is required.',
        'in_transit':'انتقال هنوز در مسیر است؛ دریافت مقصد باید تأیید شود. / In transit: destination receipt is required.',
        'damaged':'بلوک آسیب دیده است؛ پیش از فروش، بررسی و عملیات مجاز لازم است. / Damaged: review and an authorized operation are required.',
        'exhausted':'ارتفاع قابل استفاده باقی نمانده است. / No usable height remains.',
    }
    reason='' if available>0 else reasons.get(block.status,'ارتفاع آزاد قابل فروش نیست؛ رزروها و وضعیت بلوک را بررسی کنید. / No saleable free height: review reservations and block status.')
    from .master_names import language_name
    return f'''<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(block.code)} — برچسب بلوک</title>
<style>
@page{{size:A6 landscape;margin:7mm}}
*{{box-sizing:border-box}}body{{margin:0;background:#edf1f5;color:#162336;font-family:Tahoma,Arial,sans-serif;line-height:1.45}}
.instructions{{max-width:150mm;margin:20px auto;text-align:center;font-size:13px}}
.label{{width:134mm;min-height:90mm;margin:20px auto;background:#fff;border:1px solid #263a50;border-radius:5px;padding:5mm;break-inside:avoid}}
.head{{border-bottom:2px solid #263a50;padding-bottom:3mm;margin-bottom:3mm}}.business{{font-size:11px;color:#40536b}}h1{{font-size:19px;margin:1mm 0}}.code{{font:700 17px monospace;direction:ltr;unicode-bidi:isolate;overflow-wrap:anywhere}}
.body{{display:flex;align-items:flex-start;gap:5mm}}.details{{flex:1;min-width:0}}.qr{{width:35mm;min-width:35mm;direction:ltr;background:#fff}}.qr svg{{display:block;width:35mm;height:35mm}}
dl{{margin:0;display:grid;grid-template-columns:auto 1fr;gap:1.8mm 3mm;font-size:12px}}dt{{color:#40536b}}dd{{margin:0;overflow-wrap:anywhere}}.measure{{direction:ltr;unicode-bidi:isolate;text-align:end;font-weight:bold}}.foot{{font-size:9px;color:#40536b;border-top:1px solid #dce2e9;margin-top:3mm;padding-top:2mm}}
@media print{{body{{background:#fff}}.instructions{{display:none}}.label{{margin:0;border-radius:0;width:100%;min-height:0}}}}
</style></head><body>
<p class="instructions">برای چاپ از فرمان چاپ مرورگر استفاده کنید. / Print with the browser’s print command.</p>
<article class="label" aria-label="برچسب بلوک / Physical block label">
<header class="head"><div class="business">{e(ctx.business.name)}</div><h1>{e(product.name)}</h1><div class="code">{e(block.code)}</div></header>
<div class="body"><div class="details"><dl>
<dt>ابعاد ثبت اولیه / Initial</dt><dd class="measure" data-field="initial-dimensions">{e(number(block.length_mm))} × {e(number(block.width_mm))} × {e(number(block.initial_height_mm))} mm</dd>
<dt>ارتفاع باقی / Remaining</dt><dd class="measure" data-field="remaining-height">{e(number(block.remaining_height_mm))} mm = {e(number(block.remaining_height_mm / 10))} cm</dd>
<dt>قابل فروش / Available</dt><dd class="measure" data-field="available-height">{e(number(available))} cm</dd>
<dt>رزروشده / Reserved</dt><dd class="measure" data-field="reserved-height">{e(number(block.reserved_height_mm / 10))} cm</dd>
<dt>انبار / Warehouse</dt><dd>{e(language_name(warehouse,language))} · {e(language_name(warehouse.location,language))}</dd>
<dt>بچ / Batch</dt><dd dir="auto">{e(batch_number)}</dd>
<dt>وضعیت / Status</dt><dd>{e(statuses.get(block.status, block.status))}</dd>
</dl></div><div class="qr" aria-label="QR inventory identifier">{svg}</div></div>
{f'<p class="foot" data-field="availability-reason">{e(reason)}</p>' if reason else ''}
<div class="foot">QR: شناسه بلوک؛ دسترسی نیاز به ورود و اجازه دارد. پس از برش، ارتفاع تغییر می‌کند؛ برچسب تازه چاپ کنید.<br>Inventory identifier; normal access is required. Reprint after cutting. Product grade text is a name, not measured mass.</div>
</article></body></html>'''
