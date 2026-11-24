"""Manufacturing chart template. Numbers are editable conventions, not an IFRS mandate."""
GROUP_CATEGORIES = {
    'current_assets':'asset','noncurrent_assets':'asset','current_liabilities':'liability','noncurrent_liabilities':'liability','equity':'equity',
    'revenue':'income','other_operating_income':'income','investing_income':'income','finance_income':'income',
    'cost_of_sales':'expense','administrative_expenses':'expense','selling_expenses':'expense','other_operating_expenses':'expense','finance_costs':'expense','income_tax':'expense',
}
# Internal codes are stable posting keys. Display numbers never drive journal routing.
ACCOUNT_META = {
 'CASH':('10000','current_assets'),'BANK':('10100','current_assets'),'AR':('11000','current_assets'),
 'RAW':('12100','current_assets'),'WIP':('12200','current_assets'),'FG':('12300','current_assets'),'TRIM':('12400','current_assets'),'TRANSIT':('12500','current_assets'),'INVENTORY_ALLOWANCE':('12900','current_assets'),
 'ADVANCES':('13100','current_assets'),'SUPPLIER_DEPOSITS':('13200','current_assets'),'LABOR_CLEARING':('13910','current_assets'),'COST_CLEARING':('13920','current_assets'),
 'ASSETS':('15000','noncurrent_assets'),'ACCUM_DEPR':('15900','noncurrent_assets'),
 'AP':('20000','current_liabilities'),'GRNI':('20100','current_liabilities'),'PAYROLL':('20200','current_liabilities'),'TAX':('20300','current_liabilities'),'DEPOSITS':('20400','current_liabilities'),
 'EQUITY':('30000','equity'),'DRAWINGS':('32000','equity'),'SALES':('40000','revenue'),
 'COGS':('50000','cost_of_sales'),'WASTE':('50100','cost_of_sales'),'IMPAIRMENT':('50200','cost_of_sales'),
 'SALARY':('61000','administrative_expenses'),'DEPRECIATION':('61100','administrative_expenses'),'EXPENSE':('61900','other_operating_expenses'),'OVERHEAD':('62000','other_operating_expenses'),
}
EXTRA_ACCOUNTS = {
 'COMMISSION':('Sales commissions','expense','63200','selling_expenses'),
 'FX_CUSTOMER_DEPOSITS':('Refundable foreign customer deposits','liability','21310','current_liabilities'),
 'FX_SUPPLIER_DEPOSITS':('Refundable foreign supplier deposits','asset','11310','current_assets'),
 'FX_CASH':('Foreign currency cash','asset','10010','current_assets'),
 'FX_BANK':('Foreign currency bank','asset','10110','current_assets'),
 'FX_TRANSIT':('Remittances in transit','asset','10200','current_assets'),
 'FX_GAIN':('Foreign exchange gains','income','43000','other_operating_income'),
 'FX_LOSS':('Foreign exchange losses','expense','64200','other_operating_expenses'),
 'OTHER_RECEIVABLES':('Other receivables','asset','11100','current_assets'),
 'PREPAID':('Prepaid expenses','asset','13300','current_assets'),
 'LONG_TERM_DEPOSITS':('Long-term security deposits','asset','16000','noncurrent_assets'),
 'ACCRUED_EXPENSES':('Accrued expenses','liability','20500','current_liabilities'),
 'INCOME_TAX_PAYABLE':('Income tax payable','liability','20600','current_liabilities'),
 'PAYROLL_DEDUCTIONS':('Payroll deductions payable','liability','20700','current_liabilities'),
 'SHORT_TERM_LOANS':('Short-term borrowings','liability','21000','current_liabilities'),
 'CURRENT_LEASE':('Current lease liabilities','liability','21100','current_liabilities'),
 'LONG_TERM_LOANS':('Long-term borrowings','liability','25000','noncurrent_liabilities'),
 'LONG_TERM_LEASE':('Non-current lease liabilities','liability','25100','noncurrent_liabilities'),
 'RETAINED_EARNINGS':('Retained earnings','equity','31000','equity'),
 'OTHER_INCOME':('Other operating income','income','41000','other_operating_income'),
 'INVESTMENT_INCOME':('Investment income','income','42000','investing_income'),
 'INTEREST_INCOME':('Interest income','income','42100','finance_income'),
 'RENT':('Office rent','expense','61200','administrative_expenses'),
 'UTILITIES':('Office utilities','expense','61300','administrative_expenses'),
 'PROFESSIONAL_FEES':('Professional fees','expense','61400','administrative_expenses'),
 'OFFICE_SUPPLIES':('Office supplies','expense','61500','administrative_expenses'),
 'FACTORY_RENT':('Factory rent / unabsorbed overhead','expense','62100','other_operating_expenses'),
 'FACTORY_UTILITIES':('Factory utilities / unabsorbed overhead','expense','62200','other_operating_expenses'),
 'REPAIRS':('Repairs and maintenance','expense','62300','other_operating_expenses'),
 'DELIVERY':('Outbound delivery','expense','63000','selling_expenses'),
 'MARKETING':('Marketing and selling','expense','63100','selling_expenses'),
 'BANK_FEES':('Bank service charges','expense','64000','other_operating_expenses'),
 'BAD_DEBTS':('Receivable impairment','expense','64100','other_operating_expenses'),
 'INTEREST_EXPENSE':('Finance costs','expense','71000','finance_costs'),
 'INCOME_TAX_EXPENSE':('Income tax expense','expense','80000','income_tax'),
}
for _code, (_, _, _number, _group) in EXTRA_ACCOUNTS.items():
    ACCOUNT_META[_code] = (_number, _group)

def account_group(account):
    return account.statement_group or ACCOUNT_META.get(account.code,('',{'asset':'current_assets','liability':'current_liabilities','equity':'equity','income':'other_operating_income','expense':'other_operating_expenses'}[account.category]))[1]
