"""Measure actual ERP workflows in an explicitly isolated verify_* database.

Creates only a labelled synthetic workspace, ordinary posted stock/sales and
ordinary non-posting drafts. No fabricated posted ledgers or live resets.
"""
import argparse,json,os,re,sys,statistics
from pathlib import Path
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--products',type=int,default=400)
    parser.add_argument('--sales',type=int,default=200)
    parser.add_argument('--drafts',type=int,default=1000)
    parser.add_argument('--blocks',type=int,default=100)
    parser.add_argument('--runs',type=int,default=5)
    parser.add_argument('--output',type=Path,default=ROOT/'.local/design/usability-benchmark.json')
    args=parser.parse_args()
    if not re.fullmatch(r'verify_[a-z0-9_]{1,45}',args.database):parser.error('Only a named local verify_* database is accepted.')
    for name,low,high in [('products',1,2000),('sales',0,3000),('drafts',0,5000),('blocks',1,1000),('runs',1,10)]:
        if not low<=getattr(args,name)<=high:parser.error('Dataset or repeat count exceeds the bounded benchmark limit.')
    os.environ['PGDATABASE']=args.database;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');sys.path.insert(0,str(ROOT/'backend'))
    import django
    django.setup()
    from django.conf import settings
    if settings.DATABASES['default']['HOST'] not in ('127.0.0.1','localhost') or str(settings.DATABASES['default']['PORT'])!='55432':parser.error('This benchmark only writes to the project local PostgreSQL cluster.')
    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test import Client
    from django.test.utils import CaptureQueriesContext
    from erp.models import Business,Membership,Location,Warehouse,Product,Party,Document,Block,Entry
    from erp.seed import bootstrap
    from erp.core import Context,execute,create_draft
    from erp.reports import report
    owner=get_user_model().objects.get(username='owner')
    business,created=Business.objects.get_or_create(slug='workflow-benchmark-v5',defaults={'name':'SYNTHETIC workflow performance pilot','settings':{'demo':True}})
    if created:bootstrap(business)
    if not business.settings.get('demo'):raise ValueError('Existing benchmark workspace is not marked synthetic.')
    Membership.objects.get_or_create(business=business,user=owner,defaults={'permissions':['*'],'all_locations':True,'product_lines':['sponge','adhesive','shared']})
    ctx=Context(owner,business)
    location,_=Location.objects.get_or_create(business=business,code='PERF',defaults={'name':'Synthetic performance location'})
    wh,_=Warehouse.objects.get_or_create(business=business,location=location,name='Synthetic performance store')
    customer,_=Party.objects.get_or_create(business=business,name='Synthetic benchmark buyer',kind='customer')
    products=[]
    for i in range(args.products):
        product,_=Product.objects.get_or_create(business=business,code=f'PERF-{i:05}',defaults={'name':f'Synthetic measured item{i:05}','line':'shared','unit':'each','price':'2'})
        products.append(product)
    for start in range(0,args.products,500):
        key=f'workflow-stock-{start}'
        if not Document.objects.filter(business=business,idempotency_key=key).exists():
            execute(ctx,'stock_opening',{'warehouse':wh.pk,'lines':[{'product':p.pk,'quantity':'10000','value':'10000'} for p in products[start:start+500]]},key)
    sponge,_=Product.objects.get_or_create(business=business,code='PERF-FOAM',defaults={'name':'Synthetic grade label45','line':'sponge','unit':'cm','price':'100'})
    for start in range(0,args.blocks,100):
        key=f'workflow-blocks-{start}'
        if not Document.objects.filter(business=business,idempotency_key=key).exists():
            execute(ctx,'stock_opening',{'warehouse':wh.pk,'lines':[{'product':sponge.pk,'value':str(1000*min(100,args.blocks-start)),'blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000'} for _ in range(min(100,args.blocks-start))]}]},key)
    for i in range(args.sales):
        key=f'workflow-sale-{i}'
        if not Document.objects.filter(business=business,idempotency_key=key).exists():execute(ctx,'sale',{'warehouse':wh.pk,'party':customer.pk,'lines':[{'product':products[i%len(products)].pk,'quantity':'1','unit_price':'2'}]},key)
    for i in range(args.drafts):create_draft(ctx,'sale',{'warehouse':wh.pk,'lines':[]},f'workflow-draft-{i}')
    client=Client(HTTP_HOST='localhost');client.force_login(owner);headers={'HTTP_X_BUSINESS_ID':str(business.pk)}
    paths={'workspace':'/api/workspace/','invoice_page':'/api/documents/?kind=sale&state=posted&limit=20','counter_pieces':f'/api/counter/availability/?warehouse={wh.pk}&product={sponge.pk}&thickness_mm=22','crm_page':'/api/crm/?limit=20','trial_balance':'/api/reports/trial_balance/','inventory_control':'/api/reports/inventory_reconciliation/'}
    measurements={}
    for name,path in paths.items():
        samples=[];counts=[];byte_counts=[]
        for _ in range(args.runs):
            connection.queries_log.clear()
            started=perf_counter()
            with CaptureQueriesContext(connection) as queries:response=client.get(path,**headers)
            elapsed=perf_counter()-started
            if response.status_code!=200:raise ValueError(f'{name} failed with HTTP{response.status_code}; no successful timing claimed.')
            samples.append(elapsed);counts.append(len(queries));byte_counts.append(len(response.content))
        ordered=sorted(samples)
        measurements[name]={'runs':args.runs,'median_seconds':round(statistics.median(samples),4),'p95_seconds':round(ordered[min(len(ordered)-1,max(0,int(len(ordered)*.95)))],4),'max_queries':max(counts),'response_bytes':max(byte_counts)}
    checks={}
    for name in ('trial_balance','balance_sheet','cash_flow','inventory_reconciliation'):
        totals=report(ctx,name,{})['totals'];checks[name]=totals
        if 'difference' in totals and totals['difference']!='0.00':raise ValueError(f'{name} does not reconcile.')
    result={'database':args.database,'dataset':{'products':Product.objects.filter(business=business).count(),'posted_sales':Document.objects.filter(business=business,kind='sale',state='posted').count(),'drafts':Document.objects.filter(business=business,state='draft').count(),'blocks':Block.objects.filter(business=business).count(),'journal_lines':Entry.objects.filter(document__business=business).count()},'measurements':measurements,'reconciliation':checks,'scope':'Local single-user synthetic timing, including application queries; not a hardware, concurrent-user or production capacity guarantee.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
