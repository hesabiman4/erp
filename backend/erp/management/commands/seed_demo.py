import json
import secrets
import os
from pathlib import Path
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from erp.models import *
from erp.seed import bootstrap
from erp.core import Context, execute

class Command(BaseCommand):
    help='Seed explicitly marked synthetic local businesses and generated role credentials.'
    def add_arguments(self,parser): parser.add_argument('--demo',action='store_true')
    @transaction.atomic
    def handle(self,*args,**options):
        if not options['demo']: raise CommandError('Use --demo to explicitly authorize synthetic demo seeding.')
        business,_=Business.objects.get_or_create(slug='sponge-demo',defaults={'name':'اسفنج و چسپ · Demo','settings':{'demo':True}})
        if not business.settings.get('demo'): raise CommandError('Existing business is not a marked demo target.')
        furniture,_=Business.objects.get_or_create(slug='furniture-demo',defaults={'name':'مبلمان شهر · Demo','manufacturing_mode':'bom','settings':{'demo':True}})
        if not furniture.settings.get('demo'): raise CommandError('Existing furniture workspace is not a marked demo target; no data was changed.')
        bootstrap(business); bootstrap(furniture)
        sites={}
        for code,name,name_en in [('FACTORY','فابریکه','Factory'),('HERAT','دفتر مرکزی هرات','Herat main office'),('KABUL','نماینده گی کابل','Kabul branch')]:
            loc,_=Location.objects.get_or_create(business=business,code=code,defaults={'name':name,'name_fa':name,'name_en':name_en})
            store,_=Warehouse.objects.get_or_create(business=business,location=loc,kind='store',defaults={'name':name+' — گدام','name_fa':name+' — گدام','name_en':name_en+' warehouse'})
            sites[code]=(loc,store)
        factory=sites['FACTORY'][0]
        Warehouse.objects.get_or_create(business=business,location=factory,kind='floor',defaults={'name':'کف تولید','name_fa':'کف تولید','name_en':'Production floor'})
        Warehouse.objects.get_or_create(business=business,location=factory,kind='transit',defaults={'name':'موجودی در مسیر','name_fa':'موجودی در مسیر','name_en':'In transit'})
        floc,_=Location.objects.get_or_create(business=furniture,code='HERAT',defaults={'name':'کارگاه مبلمان'})
        Warehouse.objects.get_or_create(business=furniture,location=floc,kind='store',defaults={'name':'گدام مبلمان'})
        path=Path(os.environ.get('ERP_DEMO_CREDENTIALS_PATH',settings.ROOT_DIR/'.local'/'demo-credentials.json'))
        existing=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        credentials=dict(existing)
        sales=['sales.view','sales.post','sales.credit','sales.collect','inventory.view','finance.receive','documents.print','drafts.create','attachments.create']
        roles=[('owner','Owner',['*'],None,business),('herat_cashier','Herat cashier',sales,'HERAT',business),('kabul_cashier','Kabul cashier',sales,'KABUL',business),('factory','Production',['production.view','production.post','production.cost','consumption.view','cost.view','inventory.view','inventory.raw','inventory.post','transfers.view','transfers.post','documents.print','drafts.create'],'FACTORY',business),('kabul_storekeeper','Kabul storekeeper',['inventory.view','inventory.count','inventory.adjust','inventory.post','transfers.view','transfers.post','documents.print','drafts.create'],'KABUL',business),('accountant','Accountant',['accounting.*','finance.*','payroll.*','cost.view','consumption.view','inventory.view','inventory.raw','reports.view','reports.export','documents.view','documents.print','audit.view','production.cost','production.post','purchases.*','sales.view','transfers.view','drafts.create'],None,business),('furniture','Furniture',['*'],None,furniture)]
        for username,role,permissions,scope,biz in roles:
            user,created=User.objects.get_or_create(username=username)
            if created:
                password=secrets.token_urlsafe(15); user.set_password(password); user.first_name=role; user.save()
                credentials[username]=password
            Membership.objects.get_or_create(user=user,business=biz,defaults={'role':role,'permissions':permissions,'all_locations':scope is None,'location_ids':[sites[scope][0].pk] if scope else [],'product_lines':['sponge','adhesive','shared'],'approval_limit':Decimal('1000000')})
        owner=User.objects.get(username='owner')
        Membership.objects.get_or_create(user=owner,business=furniture,defaults={'role':'Owner','permissions':['*'],'all_locations':True,'product_lines':['sponge','adhesive','shared']})
        raw_names=['مواد چسپ','رنگ / پودر','مواد پولیو %45','تی دی آی','پولیو','گاز','میتو کلو راید / پودر','دابکو','کاسموس','سلیکون']
        raws=[]
        for i,name in enumerate(raw_names):
            product,_=Product.objects.get_or_create(business=business,code=f'RAW-{i+1:02}',defaults={'name':name,'kind':'raw','line':'shared','unit':'kg','price':Decimal('200')})
            raws.append(product)
        grades=[]
        for grade in [45,40,35,30,25,21,13]:
            product,_=Product.objects.get_or_create(business=business,code=f'SP-{grade}',defaults={'name':f'اسفنج {grade} کیلو گرام','unit':'cm','line':'sponge','price':Decimal(str(100+grade*5))})
            grades.append(product)
            for code,name in [('TOP','سربلوک'),('BOTTOM','کف بلوک')]:
                Product.objects.get_or_create(business=business,code=f'{code}-{grade}',defaults={'name':f'{name} {grade}','kind':'trim','unit':'each','line':'sponge','price':Decimal('150')})
        adhesive,_=Product.objects.get_or_create(business=business,code='ADH-01',defaults={'name':'چسپ / Adhesive','unit':'kg','line':'adhesive','price':Decimal('180')})
        Party.objects.get_or_create(business=business,name='مشتری نمونه / Demo customer',kind='customer',defaults={'phone':'0700000000','address':'Herat — synthetic demo'})
        Party.objects.get_or_create(business=business,name='فروشنده نمونه / Demo supplier',kind='supplier')
        for name,kind,rate in [('کارمند ماهوار','monthly','20000'),('کارگر روزمزد','daily','600'),('کارمند نیمه وقت','part_time','150'),('کارمند پروژه','project','3000')]:
            Employee.objects.get_or_create(business=business,name=name,defaults={'location':factory,'kind':kind,'rate':Decimal(rate),'advance_limit':Decimal('25000')})
        ctx=Context(owner,business)
        if not Document.objects.filter(business=business,idempotency_key='demo-opening-materials').exists():
            execute(ctx,'stock_opening',{'warehouse':sites['FACTORY'][1].pk,'lines':[{'product':r.pk,'quantity':'1000','value':'150000'} for r in raws]},'demo-opening-materials')
            for code in ['HERAT','KABUL']:
                execute(Context(owner,business),'stock_opening',{'warehouse':sites[code][1].pk,'lines':[{'product':p.pk,'value':'30000','blocks':[{'length_mm':'2000','width_mm':'1000','height_mm':'1000','code':f'{code}-SP{p.code}-001'}]} for p in grades]+[{'product':adhesive.pk,'quantity':'250.750','value':'25075'}]},'demo-opening-'+code.lower())
            for code,(loc,store) in sites.items():
                execute(Context(owner,business),'opening_cash',{'reason':'Synthetic demo opening cash','account':'CASH','amount':'100000','location':loc.pk},'demo-cash-'+code.lower())
        wood,_=Product.objects.get_or_create(business=furniture,code='WOOD',defaults={'name':'چوب / Wood','kind':'raw','line':'shared','unit':'each','price':Decimal('100')})
        chair,_=Product.objects.get_or_create(business=furniture,code='CHAIR',defaults={'name':'چوکی / Chair','kind':'finished','line':'shared','unit':'each','price':Decimal('2000')})
        BOM.objects.get_or_create(business=furniture,product=chair,version=1,defaults={'name':'Demo chair BOM','approved':True,'components':[{'product':wood.pk,'quantity':'4'}],'output_quantity':Decimal('1')})
        path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(credentials,ensure_ascii=False,indent=2),encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('Demo seeded. Generated local credentials: .local/demo-credentials.json (keep private).'))
