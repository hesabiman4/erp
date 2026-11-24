"""Presentation for private documents; only permission-filtered data enters totals.

This module does not post, mutate documents or recompute selling/carrying costs.
The staff API supplies document_data(), while the customer portal supplies its
explicitly restricted invoice projection. Browser printing retains native RTL.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .localization import printed_date
from .models import Account, Product


TITLES = {
    'crm_create': ('فرصت فروش جدید','Sales opportunity'),
    'crm_transition': ('تغییر مرحله فرصت','Opportunity stage review'),
    'crm_assign': ('تعیین مسؤول فروش','Salesperson assignment'),
    'crm_activity': ('پیگیری فروش','Sales follow-up'),
    'crm_activity_done': ('نتیجه پیگیری فروش','Follow-up outcome'),
    'crm_note': ('یادداشت فرصت فروش','Opportunity note'),
    'crm_quote': ('نرخ‌دهی متصل به فرصت','Opportunity quotation link'),
    'capture_import': ('اصل سند برای بررسی','Captured source evidence'),
    'capture_review': ('بررسی سند و مسوده','Source review and draft'),
    'capture_reject': ('رد اصل سند','Source rejection'),
    'cash_drawer': ('ثبت صندوق محل', 'Location cash drawer'),
    'cash_shift_open': ('آغاز نوبت صندوق', 'Cash shift opened'),
    'cash_shift_count': ('شمارش ختم نوبت', 'Cash shift count'),
    'cash_shift_recount': ('شمارش دوباره صندوق', 'Cash shift recount'),
    'cash_shift_review': ('بررسی تفاوت صندوق', 'Cash variance review'),
    'cash_handover': ('تحویل مسئولیت صندوق', 'Cash custody handover'),
    'cash_handover_redirect': ('تغییر تحویل‌گیرنده', 'Pending handover reassigned'),
    'statement_import': ('ورود صورت‌حساب', 'Statement evidence import'),
    'statement_review': ('بررسی سطر صورت‌حساب', 'Statement row review'),
    'statement_reconcile': ('تطبیق صورت‌حساب بانک', 'Bank statement reconciled'),
    'rfq_create': ('درخواست نرخ خرید', 'Supplier quotation request'),
    'rfq_offer': ('پیشنهاد تأمین‌کننده', 'Supplier offer'),
    'rfq_award': ('انتخاب پیشنهاد خرید', 'Supplier offer awarded'),
    'rfq_close': ('ختم درخواست نرخ خرید', 'Quotation request closed'),
    'calendar_policy': ('تنظیم تقویم دوره\u200cهای کاری', 'Business calendar policy'),
    'capacity_schedule': ('رزرو ظرفیت مراحل تولید', 'Production capacity reservation'),
    'capacity_work_order': ('برنامه چندروزه تولید', 'Multi-day production plan'),
    'closing_open': ('آغاز بررسی ختم دوره', 'Closing cycle opened'),
    'closing_review': ('بررسی حساب\u200cهای دوره', 'Period review'),
    'closing_finish': ('ختم و قفل دوره', 'Period finalized'),
    'portal_listing': ('محصولات مجاز مشتری', 'Customer published item'),
    'portal_review': ('بررسی درخواست مشتری', 'Customer request review'),
    'notice_prepare': ('آماده\u200cسازی پیام مشتری', 'Customer update prepared'),
    'notice_status': ('نتیجه پیام مشتری', 'Customer update outcome'),
    'notice_retry': ('اجازه تلاش دوباره پیام', 'Message retry authorization'),
    'supplier_claim': ('ادعای کمبود یا خرابی تأمین\u200cکننده', 'Supplier discrepancy claim'),
    'supplier_claim_resolve': ('حل ادعای تأمین\u200cکننده', 'Supplier claim resolution'),
    'cycle_count_assign': ('تعیین مسئول شمارش انبار', 'Stock count assignment'),
    'cycle_count_record': ('ثبت مشاهده شمارش انبار', 'Physical count observation'),
    'cycle_count_review': ('بررسی تفاوت شمارش انبار', 'Stock count review'),
    'weighing_device': ('ثبت ترازو', 'Weighing device registration'),
    'scale_calibrate': ('بررسی کالیبراسیون ترازو', 'Scale calibration evidence'),
    'weight_measure': ('ثبت وزن خالص تأییدشده', 'Confirmed net weight'),
    'measured_receive': ('رسید خرید با وزن خالص', 'Measured goods receipt'),

    'commission_policy': ('قاعده کمیشن فروش','Commission policy'),
    'commission_accrue': ('ورق کمیشن کسب‌شده','Commission earnings'),
    'commission_reverse': ('برگشت کمیشن پرداخت‌نشده','Unpaid commission reversed'),
    'late_cost_bill': ('ثبت بل مصارف دیررس','Late supplier cost bill'),
    'late_cost_allocate': ('تخصیص مصارف دیررس','Late-cost allocation'),
    'late_cost_wip': ('بهای اضافی تولید در جریان','Additional WIP cost'),
    'transport_vehicle': ('ثبت موتر','Vehicle registration'), 'transport_driver': ('ثبت راننده','Driver registration'),
    'delivery_trip': ('برنامه سفر تحویل','Delivery trip'), 'delivery_load': ('لست بارگیری','Loading list'),
    'delivery_depart': ('سند حرکت موتر','Trip departure'), 'delivery_acknowledge': ('رسید تحویل قسمی','Partial delivery acknowledgement'),
    'delivery_dispute_resolve': ('حل اختلاف تحویل','Delivery discrepancy resolved'), 'delivery_close': ('ختم سفر','Trip completed'),
    'delivery_cancel': ('لغو سفر','Trip cancelled'), 'quality_claim': ('شکایت کیفیت مشتری','Customer quality claim'),
    'quality_claim_review': ('بررسی شکایت کیفیت','Quality claim review'), 'quality_claim_close': ('ختم شکایت کیفیت','Quality claim closure'),
    'quality_recall': ('فراخوان کیفیت','Quality recall'), 'quality_recall_close': ('ختم فراخوان کیفیت','Quality recall closed'),
    'job_project': ('پروژه مشتری','Customer project'), 'job_estimate': ('برآورد بهای پروژه','Project estimate'),
    'job_document': ('اسناد مربوط پروژه','Project document association'), 'job_bom_plan': ('نیازمندی فرمول پروژه','Project BOM requirements'),
    'job_subcontract': ('کار پیمانکار','Subcontract job'), 'job_subcontract_link': ('اسناد واقعی پیمانکار','Subcontract source association'),
    'job_subcontract_close': ('ختم کار پیمانکار','Subcontract completed'), 'job_close': ('ختم پروژه','Project completed'),
    'fx_deposit': ('اعتبار پولی ارزی قابل استرداد','Refundable foreign monetary credit'),
    'fx_deposit_allocate': ('تخصیص اعتبار ارزی','Foreign credit allocation'), 'fx_refund': ('رسید استرداد اعتبار ارزی','Foreign credit refund'),
    'fx_settlement_reverse': ('برگشت تسویه ارزی','Foreign settlement reversal'), 'fx_credit': ('تخفیف اصلاحی بل ارزی','Foreign price credit'),
    'fx_deposit_revalue': ('تجدید ارزش اعتبار ارزی','Foreign credit revaluation'),
    'sale': ('بل فروش', 'Sales invoice'), 'quotation': ('نرخ‌نامه پیشنهادی', 'Quotation'),
    'sales_order': ('سفارش فروش', 'Sales order'), 'purchase_order': ('سفارش خرید', 'Purchase order'),
    'order_cancel': ('لغو مانده سفارش / نرخ‌نامه', 'Cancellation record'),
    'receipt': ('رسید دریافت پول', 'Payment receipt'),
    'supplier_payment': ('رسید پرداخت به تأمین‌کننده', 'Supplier payment'),
    'payment_reverse': ('سند برگشت پرداخت', 'Payment reversal'),
    'customer_refund': ('رسید بازپرداخت به مشتری', 'Customer refund'),
    'supplier_refund': ('رسید برگشت پول تأمین‌کننده', 'Supplier refund'),
    'allocate_deposit': ('تخصیص پیش‌پرداخت', 'Deposit allocation'),
    'purchase_receive': ('رسید ورود خرید', 'Goods received'), 'purchase_bill': ('بل خرید', 'Supplier bill'),
    'purchase_return': ('برگشت خرید', 'Purchase return'), 'sales_return': ('برگشت فروش', 'Credit note'),
    'transfer_dispatch': ('سند ارسال انتقال', 'Stock dispatch'), 'transfer_receive': ('سند دریافت انتقال', 'Stock receipt'),
    'transfer_resolve': ('سند تصفیه انتقال', 'Transfer resolution'),
    'internal_settlement': ('تصفیه داخلی شعبه', 'Internal settlement'),
    'payroll_accrue': ('ورق معاش و مزد', 'Payslip'), 'payroll_settle': ('رسید پرداخت معاش', 'Payroll settlement'),
    'employee_advance': ('رسید پیش‌پرداخت به کارمند', 'Employee advance'),
    'production': ('گزارش تولید', 'Production record'), 'production_bom': ('گزارش تولید با فرمول', 'BOM production'),
    'production_start': ('آغاز تولید', 'Production started'), 'production_consume': ('مصرف مواد تولید', 'Production consumption'),
    'production_complete': ('تکمیل تولید', 'Production completion'), 'production_material_return': ('برگشت مواد از تولید', 'WIP material return'),
    'material_issue': ('صدور مواد به تولید', 'Material issue'), 'material_return': ('برگشت مواد استفاده‌نشده', 'Material return'),
    'trim': ('اصلاح بلوک و محصولات جانبی', 'Block trimming'), 'cut': ('سند برش بلوک', 'Block cutting'),
    'reserve': ('رزرو موجودی', 'Stock reservation'), 'reservation_release': ('آزادسازی رزرو', 'Reservation release'),
    'stock_opening': ('موجودی آغاز دوره', 'Opening inventory'), 'stock_adjust': ('اصلاح موجودی', 'Inventory adjustment'),
    'stock_count': ('شمارش موجودی', 'Inventory count'), 'stock_count_adjust': ('اصلاح پس از شمارش', 'Count adjustment'),
    'expense_post': ('سند مصرف', 'Expense voucher'), 'cash_transfer': ('سند انتقال پول', 'Cash transfer'),
    'cash_count': ('شمارش صندوق', 'Cash count'), 'bank_reconcile': ('تطبیق حساب بانک', 'Bank reconciliation'),
    'opening_receivable': ('طلب آغاز دوره مشتری', 'Opening receivable'), 'opening_payable': ('بدهی آغاز دوره تأمین‌کننده', 'Opening payable'),
    'opening_cash': ('نقد و بانک آغاز دوره', 'Opening cash'), 'opening_employee_advance': ('پیش‌پرداخت آغاز دوره کارمند', 'Opening employee advance'),
    'asset_acquire': ('سند ثبت دارایی ثابت', 'Asset acquisition'), 'asset_depreciate': ('سند استهلاک', 'Depreciation voucher'),
    'journal_adjust': ('سند اصلاحی حسابداری', 'Journal adjustment'), 'receivable_writeoff': ('حذف طلب غیرقابل وصول', 'Receivable write-off'),
    'inventory_write_down': ('کاهش ارزش موجودی', 'Inventory write-down'), 'inventory_write_down_reverse': ('برگشت کاهش ارزش موجودی', 'Write-down reversal'),
    'period_close': ('بستن دوره مالی', 'Period close'), 'period_reopen': ('بازگشایی دوره مالی', 'Period reopened'),
    'calendar_policy': ('تقویم کاری و تاریخ اجرا', 'Business calendar policy'),
    'fx_settle': ('رسید تصفیه ارزی', 'Foreign currency settlement'),
    'fx_exchange': ('سند تبدیل اسعار', 'Currency exchange'), 'fx_revalue': ('تجدید ارزش اسعار', 'Currency revaluation'),
    'fx_remit_dispatch': ('ارسال حواله داخلی', 'Internal remittance dispatched'), 'fx_remit_receive': ('دریافت حواله داخلی', 'Internal remittance received'),
}


def number(value, money=False):
    if value is None or value == '':
        return '—'
    try:
        value = Decimal(str(value))
        if not value.is_finite():
            return '—'
        if money:
            return format(value, ',.2f')
        return format(value, ',f').rstrip('0').rstrip('.') if value % 1 else format(value, ',.0f')
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def context(business, doc, data, user, *, compact=False, copy=False):
    """Build a display context from the authorized projection, never doc.amount.

    In particular, warehouse readers can print production/transfer quantities
    without leaking the original ORM document's redacted carrying amount.
    """
    from .print_settings import profile_for
    profile = profile_for(business)
    result = data.get('result') or {}
    payload = data.get('data') or {}
    display_result = dict(result)
    if doc.kind == 'quotation' and doc.state in {'draft', 'cancelled'}:
        display_result['lines'] = payload.get('lines', [])
    title, english_title = TITLES.get(doc.kind, ('سند عملیاتی', doc.kind.replace('_', ' ').title()))
    # Cash-sale receipts and credit invoices share one authoritative sale.
    # Later collections never rename the original credit invoice.
    if doc.kind == 'sale' and data.get('amount') is not None and Decimal(str(data['amount'])) > 0 and Decimal(str(result.get('paid') or '0')) >= Decimal(str(data['amount'])):
        title, english_title = 'رسید فروش نقدی', 'Cash sales receipt'
    snapshot = result.get('customer_snapshot') or result.get('supplier_snapshot') or result.get('party_snapshot') or {
        'name': doc.party.name if doc.party else '', 'phone': doc.party.phone if doc.party else '',
        'address': doc.party.address if doc.party else '',
    }
    employee = result.get('employee_snapshot') or {}
    if not employee and doc.employee_id:
        # Payroll settlements retain their original earning-profile snapshot.
        employee = (doc.reference.result.get('employee_snapshot') if doc.reference_id else {}) or {'name': doc.employee.name}
    products = {str(p.id): p for p in Product.objects.filter(business=business, pk__in=[
        row.get('product') for key in ('lines', 'inputs', 'outputs') for row in (display_result.get(key) if isinstance(display_result.get(key), list) else [])
        if isinstance(row, dict)
    ])}

    def rows(source):
        records = []
        for index, line in enumerate(source):
            if not isinstance(line, dict):
                continue
            product = products.get(str(line.get('product')))
            records.append({
                'index': index + 1, 'name': line.get('product_name') or (product.name if product else line.get('description', '—')),
                'quantity': number(line.get('quantity')), 'unit': line.get('unit') or (product.unit if product else ''),
                'rate': number(line.get('unit_price', line.get('unit_cost')), True),
                'amount': number(line.get('amount', line.get('credit', line.get('cost'))), True),
                'thickness_mm': number(line.get('thickness_mm')) if line.get('thickness_mm') not in (None, '', 0, '0') else '',
                'sheet_count': number(line.get('sheet_count')), 'length_mm': number(line.get('length_mm')),
                'width_mm': number(line.get('width_mm')), 'discount': number(line.get('discount'), True) if Decimal(str(line.get('discount') or '0'))!=0 else '',
                'block_count': len(line['blocks']) if isinstance(line.get('blocks'), list) else None,
                'show_value': any(key in line for key in ('amount', 'cost', 'credit', 'unit_price', 'unit_cost')),
            })
        return records

    sections = []
    for key, label in [('lines', 'اقلام سند / Document items'), ('outputs', 'محصولات تولیدشده / Production outputs'), ('inputs', 'مواد مصرف‌شده / Materials consumed')]:
        if isinstance(display_result.get(key), list) and display_result[key]:
            items = rows(display_result[key])
            sections.append({'label': label, 'rows': items, 'show_values': any(row['show_value'] for row in items)})
    details = []
    if payload.get('due_date'):
        details.append(('تاریخ سررسید / Due date',printed_date(date.fromisoformat(payload['due_date']),user)))
    if payload.get('payment_terms_days_snapshot') is not None:
        details.append(('مهلت پرداخت (روز) / Payment terms (days)',number(payload['payment_terms_days_snapshot'])))
    journal_rows = []
    if doc.kind == 'journal_adjust' and isinstance(payload.get('lines'), list):
        accounts = {a.code: a for a in Account.objects.filter(business=business, code__in=[row.get('account') for row in payload['lines']])}
        for row in payload['lines']:
            account = accounts.get(row.get('account'))
            journal_rows.append({'account': account.name if account else row.get('account'), 'code': account.number if account else '',
                                 'debit': number(row.get('debit', '0'), True), 'credit': number(row.get('credit', '0'), True)})
    labels = {
        'gross': 'معاش ناخالص / Gross earnings', 'deductions': 'کسورات / Deductions', 'net': 'معاش خالص / Net earnings',
        'period': 'دوره حسابداری / Accounting period', 'rate_used': 'نرخ / Rate', 'approved_hours': 'ساعت تأییدشده / Approved hours',
        'calendar_period': 'ماه قراردادی معاش / Contract earning month', 'period_calendar': 'تقویم قرارداد / Contract calendar',
        'denominator_days': 'روزهای ماه / Full contract period days',
        'approved_days': 'روز تأییدشده / Approved days', 'advance_recovery': 'کسر پیش‌پرداخت / Advance recovery',
        'advance_remaining': 'باقی پیش‌پرداخت / Remaining advance', 'remaining_payable': 'معاش باقی / Remaining wages',
        'outstanding_advance': 'مانده پیش‌پرداخت / Advance balance', 'remaining_internal_charge': 'مانده تصفیه داخلی / Internal balance',
        'earning_from': 'آغاز دوره کار / Earning from', 'earning_through': 'پایان دوره کار / Earning through',
        'rate_basis': 'مبنای نرخ / Rate basis', 'main_height_mm': 'ارتفاع بلوک نهایی (mm) / Finished height',
        'top_height_mm': 'سربلوک (mm) / Top trim', 'bottom_height_mm': 'کف بلوک (mm) / Bottom trim',
        'loss_mm': 'ضایعات برش (mm) / Cutting loss', 'remaining_quantity': 'مقدار باقی انتقال / Transfer remaining',
        'deposit_remaining': 'اعتبار باقی / Remaining credit', 'counted': 'نقد شمارش‌شده / Counted cash',
        'expected': 'مانده ثبت‌شده / Recorded balance', 'variance': 'تفاوت شمارش / Count variance',
        'currency': 'واحد پول ارزی / Foreign currency', 'foreign_amount': 'مبلغ ارز / Foreign amount',
        'functional_cash': 'نقد معادل افغانی / Cash in AFN', 'foreign_remaining': 'مانده ارزی / Remaining foreign amount',
        'rate': 'نرخ تبدیل / Exchange rate', 'exchange_gain': 'سود / زیان اسعار / FX gain or loss',
    }
    bases = {'month': 'ماهانه / Monthly', 'week': 'هفته‌وار / Weekly', 'day': 'روزانه / Daily', 'hour': 'ساعتی / Hourly', 'project': 'پروژه‌ای / Project'}
    for key, label in labels.items():
        value = result.get(key)
        if key == 'period' and result.get('calendar_period'):
            continue
        if value is None or isinstance(value, (dict, list)):
            continue
        if key == 'rate_basis':
            value = bases.get(value, value)
        elif key == 'period_calendar':
            value = {'jalali':'هجری شمسی / Jalali','gregorian':'میلادی / Gregorian'}.get(value,value)
        elif isinstance(value, str) and len(value) == 10 and value[4:5] == '-' and value[7:8] == '-':
            value = printed_date(date.fromisoformat(value), user)
        elif key not in {'period', 'calendar_period', 'period_calendar', 'rate_basis', 'currency'}:
            value = number(value, key not in {'denominator_days', 'approved_days', 'approved_hours', 'main_height_mm', 'top_height_mm', 'bottom_height_mm', 'loss_mm', 'remaining_quantity'})
        details.append((label, value))
    if data.get('foreign_terms'):
        terms = data['foreign_terms']
        details.extend([('ارز قرارداد / Contract currency', terms['currency']), ('اصل مبلغ ارزی / Original foreign amount', number(terms['original_amount'], True)),
                        ('مانده ارز قرارداد / Foreign balance', number(terms['foreign_remaining'], True)), ('نرخ اولیه AFN / Original rate', number(terms['rate']))])
    for tender in result.get('payments',[]):
        details.append(('دریافت نقدی / Cash received' if tender.get('account')=='CASH' else 'دریافت بانکی / Bank received', number(tender.get('amount'), True)))
    total_rows = []
    if result.get('subtotal') is not None:
        total_rows.append(('مجموع اقلام / Subtotal', number(result['subtotal'], True)))
    tax = result.get('tax')
    if tax:
        total_rows.append(('مالیه / Tax', number(tax.get('amount') if isinstance(tax, dict) else tax, True)))
    if data.get('amount') is not None and doc.state == 'posted':
        total_rows.append(('مبلغ سند / Document total', number(data['amount'], True)))
    if result.get('paid') is not None and doc.kind != 'sale':
        total_rows.append(('نقد پرداخت‌شده هنگام ثبت / Cash paid at issue', number(result['paid'], True)))
    if result.get('deposit_amount') is not None and Decimal(str(result['deposit_amount'])):
        total_rows.append(('اعتبار پیش‌پرداخت هنگام ثبت / Credit at issue', number(result['deposit_amount'], True)))
    status = {'posted': 'ثبت نهایی / Posted', 'draft': 'مسوده / Draft', 'cancelled': 'لغوشده / Cancelled'}.get(doc.state, doc.state)
    if doc.kind in {'quotation', 'sales_order', 'purchase_order'}:
        status = 'بدون ثبت فروش / Non-posting commercial document'
    flow = data.get('sales_flow') or {}
    if flow.get('status') in {'cancelled', 'remaining_cancelled'}:
        status = 'مانده لغوشده / Remainder cancelled'
        closure = flow.get('closure') or {}
        if closure.get('number'):
            details.append(('سند لغو / Cancellation document', closure['number']))
        if closure.get('date'):
            details.append(('تاریخ لغو / Cancellation date', printed_date(date.fromisoformat(closure['date']), user)))
        if closure.get('reason'):
            details.append(('دلیل لغو / Cancellation reason', closure['reason']))
    notice = ''
    if doc.state == 'cancelled':
        notice = 'این نرخ‌نامه پیش از ثبت نهایی لغو شده است؛ فروش، دریافت یا خروج موجودی ایجاد نشده است. / This quotation was cancelled before posting; no revenue, collection or stock delivery was recorded.'
    elif doc.state != 'posted':
        notice = 'مسوده - این سند هنوز ثبت نهایی نشده است. / DRAFT - this document has not been posted.'
    elif doc.kind in {'quotation', 'sales_order', 'purchase_order'}:
        notice = 'این سند به تنهایی فروش، دریافت پول یا خروج موجودی را ثبت نمی‌کند. / This document alone does not record revenue, payment or stock delivery.'
        if flow.get('cancelled'):
            notice = 'مانده این سند لغو شده است. تحویل‌ها، بل‌ها و پرداخت‌های قبلی به قوت خود باقی است. / The remainder is cancelled; previous deliveries, invoices and payments remain effective.'
    elif doc.kind == 'order_cancel':
        notice = 'لغو فقط برای مانده اجرا‌نشده است. اسناد فروش، دریافت و تحویل قبلی به قوت خود باقی است. / Cancellation preserves previously posted deliveries, invoices and payments.'
    elif doc.kind.startswith('transfer_') or doc.kind == 'internal_settlement':
        notice = 'انتقال و تصفیه بین شعب همین تجارت، فروش به مشتری بیرونی نیست. / Same-business transfers and internal settlements are not external customer sales.'
    return {
        'business': business, 'doc': doc, 'data': data, 'title': title, 'english_title': english_title,
        'journal_rows': journal_rows,
        'display_date': printed_date(doc.date, user), 'party_snapshot': snapshot, 'employee_snapshot': employee,
        'sections': sections, 'details': details, 'total_rows': total_rows, 'status_label': status,
        'print_profile': profile, 'notice': notice, 'compact': compact, 'copy': copy, 'show_balance': data.get('balance') is not None,
        'balance_display': number(data.get('balance'), True), 'notes': payload.get('notes') or payload.get('comment') or '',
        'reason': result.get('reason') or payload.get('reason') or '',
        'payment_reference': payload.get('reference') or payload.get('supplier_reference') or '',
        'payment_method': {'CASH': 'نقد / Cash', 'BANK': 'بانک / Bank'}.get(payload.get('cash_account'), ''),
        'is_receipt': doc.kind in {'receipt', 'supplier_payment', 'customer_refund', 'supplier_refund', 'employee_advance', 'payroll_settle', 'fx_settle'},
        'receipt_amount_label': 'مجموع تصفیه معاش / Total payroll settlement' if doc.kind == 'payroll_settle' else 'مبلغ این رسید / Receipt amount',
        'amount_display': number(data.get('amount'), True), 'show_amount': data.get('amount') is not None and doc.state == 'posted',
        'printed_at': printed_date(timezone.localdate(), user) + ' ' + timezone.localtime().strftime('%H:%M'),
    }
