from datetime import date
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from erp.core import Context, balance, execute, journal, outstanding, stock_in, stock_out
from erp.finance import release_inventory_allowance, update_employee_rate
from erp.models import Account, Allocation, Asset, Business, Document, Employee, Entry, Location, Membership, Party, Product, StockPool, Warehouse
from erp.reports import report


class FinanceTests(TestCase):
    def test_weekly_payroll_cross_month_duplicate_and_advance_recovery(self):
        worker=Employee.objects.create(business=self.business,location=self.location,name='Weekly worker',kind='weekly',rate='7000',advance_limit='10000',join_date=date(2026,4,1))
        self.run_action('employee_advance',{'employee':worker.id,'amount':'8000'})
        payload={'employee':worker.id,'week_start_date':'2026-04-25','date':'2026-05-01'}
        payroll=self.run_action('payroll_accrue',payload,key='weekly-once')
        self.assertEqual(payroll.amount,Decimal('7000'))
        self.assertEqual(payroll.result['earning_through'],'2026-05-01')
        self.assertEqual(payroll.result['rate_basis'],'week')
        self.assertEqual(self.run_action('payroll_accrue',payload,key='weekly-once').id,payroll.id)
        with self.assertRaises(ValidationError): self.run_action('payroll_accrue',payload)
        self.run_action('payroll_settle',{'payroll':payroll.id,'advance_recovery':'7000','amount':'0','date':'2026-05-01'})
        self.assertEqual(balance(self.ctx,'PAYROLL',employee=worker),Decimal('0'))
        self.assertEqual(balance(self.ctx,'ADVANCES',employee=worker),Decimal('1000'))
        self.assertEqual(balance(self.ctx,'SALARY'),Decimal('7000'))
        with self.assertRaises(ValidationError): self.run_action('attendance_record',{'employee':worker.id,'date':'2026-04-30','days':'1'})

    def test_weekly_proration_week_alignment_and_rate_history(self):
        worker=Employee.objects.create(business=self.business,location=self.location,name='Partial weekly',kind='weekly',rate='7000',join_date=date(2026,4,28),end_date=date(2026,4,30))
        with self.assertRaises(ValidationError): self.run_action('payroll_accrue',{'employee':worker.id,'week_start_date':'2026-04-25','date':'2026-04-30'})
        with self.assertRaises(ValidationError): self.run_action('payroll_accrue',{'employee':worker.id,'week_start_date':'2026-04-27','date':'2026-05-03'})
        payroll=self.run_action('payroll_accrue',{'employee':worker.id,'week_start_date':'2026-04-25','date':'2026-05-01'})
        self.assertEqual(payroll.amount,Decimal('3000'))
        self.assertEqual(payroll.data['earning_from'],'2026-04-28')
        self.assertEqual(payroll.data['earning_through'],'2026-04-30')
        with self.assertRaises(ValidationError): update_employee_rate(worker,'8000','2026-04-29')
        with self.assertRaises(ValidationError): self.run_action('attendance_record',{'employee':worker.id,'date':'2026-05-02'})

    def test_hourly_contract_and_monthly_joining_proration(self):
        hourly=Employee.objects.create(business=self.business,location=self.location,name='Hourly contract',kind='hourly',rate='150',join_date=date(2026,4,10))
        self.run_action('attendance_record',{'employee':hourly.id,'date':'2026-04-10','hours':'4','days':'1'})
        pay=self.run_action('payroll_accrue',{'employee':hourly.id,'period':'2026-04','date':'2026-04-10'})
        self.assertEqual(pay.amount,Decimal('600'))
        monthly=Employee.objects.create(business=self.business,location=self.location,name='Joined midmonth',kind='monthly',rate='30000',join_date=date(2026,4,16))
        self.assertEqual(self.run_action('payroll_accrue',{'employee':monthly.id,'period':'2026-04'}).amount,Decimal('15000'))

    def test_professional_statement_sections_comparison_and_equity_reconcile(self):
        from erp.seed import bootstrap
        bootstrap(self.business)
        self.run_action('opening_cash',{'account':'CASH','amount':'10000','reason':'Reviewed opening'})
        self.invoice('5000')
        self.run_action('expense_post',{'expense_account':'RENT','amount':'600'})
        self.run_action('expense_post',{'expense_account':'INTEREST_EXPENSE','amount':'100'})
        self.run_action('expense_post',{'expense_account':'INCOME_TAX_EXPENSE','amount':'300'})
        params={'from':'2026-04-01','to':'2026-04-30','compare_from':'2026-03-01','compare_to':'2026-03-31'}
        profit=report(self.ctx,'profit_loss',params)
        self.assertEqual(profit['totals']['operating_profit'],'4400.00')
        self.assertEqual(profit['totals']['profit_before_financing_and_tax'],'4400.00')
        self.assertEqual(profit['totals']['profit_before_tax'],'4300.00')
        self.assertEqual(profit['totals']['profit'],'4000.00')
        cash=report(self.ctx,'cash_flow',params)
        self.assertEqual(cash['totals']['financing'],'9900.00')
        self.assertEqual(cash['totals']['operating'],'-900.00')
        self.assertEqual(cash['totals']['difference'],'0.00')
        self.assertEqual(Decimal(profit['comparative']['totals']['profit']),Decimal('0'))
        sheet=report(self.ctx,'balance_sheet',params)
        self.assertEqual(sum((Decimal(s['total']) for s in sheet['sections'] if s['key'].endswith('_assets')),Decimal('0')),Decimal(sheet['totals']['assets']))
        self.assertEqual(sheet['totals']['difference'],'0.00')
        equity=report(self.ctx,'changes_equity',params)
        self.assertEqual(equity['totals']['closing_equity'],'14000.00')
        self.assertEqual(equity['totals']['difference'],'0.00')
        chart=report(self.ctx,'chart_of_accounts',params)
        self.assertTrue(any(r['code']=='WIP' and r['group']=='current_assets' for r in chart['rows']))
        self.assertTrue(any(r['code']=='LONG_TERM_LOANS' and r['group']=='noncurrent_liabilities' for r in chart['rows']))

    def test_party_center_statement_opening_payments_deposits_and_reversal(self):
        invoice = self.invoice("5000")
        receipt = self.run_action("receipt", {"invoice": invoice.id, "amount": "3500"})
        self.run_action("receipt", {"party": self.customer.id, "amount": "800"})
        params = {"to": "2026-04-30"}
        center = report(self.ctx, "customer_balances", params)
        self.assertEqual(center["totals"], {"balance": "1500.00", "deposit": "800.00", "overdue": "1500.00"})
        detail = report(self.ctx, "customer_statement", {**params, "party": self.customer.id, "from": "2026-04-02"})
        self.assertEqual(detail["totals"], {"opening": "5000.00", "balance": "1500.00", "deposit": "800.00"})
        self.assertEqual(len(detail["rows"]), 1)
        self.assertEqual(detail["rows"][0]["balance"], "1500.00")
        self.assertEqual(detail["open_invoices"][0]["outstanding"], "1500.00")
        self.run_action("payment_reverse", {"payment": receipt.id, "date": "2026-05-01", "reason": "Receipt correction"})
        self.assertEqual(report(self.ctx, "customer_balances", params)["totals"]["balance"], "1500.00")
        self.assertEqual(report(self.ctx, "customer_statement", {"party": self.customer.id, "to": "2026-05-01"})["totals"]["balance"], "5000.00")
        # Supplier sign and deposit semantics are the opposite of AR, not a netted number.
        bill = self.invoice("5000", supplier=True)
        self.run_action("supplier_payment", {"invoice": bill.id, "amount": "5500"})
        supplier = report(self.ctx, "supplier_statement", {**params, "party": self.supplier.id})
        self.assertEqual(supplier["totals"]["balance"], "0.00")
        self.assertEqual(supplier["totals"]["deposit"], "500.00")
        self.assertEqual(supplier["open_invoices"], [])

    def test_party_centers_enforce_business_location_lines_and_module_permissions(self):
        self.invoice()
        other = Business.objects.create(name="Private", slug="party-private")
        foreign = Party.objects.create(business=other, name="Private customer")
        with self.assertRaises(ValidationError):
            report(self.ctx, "customer_statement", {"party": foreign.id})
        with self.assertRaises(ValidationError):
            report(self.ctx, "customer_statement", {"party": self.supplier.id})
        with self.assertRaises(ValidationError):
            report(self.ctx, "customer_balances", {"line": "sponge"})
        user = get_user_model().objects.create_user(username="center-reader")
        member = Membership.objects.create(user=user, business=self.business, permissions=["sales.view"], all_locations=False, location_ids=[self.kabul.id], product_lines=["sponge", "adhesive", "shared"])
        scoped = Context(user, self.business, member)
        self.assertEqual(report(scoped, "customer_balances")["totals"]["balance"], "0.00")
        self.assertEqual(report(scoped, "customer_statement", {"party": self.customer.id})["rows"], [])
        with self.assertRaises(PermissionDenied):
            report(scoped, "supplier_balances")
        member.all_locations = True
        member.product_lines = ["sponge"]
        member.save()
        self.assertEqual(report(scoped, "customer_balances")["totals"]["balance"], "0.00")

    def test_dashboard_chart_uses_journal_dates_not_recent_invoice_page(self):
        self.invoice("5000")
        self.run_action("receipt", {"party": self.customer.id, "amount": "800"})
        values = report(self.ctx, "dashboard", {"from": "2026-04-01", "to": "2026-04-30"})
        self.assertEqual(values["sales"], "5000.00")
        self.assertEqual(values["collections"], "800.00")
        self.assertEqual(values["profit"], "5000.00")
        self.assertEqual(len(values["sales_series"]), 7)
        self.assertEqual(sum(Decimal(r["amount"]) for r in values["sales_series"]), Decimal("0"))
        # The seven-day chart is independent of a narrower KPI period.
        chart = report(self.ctx, "dashboard", {"from": "2026-04-03", "to": "2026-04-07"})
        self.assertEqual(chart["sales"], "0.00")
        self.assertEqual(sum(Decimal(r["amount"]) for r in chart["sales_series"]), Decimal("5000"))

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="finance-owner", password="test-only-password")
        cls.business = Business.objects.create(name="Finance test", slug="finance-test")
        cls.location = Location.objects.create(business=cls.business, name="Herat", code="HER")
        cls.kabul = Location.objects.create(business=cls.business, name="Kabul", code="KBL")
        cls.warehouse = Warehouse.objects.create(business=cls.business, location=cls.location, name="Herat stock")
        cls.membership = Membership.objects.create(business=cls.business, user=cls.user, permissions=["*"], all_locations=True, product_lines=["sponge", "adhesive", "shared"])
        categories = {
            "CASH": "asset", "BANK": "asset", "AR": "asset", "AP": "liability", "GRNI": "liability", "RAW": "asset", "WIP": "asset", "FG": "asset", "TRIM": "asset", "TRANSIT": "asset", "ADVANCES": "asset", "PAYROLL": "liability", "SALARY": "expense", "LABOR_CLEARING": "asset", "COST_CLEARING": "asset", "OVERHEAD": "expense", "COGS": "expense", "WASTE": "expense", "SALES": "income", "DEPOSITS": "liability", "SUPPLIER_DEPOSITS": "asset", "EXPENSE": "expense", "EQUITY": "equity", "DRAWINGS": "equity", "ASSETS": "asset", "DEPRECIATION": "expense", "ACCUM_DEPR": "asset", "TAX": "liability", "INVENTORY_ALLOWANCE": "asset", "IMPAIRMENT": "expense",
        }
        controls = {"AR", "AP", "GRNI", "RAW", "WIP", "FG", "TRIM", "TRANSIT", "ADVANCES", "PAYROLL", "DEPOSITS", "SUPPLIER_DEPOSITS", "ASSETS", "ACCUM_DEPR", "INVENTORY_ALLOWANCE"}
        for code, category in categories.items():
            Account.objects.create(business=cls.business, code=code, name=code, category=category, control=code in controls)
        cls.employee = Employee.objects.create(business=cls.business, location=cls.location, name="Office employee", rate="20000", advance_limit="50000")
        cls.customer = Party.objects.create(business=cls.business, kind="customer", name="Invoice-linked walk-in", phone="0700000000")
        cls.supplier = Party.objects.create(business=cls.business, kind="supplier", name="Supplier")

    def setUp(self):
        self.ctx = Context(self.user, self.business, self.membership)

    def run_action(self, action, payload, key=None):
        payload = {"date": "2026-04-30", "location": self.location.id, **payload}
        return execute(self.ctx, action, payload, key or str(uuid4()))

    def fixture_document(self, kind, amount="0", party=None, when="2026-04-01"):
        key = uuid4().hex
        return Document.objects.create(business=self.business, kind=kind, number="FIX-" + key, state="draft", date=date.fromisoformat(when), location=self.location, amount=Decimal(amount), party=party, created_by=self.user, idempotency_key=key, request_hash=key)

    def post_fixture(self, doc):
        doc.state = "posted"
        doc.posted_at = timezone.now()
        doc.save(update_fields=["state", "posted_at"])
        return doc

    def invoice(self, amount="5000", supplier=False):
        doc = self.fixture_document("purchase_bill" if supplier else "sale", amount, self.supplier if supplier else self.customer)
        if supplier:
            lines = [{"account": "EXPENSE", "debit": amount, "location": self.location}, {"account": "AP", "credit": amount, "party": self.supplier, "location": self.location}]
        else:
            lines = [{"account": "AR", "debit": amount, "party": self.customer, "location": self.location}, {"account": "SALES", "credit": amount, "location": self.location}]
        journal(self.ctx, doc, lines)
        return self.post_fixture(doc)

    def assert_balanced(self):
        for doc in Document.objects.filter(business=self.business, state="posted"):
            self.assertEqual(sum((entry.debit - entry.credit for entry in doc.entries.all()), Decimal("0")), Decimal("0"))

    def test_advance_below_salary_and_exact_settlement(self):
        self.run_action("employee_advance", {"employee": self.employee.id, "amount": "12000", "cash_account": "CASH"})
        payroll = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04"})
        settled = self.run_action("payroll_settle", {"payroll": payroll.id, "advance_recovery": "12000", "amount": "8000"})
        self.assertEqual(balance(self.ctx, "SALARY"), Decimal("20000"))
        self.assertEqual(balance(self.ctx, "ADVANCES", employee=self.employee), Decimal("0"))
        self.assertEqual(balance(self.ctx, "PAYROLL", employee=self.employee), Decimal("0"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("-20000"))
        self.assertEqual(settled.result["remaining_payable"], "0.00")
        self.assert_balanced()

    def test_reviewed_openings_settle_without_inventing_revenue_or_expense(self):
        self.run_action("opening_cash", {"account": "CASH", "amount": "10000", "reason": "Reviewed conversion balance"})
        receivable = self.run_action("opening_receivable", {"party": self.customer.id, "amount": "3000", "due_date": "2026-03-01"})
        payable = self.run_action("opening_payable", {"party": self.supplier.id, "amount": "2000", "due_date": "2026-04-15"})
        self.run_action("opening_employee_advance", {"employee": self.employee.id, "amount": "500"})
        self.run_action("receipt", {"invoice": receivable.id, "amount": "3000"})
        self.run_action("supplier_payment", {"invoice": payable.id, "amount": "2000"})
        self.assertEqual(outstanding(receivable), Decimal("0"))
        self.assertEqual(outstanding(payable), Decimal("0"))
        self.assertEqual(balance(self.ctx, "SALES"), Decimal("0"))
        self.assertEqual(balance(self.ctx, "EXPENSE"), Decimal("0"))
        self.assertEqual(balance(self.ctx, "ADVANCES", employee=self.employee), Decimal("500"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("11000"))

    def test_advance_above_salary_remains_employee_asset(self):
        self.run_action("employee_advance", {"employee": self.employee.id, "amount": "25000"})
        payroll = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04"})
        self.run_action("payroll_settle", {"payroll": payroll.id, "advance_recovery": "20000", "amount": "0"})
        self.assertEqual(balance(self.ctx, "ADVANCES", employee=self.employee), Decimal("5000"))
        self.assertEqual(balance(self.ctx, "PAYROLL", employee=self.employee), Decimal("0"))
        with self.assertRaises(ValidationError):
            self.run_action("payroll_settle", {"payroll": payroll.id, "amount": "1"})

    def test_deductions_reduce_available_recovery_and_duplicate_payroll_rejected(self):
        self.run_action("employee_advance", {"employee": self.employee.id, "amount": "25000"})
        payroll = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04", "deductions": [{"account": "TAX", "amount": "2000"}]})
        self.assertEqual(payroll.amount, Decimal("18000"))
        with self.assertRaises(ValidationError):
            self.run_action("payroll_settle", {"payroll": payroll.id, "advance_recovery": "20000", "amount": "0"})
        self.run_action("payroll_settle", {"payroll": payroll.id, "advance_recovery": "18000", "amount": "0"})
        with self.assertRaises(ValidationError):
            self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04"})
        self.assertEqual(balance(self.ctx, "TAX"), Decimal("-2000"))

    def test_daily_attendance_and_project_reference_are_real_earnings(self):
        daily = Employee.objects.create(business=self.business, location=self.location, name="Daily", kind="daily", rate="500")
        self.run_action("attendance_record", {"employee": daily.id, "date": "2026-04-02", "days": "1"})
        self.run_action("attendance_record", {"employee": daily.id, "date": "2026-04-03", "days": "0.5"})
        payroll = self.run_action("payroll_accrue", {"employee": daily.id, "period": "2026-04"})
        self.assertEqual(payroll.amount, Decimal("750"))
        project = Employee.objects.create(business=self.business, location=self.location, name="Project", kind="project", rate="0")
        self.run_action("payroll_accrue", {"employee": project.id, "period": "2026-04", "project_reference": "CHAIR-12", "gross": "1000"})
        with self.assertRaises(ValidationError):
            self.run_action("payroll_accrue", {"employee": project.id, "period": "2026-04", "project_reference": "CHAIR-12", "gross": "1000"})

    def test_payment_partial_later_collection_and_idempotency(self):
        invoice = self.invoice()
        first = self.run_action("receipt", {"invoice": invoice.id, "amount": "3500"}, key="first-receipt")
        self.assertEqual(outstanding(invoice), Decimal("1500"))
        same = self.run_action("receipt", {"invoice": invoice.id, "amount": "3500"}, key="first-receipt")
        self.assertEqual(first.id, same.id)
        self.run_action("receipt", {"invoice": invoice.id, "amount": "1500"})
        self.assertEqual(outstanding(invoice), Decimal("0"))
        self.assertEqual(balance(self.ctx, "SALES"), Decimal("-5000"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("5000"))
        self.assert_balanced()

    def test_customer_overpayment_allocates_and_refunds_once(self):
        invoice = self.invoice("5000")
        receipt = self.run_action("receipt", {"invoice": invoice.id, "amount": "6000"})
        self.assertEqual(receipt.result["deposit_amount"], "1000.00")
        later = self.invoice("700")
        self.run_action("allocate_deposit", {"deposit": receipt.id, "allocations": [{"invoice": later.id, "amount": "700"}]})
        self.assertEqual(outstanding(later), Decimal("0"))
        self.run_action("customer_refund", {"deposit": receipt.id, "amount": "300", "reason": "Customer requests remaining credit"})
        self.assertEqual(balance(self.ctx, "DEPOSITS"), Decimal("0"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("5700"))
        with self.assertRaises(ValidationError):
            self.run_action("customer_refund", {"deposit": receipt.id, "amount": "1", "reason": "Already refunded"})

    def test_supplier_deposit_is_asset_not_customer_liability(self):
        bill = self.invoice("5000", supplier=True)
        payment = self.run_action("supplier_payment", {"invoice": bill.id, "amount": "6000"})
        self.assertEqual(outstanding(bill), Decimal("0"))
        self.assertEqual(balance(self.ctx, "SUPPLIER_DEPOSITS"), Decimal("1000"))
        self.assertEqual(balance(self.ctx, "DEPOSITS"), Decimal("0"))
        self.run_action("supplier_refund", {"deposit": payment.id, "amount": "1000", "reason": "Unused supplier credit returned"})
        self.assertEqual(balance(self.ctx, "SUPPLIER_DEPOSITS"), Decimal("0"))

    def test_payment_rejects_overallocation_and_cross_customer(self):
        invoice = self.invoice()
        before = Document.objects.count()
        with self.assertRaises(ValidationError):
            self.run_action("receipt", {"amount": "3000", "allocations": [{"invoice": invoice.id, "amount": "3500"}]})
        self.assertEqual(Document.objects.count(), before)
        other = Party.objects.create(business=self.business, name="Other customer")
        with self.assertRaises(ValidationError):
            self.run_action("receipt", {"party": other.id, "invoice": invoice.id, "amount": "1000"})

    def test_expense_supplier_payment_and_cash_transfer(self):
        expense = self.run_action("expense_post", {"amount": "1200", "supplier": self.supplier.id, "description": "Office rent"})
        self.assertEqual(balance(self.ctx, "AP"), Decimal("-1200"))
        self.run_action("supplier_payment", {"invoice": expense.id, "amount": "1200"})
        self.run_action("cash_transfer", {"amount": "400", "from_account": "CASH", "from_location": self.location.id, "to_account": "BANK", "to_location": self.kabul.id})
        self.assertEqual(balance(self.ctx, "AP"), Decimal("0"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("-1600"))
        self.assertEqual(balance(self.ctx, "BANK"), Decimal("400"))
        cash = report(self.ctx, "cash_flow", {"date_from": "2026-04-01", "date_to": "2026-04-30"})
        self.assertEqual(cash["totals"]["internal_transfer"], "0")
        self.assertEqual(Decimal(cash["totals"]["difference"]), Decimal("0"))

    def test_asset_depreciation_accumulates_without_duplicates_and_caps_at_residual(self):
        acquired = self.run_action("asset_acquire", {"name": "Cutter", "cost": "12000", "residual": "0", "life_months": 12, "date": "2026-01-01", "acquired": "2026-01-01", "depreciation_start": "2026-01-01"})
        asset = acquired.result["asset"]
        first = self.run_action("asset_depreciate", {"asset": asset, "through_month": "2026-04"})
        self.assertEqual(first.amount, Decimal("4000"))
        with self.assertRaises(ValidationError):
            self.run_action("asset_depreciate", {"asset": asset, "through_month": "2026-04"})
        self.run_action("asset_depreciate", {"asset": asset, "through_month": "2027-01", "date": "2027-01-31"})
        self.assertEqual(balance(self.ctx, "ACCUM_DEPR"), Decimal("-12000"))
        self.assertEqual(report(self.ctx, "assets", {"as_of": "2027-01-31"})["totals"]["carrying_value"], "0.00")

    def test_cash_count_is_evidence_not_silent_variance_posting(self):
        opening = self.fixture_document("opening")
        journal(self.ctx, opening, [{"account": "CASH", "debit": "1000", "location": self.location}, {"account": "EQUITY", "credit": "1000", "location": self.location}])
        self.post_fixture(opening)
        count = self.run_action("cash_count", {"cash_account": "CASH", "location": self.location.id, "counted": "900"})
        self.assertEqual(count.result["expected"], "1000.00")
        self.assertEqual(count.result["variance"], "-100.00")
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("1000"))
        self.assertEqual(count.entries.count(), 0)

    def test_bank_reconciliation_requires_actual_cleared_entries(self):
        moved = self.run_action("cash_transfer", {"amount": "300", "from_account": "CASH", "to_account": "BANK", "from_location": self.location.id, "to_location": self.location.id})
        bank_entry = moved.entries.get(account__code="BANK")
        reconciled = self.run_action("bank_reconcile", {"account": "BANK", "statement_balance": "300", "through_date": "2026-04-30", "entry_ids": [bank_entry.id]})
        self.assertEqual(reconciled.result["uncleared"], "0.00")
        with self.assertRaises(ValidationError):
            self.run_action("bank_reconcile", {"account": "BANK", "statement_balance": "400", "entry_ids": [bank_entry.id]})

    def test_production_conversion_sources_do_not_double_count_expense(self):
        payroll = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04", "expense_account": "LABOR_CLEARING"})
        overhead = self.run_action("expense_post", {"amount": "1000", "expense_account": "COST_CLEARING", "production_cost": True, "description": "Eligible factory electricity"})
        self.assertEqual(payroll.amount, Decimal("20000"))
        self.assertEqual(overhead.amount, Decimal("1000"))
        self.assertEqual(balance(self.ctx, "LABOR_CLEARING"), Decimal("20000"))
        self.assertEqual(balance(self.ctx, "COST_CLEARING"), Decimal("1000"))
        self.assertEqual(balance(self.ctx, "SALARY"), Decimal("0"))

    def test_adjustments_balance_and_control_accounts_are_protected(self):
        self.run_action("journal_adjust", {"reason": "Accrued office cost", "lines": [{"account": "EXPENSE", "debit": "50"}, {"account": "OVERHEAD", "credit": "50"}]})
        with self.assertRaises(ValidationError):
            self.run_action("journal_adjust", {"reason": "Bad entry", "lines": [{"account": "EXPENSE", "debit": "50"}, {"account": "OVERHEAD", "credit": "40"}]})
        with self.assertRaises(ValidationError):
            self.run_action("journal_adjust", {"reason": "Bypass customer ledger", "lines": [{"account": "AR", "debit": "50"}, {"account": "SALES", "credit": "50"}]})
        self.assert_balanced()

    def test_period_close_blocks_posting_and_reopening_is_audited_document(self):
        self.run_action("period_close", {"through_date": "2026-03-31"})
        with self.assertRaises(ValidationError):
            self.run_action("expense_post", {"date": "2026-03-15", "amount": "20"})
        self.run_action("period_reopen", {"through_date": "2026-02-28", "reason": "Accountant correction"})
        self.run_action("expense_post", {"date": "2026-03-15", "amount": "20"})
        self.assertEqual(Document.objects.filter(kind="period_reopen", state="posted").count(), 1)

    def test_trial_balance_and_balance_sheet_reconcile(self):
        self.invoice("5000")
        self.run_action("receipt", {"party": self.customer.id, "amount": "1000"})
        self.run_action("expense_post", {"amount": "600"})
        trial = report(self.ctx, "trial_balance", {"as_of": "2026-04-30"})
        sheet = report(self.ctx, "balance_sheet", {"as_of": "2026-04-30"})
        profit = report(self.ctx, "profit_loss", {"date_from": "2026-04-01", "date_to": "2026-04-30"})
        self.assertEqual(Decimal(trial["totals"]["difference"]), Decimal("0"))
        self.assertEqual(Decimal(sheet["totals"]["difference"]), Decimal("0"))
        self.assertEqual(Decimal(profit["totals"]["profit"]), Decimal("4400"))
        with self.assertRaises(ValidationError):
            report(self.ctx, "balance_sheet", {"location": self.location.id})

    def test_aging_uses_as_of_payment_date_and_preserves_old_debt(self):
        invoice = self.invoice("5000")
        self.run_action("receipt", {"invoice": invoice.id, "amount": "3500", "date": "2026-05-01"})
        april = report(self.ctx, "receivables", {"date_from": "2026-04-20", "as_of": "2026-04-30"})
        may = report(self.ctx, "receivables", {"as_of": "2026-05-31"})
        self.assertEqual(Decimal(april["totals"]["outstanding"]), Decimal("5000"))
        self.assertEqual(Decimal(may["totals"]["outstanding"]), Decimal("1500"))

    def test_cross_business_and_branch_permissions_reject_references(self):
        other = Business.objects.create(name="Furniture", slug="furniture-test")
        outsider = Party.objects.create(business=other, name="Furniture customer")
        with self.assertRaises(ValidationError):
            self.run_action("receipt", {"party": outsider.id, "amount": "100"})
        limited_user = get_user_model().objects.create_user(username="limited-finance")
        limited = Membership.objects.create(business=self.business, user=limited_user, permissions=["finance.post", "accounting.view"], all_locations=False, location_ids=[self.kabul.id], product_lines=["shared"])
        limited_ctx = Context(limited_user, self.business, limited)
        with self.assertRaises(PermissionDenied):
            execute(limited_ctx, "cash_transfer", {"date": "2026-04-30", "amount": "100", "from_account": "CASH", "to_account": "BANK", "from_location": self.location.id, "to_location": self.kabul.id}, uuid4().hex)
        with self.assertRaises(PermissionDenied):
            report(limited_ctx, "trial_balance", {})

    def test_write_down_reversal_and_release_preserve_quantity_and_original_cost(self):
        product = Product.objects.create(business=self.business, name="Sponge", code="SP45", kind="finished", unit="cm", line="sponge")
        opening = self.fixture_document("opening")
        pool = stock_in(self.ctx, opening, product, self.warehouse, "100", "2000", "2000x1000")
        journal(self.ctx, opening, [{"account": "FG", "debit": "2000", "location": self.location, "warehouse": self.warehouse, "line": "sponge"}, {"account": "EQUITY", "credit": "2000", "location": self.location, "line": "sponge"}])
        self.post_fixture(opening)
        write_down = self.run_action("inventory_write_down", {"pool": pool.id, "amount": "400", "reason": "Approved lower expected selling value"})
        pool.refresh_from_db()
        self.assertEqual(pool.quantity, Decimal("100"))
        self.assertEqual(pool.value, Decimal("2000"))
        self.run_action("inventory_write_down_reverse", {"write_down": write_down.id, "amount": "100", "reason": "Revised NRV"})
        issue = self.fixture_document("sale", when="2026-05-01")
        released = release_inventory_allowance(self.ctx, issue, pool, Decimal("25"), pool.quantity)
        self.assertEqual(released, Decimal("75"))
        self.assertEqual(balance(self.ctx, "INVENTORY_ALLOWANCE"), Decimal("-225"))
        with self.assertRaises(ValidationError):
            self.run_action("inventory_write_down_reverse", {"write_down": write_down.id, "amount": "226", "reason": "Cannot reverse used allowance", "date": "2026-05-01"})

    def test_impaired_sales_returns_restore_net_cost_without_artificial_profit(self):
        product = Product.objects.create(business=self.business, name="Adhesive", code="NRV-ADH", kind="finished", unit="kg", line="adhesive", price="100")
        opening = self.fixture_document("opening")
        pool = stock_in(self.ctx, opening, product, self.warehouse, "100", "2000")
        journal(self.ctx, opening, [{"account": "FG", "debit": "2000", "location": self.location, "warehouse": self.warehouse, "line": "adhesive"}, {"account": "EQUITY", "credit": "2000", "location": self.location, "line": "adhesive"}])
        self.post_fixture(opening)
        self.run_action("inventory_write_down", {"pool": pool.id, "amount": "400", "reason": "Reviewed NRV"})
        sale = self.run_action("sale", {"date": "2026-05-01", "warehouse": self.warehouse.id, "party": self.customer.id, "lines": [{"product": product.id, "quantity": "25", "unit_price": "100"}]})
        self.assertEqual(balance(self.ctx, "COGS"), Decimal("400"))
        self.run_action("sales_return", {"date": "2026-05-01", "invoice": sale.id, "warehouse": self.warehouse.id, "lines": [{"index": 0, "quantity": "10"}]})
        self.assertEqual(balance(self.ctx, "COGS"), Decimal("240"))
        self.assertEqual(balance(self.ctx, "INVENTORY_ALLOWANCE"), Decimal("-340"))
        # Two entries for the same original line exercise independent child-event numbering.
        self.run_action("sales_return", {"date": "2026-05-01", "invoice": sale.id, "warehouse": self.warehouse.id, "lines": [{"index": 0, "quantity": "5"}, {"index": 0, "quantity": "10"}]})
        pool.refresh_from_db()
        self.assertEqual(pool.quantity, Decimal("100"))
        self.assertEqual(pool.value, Decimal("2000"))
        self.assertEqual(balance(self.ctx, "COGS"), Decimal("0"))
        self.assertEqual(balance(self.ctx, "INVENTORY_ALLOWANCE"), Decimal("-400"))
        self.assertEqual(outstanding(sale), Decimal("0"))

    def test_cross_branch_collection_keeps_receivable_at_original_sale_location(self):
        invoice = self.invoice("5000")
        self.run_action("receipt", {"invoice": invoice.id, "amount": "5000", "location": self.kabul.id})
        self.assertEqual(balance(self.ctx, "AR", location=self.location), Decimal("0"))
        self.assertEqual(balance(self.ctx, "AR", location=self.kabul), Decimal("0"))
        self.assertEqual(balance(self.ctx, "CASH", location=self.kabul), Decimal("5000"))

    def test_deposit_allocation_keeps_source_credit_and_target_invoice_dimensions(self):
        deposit = self.run_action("receipt", {"party": self.customer.id, "amount": "1000", "location": self.kabul.id})
        invoice = self.invoice("1000")
        self.run_action("allocate_deposit", {"deposit": deposit.id, "allocations": [{"invoice": invoice.id, "amount": "1000"}], "location": self.location.id})
        self.assertEqual(balance(self.ctx, "DEPOSITS", location=self.kabul), Decimal("0"))
        self.assertEqual(balance(self.ctx, "AR", location=self.location), Decimal("0"))

    def test_employee_rate_history_preserves_old_period_and_prevents_rewriting_accrued_rate(self):
        update_employee_rate(self.employee, "24000", "2026-05-01")
        self.employee.save(update_fields=["rate", "terms"])
        april = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04"})
        may = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-05", "date": "2026-05-31"})
        self.assertEqual(april.amount, Decimal("20000"))
        self.assertEqual(may.amount, Decimal("24000"))
        with self.assertRaises(ValidationError):
            update_employee_rate(self.employee, "26000", "2026-05-15")

    def test_midperiod_rate_change_requires_approved_gross(self):
        update_employee_rate(self.employee, "24000", "2026-04-15")
        self.employee.save(update_fields=["rate", "terms"])
        with self.assertRaises(ValidationError):
            self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04"})
        payroll = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04", "gross": "22000"})
        self.assertEqual(payroll.amount, Decimal("22000"))

    def test_future_advance_cannot_be_recovered_in_earlier_payroll_settlement(self):
        payroll = self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04"})
        self.run_action("employee_advance", {"employee": self.employee.id, "amount": "1000", "date": "2026-05-01"})
        with self.assertRaises(ValidationError):
            self.run_action("payroll_settle", {"payroll": payroll.id, "advance_recovery": "1000", "amount": "0"})

    def test_post_permission_alone_cannot_override_payroll_gross(self):
        clerk = get_user_model().objects.create_user(username="payroll-clerk")
        member = Membership.objects.create(business=self.business, user=clerk, permissions=["payroll.post"], all_locations=True, product_lines=["shared"])
        with self.assertRaises(PermissionDenied):
            execute(Context(clerk, self.business, member), "payroll_accrue", {"date": "2026-04-30", "employee": self.employee.id, "period": "2026-04", "gross": "99999"}, uuid4().hex)

    def test_general_ledger_hides_employee_detail_without_payroll_permission(self):
        self.run_action("payroll_accrue", {"employee": self.employee.id, "period": "2026-04"})
        viewer = get_user_model().objects.create_user(username="non-payroll-accountant")
        member = Membership.objects.create(business=self.business, user=viewer, permissions=["accounting.view", "cost.view"], all_locations=True, product_lines=["sponge", "adhesive", "shared"])
        result = report(Context(viewer, self.business, member), "general_ledger", {"as_of": "2026-04-30"})
        self.assertEqual(result["rows"], [])
        self.assertFalse(result["payroll_detail_included"])

    def test_product_line_cash_and_debt_not_misrepresented(self):
        with self.assertRaises(ValidationError):
            report(self.ctx, "receivables", {"line": "sponge"})
        with self.assertRaises(ValidationError):
            report(self.ctx, "cash_flow", {"line": "sponge"})
        summary = report(self.ctx, "dashboard", {"line": "sponge"})
        self.assertIsNone(summary["cash"])
        self.assertIsNone(summary["receivables"])

    def test_receipt_full_reversal_preserves_original_and_reopens_invoice(self):
        invoice = self.invoice("5000")
        receipt = self.run_action("receipt", {"invoice": invoice.id, "amount": "3500"})
        original_entry_ids = list(receipt.entries.values_list("id", flat=True))
        reversal = self.run_action("payment_reverse", {"payment": receipt.id, "reason": "Receipt amount entered twice on paper", "date": "2026-05-01"})
        self.assertEqual(outstanding(invoice), Decimal("5000"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("0"))
        self.assertEqual(list(receipt.entries.values_list("id", flat=True)), original_entry_ids)
        self.assertEqual(receipt.allocations.get().amount, Decimal("3500"))
        self.assertEqual(reversal.allocations.get().amount, Decimal("-3500"))
        april = report(self.ctx, "receivables", {"as_of": "2026-04-30"})
        may = report(self.ctx, "receivables", {"as_of": "2026-05-01"})
        self.assertEqual(Decimal(april["totals"]["outstanding"]), Decimal("1500"))
        self.assertEqual(Decimal(may["totals"]["outstanding"]), Decimal("5000"))
        self.assertEqual(report(self.ctx, "dashboard", {"as_of": "2026-05-01"})["collections"], "0.00")
        with self.assertRaises(ValidationError):
            self.run_action("payment_reverse", {"payment": receipt.id, "reason": "Already reversed", "date": "2026-05-01"})

    def test_deposit_reversal_cannot_leave_reusable_credit(self):
        deposit = self.run_action("receipt", {"party": self.customer.id, "amount": "1000"})
        self.run_action("payment_reverse", {"payment": deposit.id, "reason": "Wrong receipt"})
        self.assertEqual(balance(self.ctx, "DEPOSITS"), Decimal("0"))
        with self.assertRaises(ValidationError):
            self.run_action("customer_refund", {"deposit": deposit.id, "amount": "1", "reason": "Credit is already reversed"})
        invoice = self.invoice("1000")
        with self.assertRaises(ValidationError):
            self.run_action("allocate_deposit", {"deposit": deposit.id, "allocations": [{"invoice": invoice.id, "amount": "1"}]})

    def test_payment_with_consumed_deposit_cannot_reverse(self):
        deposit = self.run_action("receipt", {"party": self.customer.id, "amount": "1000"})
        invoice = self.invoice("500")
        self.run_action("allocate_deposit", {"deposit": deposit.id, "allocations": [{"invoice": invoice.id, "amount": "500"}]})
        with self.assertRaises(ValidationError):
            self.run_action("payment_reverse", {"payment": deposit.id, "reason": "Has downstream use"})

    def test_supplier_payment_reversal_restores_payable_and_cash(self):
        self.run_action("opening_cash", {"account": "CASH", "amount": "5000", "reason": "Reviewed opening"})
        bill = self.invoice("5000", supplier=True)
        payment = self.run_action("supplier_payment", {"invoice": bill.id, "amount": "5000"})
        self.run_action("payment_reverse", {"payment": payment.id, "reason": "Payment not actually sent"})
        self.assertEqual(outstanding(bill), Decimal("5000"))
        self.assertEqual(balance(self.ctx, "AP"), Decimal("-5000"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("5000"))
        self.assertEqual(balance(self.ctx, "EXPENSE"), Decimal("5000"))
        self.assert_balanced()

    def test_receipt_reversal_requires_cash_and_dedicated_permission(self):
        invoice = self.invoice("1000")
        receipt = self.run_action("receipt", {"invoice": invoice.id, "amount": "1000"})
        clerk = get_user_model().objects.create_user(username="collect-only")
        member = Membership.objects.create(business=self.business, user=clerk, permissions=["sales.collect"], all_locations=True, product_lines=["shared", "sponge", "adhesive"])
        with self.assertRaises(PermissionDenied):
            execute(Context(clerk, self.business, member), "payment_reverse", {"date": "2026-04-30", "payment": receipt.id, "reason": "No reversal grant"}, uuid4().hex)
        self.run_action("expense_post", {"amount": "1000"})
        with self.assertRaises(ValidationError):
            self.run_action("payment_reverse", {"payment": receipt.id, "reason": "Money already spent"})

    def test_cash_balances_flags_negative_location_without_hiding_in_company_total(self):
        self.run_action("opening_cash", {"account": "CASH", "amount": "1000", "reason": "Reviewed opening", "location": self.kabul.id})
        self.run_action("expense_post", {"amount": "200", "location": self.location.id})
        result = report(self.ctx, "cash_balances", {"as_of": "2026-04-30"})
        self.assertEqual(Decimal(result["totals"]["total"]), Decimal("800"))
        self.assertEqual(result["totals"]["negative_cash_accounts"], 1)
        herat = next(item for item in result["rows"] if item["location_id"] == self.location.id)
        self.assertTrue(herat["negative"])
        self.assertTrue(herat["review_required"])
        limited = report(self.ctx, "cash_balances", {"location": self.kabul.id, "as_of": "2026-04-30"})
        self.assertEqual(len(limited["rows"]), 1)
        self.assertEqual(limited["totals"]["negative_cash_accounts"], 0)

    def test_shared_expense_allocates_by_backed_weights_without_new_company_cost_or_cash(self):
        source = self.run_action("expense_post", {"amount": "1200", "description": "Shared office rent", "line": "shared"})
        original_entries = list(source.entries.values_list("id", flat=True))
        allocation = self.run_action("shared_cost_allocate", {"source": source.id, "amount": "1000", "reason": "Approved occupied area: Sponge 3 rooms, Adhesive 1 room", "weights": [{"line": "sponge", "weight": "3"}, {"line": "adhesive", "weight": "1"}]}, key="rent-allocation")
        self.assertEqual(allocation.result["weights"][0]["amount"], "750.00")
        self.assertEqual(allocation.result["weights"][1]["amount"], "250.00")
        self.assertEqual(allocation.result["remaining_shared"], "200.00")
        self.assertEqual(balance(self.ctx, "EXPENSE"), Decimal("1200"))
        self.assertEqual(balance(self.ctx, "CASH"), Decimal("-1200"))
        self.assertEqual(list(source.entries.values_list("id", flat=True)), original_entries)
        self.assertEqual(allocation.entries.filter(account__code__in=["CASH", "BANK"]).count(), 0)
        result = report(self.ctx, "profit_loss", {"line": "sponge", "as_of": "2026-04-30"})
        self.assertEqual(Decimal(result["totals"]["expenses"]), Decimal("750"))
        shared = report(self.ctx, "profit_loss", {"line": "shared", "as_of": "2026-04-30"})
        self.assertEqual(Decimal(shared["totals"]["expenses"]), Decimal("200"))
        self.run_action("shared_cost_allocate", {"source": source.id, "amount": "200", "reason": "Approved allocation of remaining shared rent", "weights": [{"line": "sponge", "weight": "1"}, {"line": "adhesive", "weight": "1"}]})
        self.assertEqual(balance(self.ctx, "EXPENSE"), Decimal("1200"))
        with self.assertRaises(ValidationError):
            self.run_action("shared_cost_allocate", {"source": source.id, "amount": "1", "reason": "Cannot allocate twice", "weights": [{"line": "sponge", "weight": "1"}]})
        self.assert_balanced()

    def test_shared_allocation_rejects_nonshared_payroll_and_invalid_weights(self):
        assigned = self.run_action("expense_post", {"amount": "100", "line": "sponge"})
        salary = self.run_action("expense_post", {"amount": "100", "expense_account": "SALARY"})
        shared = self.run_action("expense_post", {"amount": "100", "line": "shared"})
        for source, weights in [(assigned, [{"line": "adhesive", "weight": "1"}]), (salary, [{"line": "sponge", "weight": "1"}]), (shared, [{"line": "sponge", "weight": "1"}, {"line": "sponge", "weight": "2"}]), (shared, [{"line": "sponge", "weight": "0"}])]:
            with self.assertRaises(ValidationError):
                self.run_action("shared_cost_allocate", {"source": source.id, "reason": "Invalid source or driver", "weights": weights})
        self.assertEqual(Document.objects.filter(kind="shared_cost_allocate").count(), 0)

    def test_hourly_part_time_payroll_uses_attendance_hours_and_rate_history(self):
        hourly = Employee.objects.create(business=self.business, location=self.location, name="Part-time hourly", kind="part_time", rate="150", terms={"rate_basis": "hour", "rates": [{"effective_date": "1900-01-01", "rate": "125"}, {"effective_date": "2026-04-01", "rate": "150"}]})
        self.run_action("attendance_record", {"employee": hourly.id, "date": "2026-04-02", "days": "1", "hours": "4"})
        self.run_action("attendance_record", {"employee": hourly.id, "date": "2026-04-03", "days": "1", "hours": "6"})
        payroll = self.run_action("payroll_accrue", {"employee": hourly.id, "period": "2026-04"})
        self.assertEqual(payroll.amount, Decimal("1500"))
        self.assertEqual(payroll.result["approved_hours"], "10")
        self.assertEqual(payroll.result["rate_used"], "150")
        self.assertEqual(payroll.result["rate_basis"], "hour")
        self.assertIsNone(payroll.result["approved_days"])
        update_employee_rate(hourly, "200", "2026-05-01")
        hourly.save(update_fields=["rate", "terms"])
        may = self.run_action("payroll_accrue", {"employee": hourly.id, "period": "2026-05", "hours": "10", "date": "2026-05-31"})
        self.assertEqual(may.amount, Decimal("2000"))

    def test_hour_override_requires_payroll_approval(self):
        hourly = Employee.objects.create(business=self.business, location=self.location, name="Hourly", kind="part_time", rate="150", terms={"rate_basis": "hour"})
        clerk = get_user_model().objects.create_user(username="hours-clerk")
        member = Membership.objects.create(business=self.business, user=clerk, permissions=["payroll.post"], all_locations=True, product_lines=["shared"])
        with self.assertRaises(PermissionDenied):
            execute(Context(clerk, self.business, member), "payroll_accrue", {"date": "2026-04-30", "employee": hourly.id, "period": "2026-04", "hours": "100"}, uuid4().hex)

    def test_dashboard_rejects_mixed_document_totals_for_restricted_product_scope(self):
        mixed = self.fixture_document("sale", "5000", self.customer)
        journal(self.ctx, mixed, [{"account": "AR", "debit": "5000", "location": self.location}, {"account": "SALES", "credit": "3000", "line": "sponge", "location": self.location}, {"account": "SALES", "credit": "2000", "line": "adhesive", "location": self.location}])
        mixed.product_lines = ["sponge", "adhesive"]
        mixed.save(update_fields=["product_lines"])
        self.post_fixture(mixed)
        self.invoice("1000")
        viewer = get_user_model().objects.create_user(username="sponge-report-viewer")
        member = Membership.objects.create(business=self.business, user=viewer, permissions=["reports.view", "sales.view"], all_locations=True, product_lines=["shared", "sponge"])
        restricted = report(Context(viewer, self.business, member), "dashboard", {"as_of": "2026-04-30"})
        complete = report(self.ctx, "dashboard", {"as_of": "2026-04-30"})
        self.assertEqual(Decimal(restricted["sales"]), Decimal("1000"))
        self.assertEqual(Decimal(restricted["receivables"]), Decimal("1000"))
        self.assertEqual(Decimal(complete["sales"]), Decimal("6000"))
        self.assertEqual(Decimal(complete["receivables"]), Decimal("6000"))


    def test_daily_wages_can_be_accrued_and_paid_before_month_end_without_reuse(self):
        worker=Employee.objects.create(business=self.business,location=self.location,name="Daily paid worker",kind="daily",rate="600",advance_limit="1000")
        self.run_action("attendance_record",{"employee":worker.pk,"date":"2026-04-03","days":"1"})
        first=self.run_action("payroll_accrue",{"employee":worker.pk,"period":"2026-04","date":"2026-04-03"})
        self.assertEqual(first.amount,Decimal("600"))
        self.run_action("payroll_settle",{"payroll":first.pk,"amount":"600","date":"2026-04-03"})
        with self.assertRaises(ValidationError):
            self.run_action("payroll_accrue",{"employee":worker.pk,"period":"2026-04","date":"2026-04-03"})
        self.run_action("attendance_record",{"employee":worker.pk,"date":"2026-04-04","days":"1"})
        second=self.run_action("payroll_accrue",{"employee":worker.pk,"period":"2026-04","date":"2026-04-04"})
        self.assertEqual(second.amount,Decimal("600"))
        self.assertEqual(second.data["earning_from"],"2026-04-04")
        self.assertEqual(balance(self.ctx,"PAYROLL",employee=worker),Decimal("-600"))
        with self.assertRaises(ValidationError):
            self.run_action("attendance_record",{"employee":worker.pk,"date":"2026-04-02","days":"1"})

    def test_accepted_project_can_be_paid_on_completion_before_month_end(self):
        worker=Employee.objects.create(business=self.business,location=self.location,name="Project worker",kind="project",rate="0")
        earned=self.run_action("payroll_accrue",{"employee":worker.pk,"period":"2026-04","project_reference":"ACCEPTED-APRIL-10","gross":"3000","date":"2026-04-10"})
        settled=self.run_action("payroll_settle",{"payroll":earned.pk,"amount":"3000","date":"2026-04-10"})
        self.assertEqual(settled.amount,Decimal("3000"))
        self.assertEqual(balance(self.ctx,"PAYROLL",employee=worker),Decimal("0"))
        with self.assertRaises(ValidationError):
            self.run_action("payroll_accrue",{"employee":worker.pk,"period":"2026-04","project_reference":"ACCEPTED-APRIL-10","gross":"3000","date":"2026-04-11"})
