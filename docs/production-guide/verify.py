"""Read-only verification of the separately named production-guide database."""
import json,os,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings',PGDATABASE='verify_production_guide_20261123')
sys.path.insert(0,str(ROOT/'backend'))
import django
django.setup()
from django.db import connection,transaction
from django.db.models import Sum
from erp.models import Business,Document,Entry,StockPool,Block,BOM

assert connection.settings_dict['NAME']=='verify_production_guide_20261123'
state=json.loads((ROOT/'.local/production_guide_20261123/progress.json').read_text(encoding='utf-8'))
assert state['finished'] and len(state['done'])==40
checks=[]
def check(title,condition,observed=None):
    checks.append({'check':title,'passed':bool(condition),'observed':observed})
    assert condition,(title,observed)

with transaction.atomic():
    with connection.cursor() as cursor:cursor.execute('SET TRANSACTION READ ONLY')
    business=Business.objects.get(pk=state['business'])
    def balance(code):
        row=Entry.objects.filter(document__business=business,account__code=code).aggregate(debit=Sum('debit'),credit=Sum('credit'))
        return (row['debit'] or Decimal(0))-(row['credit'] or Decimal(0))
    def qty(key,warehouse):
        return StockPool.objects.filter(business=business,product_id=state['items'][key]['id'],warehouse_id=warehouse).aggregate(q=Sum('quantity'))['q'] or Decimal(0)
    store=state['items']['store']['id'];floor=state['items']['03-floor']['id'];herat=state['items']['05-herat-store']['id']
    block=Block.objects.get(pk=state['block'])
    value=StockPool.objects.filter(business=business).aggregate(v=Sum('value'))['v']
    check('Raw A factory90kg',qty('06-raw-a',store)==90,str(qty('06-raw-a',store)))
    check('Raw B factory90kg',qty('07-raw-b',store)==90,str(qty('07-raw-b',store)))
    check('Raw adhesive factory30kg',qty('11-raw-glue',store)==30,str(qty('11-raw-glue',store)))
    check('Floor unused stock fully returned',qty('06-raw-a',floor)==0 and qty('07-raw-b',floor)==0)
    check('Finished block ready1000mm in Herat',block.remaining_height_mm==1000 and block.reserved_height_mm==0 and block.warehouse_id==herat and block.status=='ready',{'height_mm':str(block.remaining_height_mm),'warehouse':block.warehouse_id,'status':block.status})
    check('Sponge100cm in Herat',qty('08-sponge',herat)==100,str(qty('08-sponge',herat)))
    check('Saleable top1 and bottom1',qty('09-top',store)==1 and qty('10-bottom',store)==1)
    check('Adhesive20kg cost2500',qty('12-glue',store)==20 and StockPool.objects.get(business=business,product_id=state['items']['12-glue']['id'],warehouse_id=store).value==2500)
    check('Inventory carrying value34500',value==34500,str(value))
    check('Abnormal loss1000',balance('WASTE')==1000,str(balance('WASTE')))
    check('WIP GRNI conversion clearing all zero',all(balance(code)==0 for code in ['WIP','GRNI','COST_CLEARING']))
    check('Supplier payable35500',balance('AP')==-35500,str(balance('AP')))
    check('No sale and no BOM',not Document.objects.filter(business=business,kind='sale').exists() and not BOM.objects.filter(business=business).exists())
    check('Only adhesive one-shot actually posted',Document.objects.filter(business=business,kind='production').count()==1)
    check('Every posted journal balanced',all(sum((e.debit-e.credit for e in doc.entries.all()),Decimal(0))==0 for doc in Document.objects.filter(business=business,state='posted')))
    difference=sum((e.debit-e.credit for e in Entry.objects.filter(document__business=business)),Decimal(0))
    check('Whole trial balance balanced',difference==0,str(difference))
    check('Inventory control equals stock value',sum(balance(code) for code in ['RAW','FG','TRIM','TRANSIT'])==value)
    check('Nonnegative physical stock',not StockPool.objects.filter(business=business,quantity__lt=0).exists())
    report={'database':connection.settings_dict['NAME'],'synthetic_only':True,'business':business.pk,'documents':Document.objects.filter(business=business).count(),
            'actual_ui_screenshots':len(state['captures']),'steps':40,'all_checks_passed':True,'checks':checks}
(ROOT/'docs/production-guide/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':len(checks),'all_checks_passed':True,'documents':report['documents']}))
