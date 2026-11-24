"""Reproduce migrations + synthetic onboarding in a NEW local verification DB."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import psycopg
from psycopg import sql
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser();parser.add_argument('--database',required=True);args=parser.parse_args()
if not re.fullmatch(r'verify_[a-z0-9_]{1,45}',args.database): raise SystemExit('Use a new verify_* database name.')
config=dotenv_values(ROOT/'.env.local')
if config.get('PGHOST')!='127.0.0.1': raise SystemExit('Only local verification is supported.')
with psycopg.connect(host=config['PGHOST'],port=config['PGPORT'],user=config['PGUSER'],password=config['PGPASSWORD'],dbname='postgres',autocommit=True) as conn:
    if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(args.database,)).fetchone(): raise SystemExit('Existing verification database will not be overwritten.')
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(args.database)))
env=os.environ.copy();env['PGDATABASE']=args.database;env['PYTHONPATH']=str(ROOT/'backend')
env['ERP_DEMO_CREDENTIALS_PATH']=str(ROOT/'.local'/f'{args.database}-credentials.json')
for command in [['backend/manage.py','migrate','--noinput'],['backend/manage.py','seed_demo','--demo'],['backend/manage.py','seed_demo','--demo']]:
    subprocess.run([sys.executable,*command],cwd=ROOT,env=env,check=True)
with psycopg.connect(host=config['PGHOST'],port=config['PGPORT'],user=config['PGUSER'],password=config['PGPASSWORD'],dbname=args.database) as conn:
    rows=conn.execute('SELECT (SELECT count(*) FROM erp_business),(SELECT count(*) FROM erp_document),(SELECT COALESCE(sum(value),0) FROM erp_stockpool),(SELECT COALESCE(sum(debit-credit),0) FROM erp_entry)').fetchone()
assert rows[0]==2 and rows[1]==6 and rows[3]==0,rows
result={'database':args.database,'businesses':rows[0],'documents_after_double_seed':rows[1],'inventory_value':str(rows[2]),'journal_difference':str(rows[3]),'fresh_install_verified':True,'repeatable_seed_verified':True}
(ROOT/'.local'/'fresh-install-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
