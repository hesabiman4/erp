"""Import research schedules as unconfirmed, nonposting revisions; explicit tenant/actor."""
import json
import hashlib
from pathlib import Path
from django.core.management.base import BaseCommand,CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from erp.core import Context
from erp.models import Business
from erp.tax_models import TaxScheduleChange
from erp.taxation import change,validate_content,full_scope


class Command(BaseCommand):
    help='Preview or explicitly import unconfirmed research tax schedules. Never activates document/payroll tax.'

    def add_arguments(self,parser):
        parser.add_argument('--business',required=True,help='Exact existing business slug')
        parser.add_argument('--actor',required=True,help='Assigned user with accounting.tax_manage')
        parser.add_argument('--apply',action='store_true',help='Write unconfirmed research revisions; default is dry run')

    @transaction.atomic
    def handle(self,*args,**options):
        try:
            business=Business.objects.get(slug=options['business'])
            actor=get_user_model().objects.get(username=options['actor'],is_active=True)
        except (Business.DoesNotExist,get_user_model().DoesNotExist):raise CommandError('Select an existing business and active assigned actor.')
        ctx=Context(actor,business);ctx.require('accounting.tax_manage');full_scope(ctx)
        rules=json.loads((Path(__file__).resolve().parents[2]/'data/afghan_tax_research_20261122.json').read_text(encoding='utf-8'))
        created=existing=0
        for rule in rules:
            validate_content(rule)
            payload={'rule':rule,'reason':'ورود نسخهٔ پژوهشی؛ منبع و قابل اجرا بودن آن هنوز باید توسط حسابدار تأیید شود.'}
            key='tax-research-'+hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if options['apply']:
                present=TaxScheduleChange.objects.filter(business=business,request_key=key).exists()
                change(ctx,'create',payload,key)
                existing+=int(present);created+=int(not present)
        self.stdout.write(json.dumps({'dry_run':not options['apply'],'reviewed_rules':len(rules),'created':created,'already_present':existing,
                                      'automatic_posting_enabled':False,'financial_posting':False}))
