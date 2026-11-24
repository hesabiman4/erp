"""Read-only restore snapshot verification without assuming demo usernames."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from decimal import Decimal

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);parser.add_argument('--ledger',action='store_true');args=parser.parse_args()
if not re.fullmatch(r'restore_[a-z0-9_]{1,45}',args.database):raise SystemExit('Only restore_* verification copies are allowed.')
os.environ['PGDATABASE']=args.database;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');sys.path.insert(0,str(ROOT/'backend'))
import django
django.setup()
from django.conf import settings
from django.db import connection
from erp.models import Attachment

if settings.DATABASES['default']['HOST'] not in ('127.0.0.1','localhost') or settings.DATABASES['default']['NAME']!=args.database:raise SystemExit('Read-only verification is restricted to the named local restore copy.')
storage=(ROOT/'.local'/'restores'/args.database).resolve();manifest=json.loads((storage/'manifest.json').read_text(encoding='utf-8'));checked=0
with connection.cursor() as cursor:
    cursor.execute('SET default_transaction_read_only=on')
    cursor.execute('SELECT count(*) FROM erp_document');documents=cursor.fetchone()[0]
    cursor.execute('SELECT COALESCE(sum(value),0) FROM erp_stockpool');inventory=cursor.fetchone()[0]
    cursor.execute('SELECT COALESCE(sum(debit-credit),0) FROM erp_entry');difference=cursor.fetchone()[0]
    for item in manifest['files']:
        target=(storage/'media'/item['name']).resolve()
        if not target.is_relative_to(storage/'media') or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=item['sha256']:raise SystemExit('Missing, unsafe or checksum-mismatched restored attachment.')
        if not Attachment.objects.filter(file=item['name']).exists():raise SystemExit('Restored attachment has no database record.')
        checked+=1
    if args.ledger:
        cursor.execute("SELECT d.id FROM erp_document d LEFT JOIN erp_entry e ON e.document_id=d.id WHERE d.state='posted' GROUP BY d.id HAVING COALESCE(sum(e.debit-e.credit),0)<>0 LIMIT 1")
        if cursor.fetchone():raise SystemExit('A restored posted document has an unbalanced journal.')
        cursor.execute("SELECT b.id,COALESCE((SELECT sum(e.debit-e.credit) FROM erp_entry e JOIN erp_account a ON a.id=e.account_id JOIN erp_document d ON d.id=e.document_id WHERE d.business_id=b.id AND d.state='posted' AND a.code IN ('RAW','FG','TRIM','TRANSIT')),0),COALESCE((SELECT sum(s.value) FROM erp_stockpool s WHERE s.business_id=b.id),0) FROM erp_business b")
        businesses=cursor.fetchall()
        for business,ledger,stock in businesses:
            if ledger.quantize(Decimal('.01'))!=stock.quantize(Decimal('.01')):raise SystemExit('Restored inventory control does not reconcile to stock pools.')
        cursor.execute('SELECT id FROM erp_stockpool WHERE quantity<0 OR value<0 LIMIT 1')
        if cursor.fetchone():raise SystemExit('Restored stock pool has a negative quantity or carrying value.')
        cursor.execute('SELECT id FROM erp_block WHERE remaining_height_mm<0 OR reserved_height_mm<0 OR reserved_height_mm>remaining_height_mm LIMIT 1')
        if cursor.fetchone():raise SystemExit('Restored physical block height/reservation is inconsistent.')
if documents!=manifest['documents'] or inventory!=Decimal(manifest['inventory_value']) or difference!=Decimal(manifest['journal_difference']):raise SystemExit('Restored snapshot totals differ from the captured manifest.')
print(json.dumps({'verified':True,'database':args.database,'documents':documents,'inventory_value':str(inventory),'journal_difference':str(difference),'attachment_checksums_verified':checked,'read_only':True,'ledger_controls_checked':args.ledger,'scope':'Snapshot totals, posted journal balance, inventory control/pool agreement and nonnegative physical reservations; not a full statutory or foreign-subledger review.'}))
