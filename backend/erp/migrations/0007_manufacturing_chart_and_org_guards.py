from django.db import migrations

META = {'ACCRUED_EXPENSES': ('20500', 'current_liabilities'),
 'ACCUM_DEPR': ('15900', 'noncurrent_assets'),
 'ADVANCES': ('13100', 'current_assets'),
 'AP': ('20000', 'current_liabilities'),
 'AR': ('11000', 'current_assets'),
 'ASSETS': ('15000', 'noncurrent_assets'),
 'BAD_DEBTS': ('64100', 'other_operating_expenses'),
 'BANK': ('10100', 'current_assets'),
 'BANK_FEES': ('64000', 'other_operating_expenses'),
 'CASH': ('10000', 'current_assets'),
 'COGS': ('50000', 'cost_of_sales'),
 'COST_CLEARING': ('13920', 'current_assets'),
 'CURRENT_LEASE': ('21100', 'current_liabilities'),
 'DELIVERY': ('63000', 'selling_expenses'),
 'DEPOSITS': ('20400', 'current_liabilities'),
 'DEPRECIATION': ('61100', 'administrative_expenses'),
 'DRAWINGS': ('32000', 'equity'),
 'EQUITY': ('30000', 'equity'),
 'EXPENSE': ('61900', 'other_operating_expenses'),
 'FACTORY_RENT': ('62100', 'other_operating_expenses'),
 'FACTORY_UTILITIES': ('62200', 'other_operating_expenses'),
 'FG': ('12300', 'current_assets'),
 'GRNI': ('20100', 'current_liabilities'),
 'IMPAIRMENT': ('50200', 'cost_of_sales'),
 'INCOME_TAX_EXPENSE': ('80000', 'income_tax'),
 'INCOME_TAX_PAYABLE': ('20600', 'current_liabilities'),
 'INTEREST_EXPENSE': ('71000', 'finance_costs'),
 'INTEREST_INCOME': ('42100', 'finance_income'),
 'INVENTORY_ALLOWANCE': ('12900', 'current_assets'),
 'INVESTMENT_INCOME': ('42000', 'investing_income'),
 'LABOR_CLEARING': ('13910', 'current_assets'),
 'LONG_TERM_DEPOSITS': ('16000', 'noncurrent_assets'),
 'LONG_TERM_LEASE': ('25100', 'noncurrent_liabilities'),
 'LONG_TERM_LOANS': ('25000', 'noncurrent_liabilities'),
 'MARKETING': ('63100', 'selling_expenses'),
 'OFFICE_SUPPLIES': ('61500', 'administrative_expenses'),
 'OTHER_INCOME': ('41000', 'other_operating_income'),
 'OTHER_RECEIVABLES': ('11100', 'current_assets'),
 'OVERHEAD': ('62000', 'other_operating_expenses'),
 'PAYROLL': ('20200', 'current_liabilities'),
 'PAYROLL_DEDUCTIONS': ('20700', 'current_liabilities'),
 'PREPAID': ('13300', 'current_assets'),
 'PROFESSIONAL_FEES': ('61400', 'administrative_expenses'),
 'RAW': ('12100', 'current_assets'),
 'RENT': ('61200', 'administrative_expenses'),
 'REPAIRS': ('62300', 'other_operating_expenses'),
 'RETAINED_EARNINGS': ('31000', 'equity'),
 'SALARY': ('61000', 'administrative_expenses'),
 'SALES': ('40000', 'revenue'),
 'SHORT_TERM_LOANS': ('21000', 'current_liabilities'),
 'SUPPLIER_DEPOSITS': ('13200', 'current_assets'),
 'TAX': ('20300', 'current_liabilities'),
 'TRANSIT': ('12500', 'current_assets'),
 'TRIM': ('12400', 'current_assets'),
 'UTILITIES': ('61300', 'administrative_expenses'),
 'WASTE': ('50100', 'cost_of_sales'),
 'WIP': ('12200', 'current_assets')}
