"""Synthetic chart/bootstrap helpers shared by explicit demo setup and tests."""
from .models import Account, Business, Location, Warehouse
from .chart import ACCOUNT_META, EXTRA_ACCOUNTS

CHART={
 'CASH':('Cash','asset',True),'BANK':('Bank','asset',True),'AR':('Customer receivables','asset',True),'SUPPLIER_DEPOSITS':('Supplier deposits','asset',True),
 'RAW':('Raw materials','asset',True),'WIP':('Work in progress','asset',True),'FG':('Finished goods','asset',True),'TRIM':('Saleable trims','asset',True),'TRANSIT':('Inventory in transit','asset',True),
 'ADVANCES':('Employee advances','asset',True),'LABOR_CLEARING':('Production labor clearing','asset',True),'COST_CLEARING':('Production conversion clearing','asset',True),
 'ASSETS':('Fixed assets','asset',True),'ACCUM_DEPR':('Accumulated depreciation','asset',True),'INVENTORY_ALLOWANCE':('Inventory valuation allowance','asset',True),
 'AP':('Supplier payables','liability',True),'GRNI':('Goods received not invoiced','liability',True),'PAYROLL':('Salary payable','liability',True),'DEPOSITS':('Customer deposits','liability',True),'TAX':('Tax payable','liability',True),
 'EQUITY':('Opening capital','equity',False),'DRAWINGS':('Owner drawings','equity',False),'SALES':('External sales','income',True),
 'COGS':('Cost of goods sold','expense',True),'WASTE':('Abnormal waste and stock losses','expense',True),'SALARY':('Administrative wages','expense',False),'OVERHEAD':('Production overhead','expense',False),'EXPENSE':('Operating expenses','expense',False),'DEPRECIATION':('Depreciation','expense',False),'IMPAIRMENT':('Inventory write-down expense','expense',False),
}

def bootstrap(business):
    chart={**CHART,**{code:(item[0],item[1],code in {'FX_CASH','FX_BANK','FX_TRANSIT','FX_CUSTOMER_DEPOSITS','FX_SUPPLIER_DEPOSITS'}) for code,item in EXTRA_ACCOUNTS.items()}}
    for code,(name,category,control) in chart.items():
        number,group=ACCOUNT_META.get(code,('',''))
        Account.objects.get_or_create(business=business,code=code,defaults={'name':name,'category':category,'control':control,'number':number,'statement_group':group})
    return business
