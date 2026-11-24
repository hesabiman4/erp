"""Print documents retain the posted truth and permission-filtered amounts."""
from decimal import Decimal

from erp.models import Document, Employee
from erp.tests.test_api import environment, client_for
from erp.tests.test_growth import growth_env, open_block


def test_receipt_print_identifies_payment_allocation_and_current_balance(growth_env):
    ctx, post, warehouse, sponge, raw, customer, supplier = growth_env
    block = open_block(post, warehouse, sponge)
    invoice = post('sale', {'warehouse': warehouse.id, 'party': customer.id,
        'lines': [{'product': sponge.id, 'block': block.id, 'thickness_mm': '100'}], 'paid': '3500'})
    payment = post('receipt', {'invoice': invoice.id, 'location': warehouse.location_id, 'amount': '1000', 'reference': '<script>unsafe</script>'})
    before = Document.objects.count()
    html = client_for(ctx.user, ctx.business).get(f'/api/documents/{payment.id}/print/').content.decode()
    assert 'Payment receipt' in html and invoice.number in html
    assert '1,000.00' in html and '500.00' in html and 'Current balance' in html
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in html and '<script>unsafe</script>' not in html
    assert Document.objects.count() == before
    invoice_html = client_for(ctx.user, ctx.business).get(f'/api/documents/{invoice.id}/print/').content.decode()
    assert '5,000.00' in invoice_html and '3,500.00' in invoice_html and '4,500.00' in invoice_html
    assert '100 mm × 1' in invoice_html and '10 cm' in invoice_html
    assert Decimal(invoice.result['outstanding']) == 1500  # Frozen issue snapshot is untouched.
    post('receipt', {'invoice': invoice.id, 'location': warehouse.location_id, 'amount': '500'})
    settled_html = client_for(ctx.user, ctx.business).get(f'/api/documents/{invoice.id}/print/').content.decode()
    assert 'Sales invoice' in settled_html and 'Cash sales receipt' not in settled_html


def test_full_payment_at_issue_prints_cash_sales_receipt_without_duplicate_sale(growth_env):
    ctx, post, warehouse, sponge, *_ = growth_env
    block = open_block(post, warehouse, sponge)
    sale = post('sale', {'warehouse': warehouse.id, 'lines': [{'product': sponge.id, 'block': block.id, 'thickness_mm': '100'}], 'paid': '5000'})
    before = Document.objects.count()
    html = client_for(ctx.user, ctx.business).get(f'/api/documents/{sale.id}/print/').content.decode()
    assert 'Cash sales receipt' in html and '5,000.00' in html
    assert Document.objects.count() == before
    assert sale.entries.filter(account__code='SALES').count() == 1


def test_print_cannot_recover_redacted_inventory_carrying_amount(growth_env):
    ctx, post, warehouse, sponge, raw, *_ = growth_env
    opening = post('stock_opening', {'warehouse': warehouse.id, 'lines': [{'product': sponge.id, 'value': '987654.32',
        'blocks': [{'length_mm': '2000', 'width_mm': '1000', 'height_mm': '1000'}]}]})
    ctx.membership.permissions = ['inventory.view', 'documents.print', 'documents.view']
    ctx.membership.save()
    response = client_for(ctx.user, ctx.business).get(f'/api/documents/{opening.id}/print/')
    assert response.status_code == 200
    html = response.content.decode()
    assert sponge.name in html
    assert '987654' not in html and '987,654' not in html and 'Document total' not in html


def test_quotation_print_uses_snapshot_and_explains_nonposting(growth_env):
    ctx, post, warehouse, sponge, raw, customer, supplier = growth_env
    quote = post('quotation', {'warehouse': warehouse.id, 'party': customer.id, 'lines': [{'product': sponge.id, 'quantity': '5'}]})
    customer.name = 'Changed customer after quote'; customer.save()
    html = client_for(ctx.user, ctx.business).get(f'/api/documents/{quote.id}/print/?compact=1&copy=1').content.decode()
    assert 'Quotation' in html and 'Non-posting commercial document' in html
    assert 'Changed customer after quote' not in html and 'COPY' in html
    assert '80mm 297mm' in html and '2,500.00' in html


def test_payroll_print_distinguishes_cash_recovery_and_remaining_liability(growth_env):
    ctx, post, warehouse, sponge, raw, *_ = growth_env
    employee = Employee.objects.create(business=ctx.business, name='Print employee', location=warehouse.location, kind='monthly', rate='10000', advance_limit='10000')
    post('opening_cash', {'location': warehouse.location_id, 'amount': '20000', 'reason': 'Test funds'})
    post('employee_advance', {'employee': employee.id, 'amount': '3500', 'location': warehouse.location_id})
    payroll = post('payroll_accrue', {'employee': employee.id, 'period': '2026-05'})
    settlement = post('payroll_settle', {'payroll': payroll.id, 'amount': '6000', 'advance_recovery': '2000', 'location': warehouse.location_id})
    html = client_for(ctx.user, ctx.business).get(f'/api/documents/{settlement.id}/print/').content.decode()
    assert 'Total payroll settlement' in html and '8,000.00' in html
    assert 'Cash paid at issue' in html and '6,000.00' in html
    assert 'Advance recovery' in html and '2,000.00' in html and '1,500.00' in html


def test_adjustment_journal_print_handles_line_count_and_shows_actual_sides(growth_env):
    ctx, post, warehouse, *_ = growth_env
    journal = post('journal_adjust', {'location': warehouse.location_id, 'reason': 'Reclassify expenses',
        'lines': [{'account': 'RENT', 'debit': '125'}, {'account': 'REPAIRS', 'credit': '125'}]})
    assert journal.result['lines'] == 2
    response = client_for(ctx.user, ctx.business).get(f'/api/documents/{journal.id}/print/')
    assert response.status_code == 200
    html = response.content.decode()
    assert 'Journal entries' in html and 'Debit' in html and 'Credit' in html and '125.00' in html
