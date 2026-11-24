"""Verify attachment bytes and business authorization in a restored local DB."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser()
parser.add_argument('--database',required=True)
args=parser.parse_args()
if not re.fullmatch(r'restore_[a-z0-9_]{1,45}',args.database): raise SystemExit('Only a restore_* verification target is allowed.')
storage=ROOT/'.local'/'restores'/args.database
manifest=json.loads((storage/'manifest.json').read_text(encoding='utf-8'))
os.environ['PGDATABASE']=args.database
os.environ['PRIVATE_MEDIA_ROOT']=str(storage/'media')
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
sys.path.insert(0,str(ROOT/'backend'))
import django
django.setup()
from django.contrib.auth.models import User
from django.test import Client
from erp.models import Attachment, Document, StockPool, Entry
from django.db.models import Sum

owner=User.objects.get(username='owner')
outsider=User.objects.get(username='furniture')
client=Client();client.force_login(owner)
other=Client();other.force_login(outsider)
checked=[]
for item in manifest['files']:
    attachment=Attachment.objects.get(file=item['name'])
    r=client.get(f'/api/attachments/{attachment.pk}/',HTTP_X_BUSINESS_ID=str(attachment.business_id))
    assert r.status_code==200,(r.status_code,r.content)
    digest=hashlib.sha256(b''.join(r.streaming_content)).hexdigest()
    assert digest==item['sha256']
    denied=other.get(f'/api/attachments/{attachment.pk}/',HTTP_X_BUSINESS_ID=str(attachment.business_id))
    assert denied.status_code==403
    checked.append({'attachment':attachment.pk,'sha256_verified':True,'owner_http':200,'unassigned_http':403})
sums=Entry.objects.aggregate(dr=Sum('debit'),cr=Sum('credit'))
result={'database':args.database,'documents':Document.objects.count(),'stock_value':str(StockPool.objects.aggregate(v=Sum('value'))['v']),'journal_difference':str((sums['dr'] or 0)-(sums['cr'] or 0)),'attachments':checked,'verified':True}
assert result['documents']==manifest['documents']
assert result['stock_value']==manifest['inventory_value']
assert result['journal_difference']==manifest['journal_difference']
(ROOT/'.local'/'restore-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
