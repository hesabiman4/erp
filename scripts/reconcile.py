"""Read-only financial/stock reconciliation for the configured local instance."""
import json
import os
from pathlib import Path
import sys
from decimal import Decimal

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'backend'));os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.contrib.auth.models import User
from erp.models import Business
from erp.core import Context
from erp.reports import report

owner=User.objects.get(username=os.environ.get('ERP_RECONCILE_USER','owner'))
results=[]
for business in Business.objects.filter(membership__user=owner,membership__active=True).distinct():
    ctx=Context(owner,business)
    trial=report(ctx,'trial_balance',{})['totals']
    sheet=report(ctx,'balance_sheet',{})['totals']
    stock=report(ctx,'inventory_reconciliation',{})['totals']
    cash=report(ctx,'cash_flow',{})['totals']
    from erp.foreign import reconcile as foreign_reconcile
    foreign=foreign_reconcile(ctx)
    for values in [trial,sheet,stock,cash]:
        if 'difference' in values:
            assert Decimal(values['difference']) == 0, (business.slug, values)
    assert Decimal(foreign['difference'])==0,(business.slug,foreign)
    results.append({'business':business.slug,'trial_balance':trial,'balance_sheet':sheet,'inventory':stock,'cash_flow':cash,'foreign':foreign})
result={'reconciled':True,'businesses':results}
output=Path(os.environ.get('ERP_RECONCILE_OUTPUT',str(ROOT/'.local'/'live-reconciliation.json')))
output.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