EXTRA = {'ACCRUED_EXPENSES': ('Accrued expenses',
                      'liability',
                      '20500',
                      'current_liabilities'),
 'BAD_DEBTS': ('Receivable impairment',
               'expense',
               '64100',
               'other_operating_expenses'),
 'BANK_FEES': ('Bank service charges',
               'expense',
               '64000',
               'other_operating_expenses'),
 'CURRENT_LEASE': ('Current lease liabilities',
                   'liability',
                   '21100',
                   'current_liabilities'),
 'DELIVERY': ('Outbound delivery', 'expense', '63000', 'selling_expenses'),
 'FACTORY_RENT': ('Factory rent / unabsorbed overhead',
                  'expense',
                  '62100',
                  'other_operating_expenses'),
 'FACTORY_UTILITIES': ('Factory utilities / unabsorbed overhead',
                       'expense',
                       '62200',
                       'other_operating_expenses'),
 'INCOME_TAX_EXPENSE': ('Income tax expense', 'expense', '80000', 'income_tax'),
 'INCOME_TAX_PAYABLE': ('Income tax payable',
                        'liability',
                        '20600',
                        'current_liabilities'),
 'INTEREST_EXPENSE': ('Finance costs', 'expense', '71000', 'finance_costs'),
 'INTEREST_INCOME': ('Interest income', 'income', '42100', 'finance_income'),
 'INVESTMENT_INCOME': ('Investment income',
                       'income',
                       '42000',
                       'investing_income'),
 'LONG_TERM_DEPOSITS': ('Long-term security deposits',
                        'asset',
                        '16000',
                        'noncurrent_assets'),
 'LONG_TERM_LEASE': ('Non-current lease liabilities',
                     'liability',
                     '25100',
                     'noncurrent_liabilities'),
 'LONG_TERM_LOANS': ('Long-term borrowings',
                     'liability',
                     '25000',
                     'noncurrent_liabilities'),
 'MARKETING': ('Marketing and selling', 'expense', '63100', 'selling_expenses'),
 'OFFICE_SUPPLIES': ('Office supplies',
                     'expense',
                     '61500',
                     'administrative_expenses'),
 'OTHER_INCOME': ('Other operating income',
                  'income',
                  '41000',
                  'other_operating_income'),
 'OTHER_RECEIVABLES': ('Other receivables', 'asset', '11100', 'current_assets'),
 'PAYROLL_DEDUCTIONS': ('Payroll deductions payable',
                        'liability',
                        '20700',
                        'current_liabilities'),
 'PREPAID': ('Prepaid expenses', 'asset', '13300', 'current_assets'),
 'PROFESSIONAL_FEES': ('Professional fees',
                       'expense',
                       '61400',
                       'administrative_expenses'),
 'RENT': ('Office rent', 'expense', '61200', 'administrative_expenses'),
 'REPAIRS': ('Repairs and maintenance',
             'expense',
             '62300',
             'other_operating_expenses'),
 'RETAINED_EARNINGS': ('Retained earnings', 'equity', '31000', 'equity'),
 'SHORT_TERM_LOANS': ('Short-term borrowings',
                      'liability',
                      '21000',
                      'current_liabilities'),
 'UTILITIES': ('Office utilities',
               'expense',
               '61300',
               'administrative_expenses')}

def populate(apps,schema_editor):
    Account=apps.get_model('erp','Account'); Business=apps.get_model('erp','Business'); Employee=apps.get_model('erp','Employee')
    for business in Business.objects.all().iterator():
        for code,(name,category,number,group) in EXTRA.items():
            Account.objects.get_or_create(business=business,code=code,defaults={'name':name,'category':category,'control':False})
        for account in Account.objects.filter(business=business):
            if account.code in META:
                number,group=META[account.code]
                if not Account.objects.filter(business=business,number=number).exclude(pk=account.pk).exists(): account.number=number
                account.statement_group=group
                account.save(update_fields=['number','statement_group'])
    for employee in Employee.objects.filter(code='').iterator():
        employee.code='EMP-'+str(employee.pk).zfill(5);employee.save(update_fields=['code'])

SQL = r"""
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_department FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE TRIGGER business_scope BEFORE INSERT OR UPDATE ON erp_position FOR EACH ROW EXECUTE FUNCTION erp_guard_business();
CREATE OR REPLACE FUNCTION erp_guard_employee_org() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE dep_location bigint; pos_department bigint;
BEGIN
 IF NEW.department_id IS NOT NULL THEN
  SELECT location_id INTO dep_location FROM erp_department WHERE id=NEW.department_id;
  IF dep_location IS NOT NULL AND dep_location<>NEW.location_id THEN RAISE EXCEPTION 'Employee department location mismatch'; END IF;
 END IF;
 IF NEW.position_id IS NOT NULL THEN
  SELECT department_id INTO pos_department FROM erp_position WHERE id=NEW.position_id;
  IF pos_department IS NOT NULL AND pos_department IS DISTINCT FROM NEW.department_id THEN RAISE EXCEPTION 'Employee position department mismatch'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER employee_org BEFORE INSERT OR UPDATE ON erp_employee FOR EACH ROW EXECUTE FUNCTION erp_guard_employee_org();
"""
REVERSE="DROP TRIGGER IF EXISTS business_scope ON erp_department; DROP TRIGGER IF EXISTS business_scope ON erp_position; DROP FUNCTION IF EXISTS erp_guard_employee_org() CASCADE;"
class Migration(migrations.Migration):
    dependencies=[('erp','0006_employee_profiles_and_account_groups')]
    operations=[migrations.RunPython(populate,migrations.RunPython.noop),migrations.RunSQL(SQL,REVERSE)]
