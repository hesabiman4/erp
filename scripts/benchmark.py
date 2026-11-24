"""Small reproducible synthetic measurement, restricted to verify_* databases."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--items',type=int,default=1000);args=parser.parse_args()
if not re.fullmatch(r'verify_[a-z0-9_]{1,45}',args.database) or not 1<=args.items<=2000: raise SystemExit('Use a verify_* database and 1–2000 synthetic items.')
os.environ['PGDATABASE']=args.database;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');sys.path.insert(0,str(ROOT/'backend'))
import django
django.setup()
from django.contrib.auth.models import User
from erp.models import Business, Membership, Location, Warehouse, Product, StockPool, Document
from erp.core import Context, execute
from erp.seed import bootstrap
from erp.reports import report

user=User.objects.get(username='owner')
business,_=Business.objects.get_or_create(slug='benchmark-only',defaults={'name':'Synthetic performance verification','manufacturing_mode':'trading','settings':{'demo':True}})
bootstrap(business)
Membership.objects.get_or_create(business=business,user=user,defaults={'permissions':['*'],'all_locations':True,'product_lines':['sponge','adhesive','shared']})
location,_=Location.objects.get_or_create(business=business,code='BENCH',defaults={'name':'Benchmark location'})
warehouse,_=Warehouse.objects.get_or_create(business=business,location=location,name='Benchmark store')
products=[]
for i in range(args.items):
    p,_=Product.objects.get_or_create(business=business,code=f'BENCH-{i:05d}',defaults={'name':f'Synthetic item {i:05d}','unit':'each','line':'shared','price':'2'})
    products.append(p)
key=f'benchmark-opening-{args.items}'
if not Document.objects.filter(business=business,idempotency_key=key).exists():
    execute(Context(user,business),'stock_opening',{'warehouse':warehouse.pk,'lines':[{'product':p.pk,'quantity':'100','value':'100'} for p in products]},key)
measurements={}
for name in ('inventory_reconciliation','trial_balance','profit_loss','cash_flow'):
    start=perf_counter();result=report(Context(user,business),name,{});elapsed=perf_counter()-start
    measurements[name]={'seconds':round(elapsed,4),'rows':len(result.get('rows',[])),'totals':result.get('totals',{})}
    if name=='inventory_reconciliation': assert result['totals']['difference']=='0.00'
start=perf_counter(); matches=list(Product.objects.filter(business=business,code__icontains='BENCH-009')[:100]);lookup=perf_counter()-start
result={'database':args.database,'synthetic_items':len(products),'stock_pools':StockPool.objects.filter(business=business).count(),'lookup_seconds':round(lookup,4),'lookup_matches':len(matches),'reports':measurements,'note':'Local single-user synthetic benchmark, not a production capacity guarantee.'}
(ROOT/'.local'/'benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
