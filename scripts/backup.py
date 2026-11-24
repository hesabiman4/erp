"""Encrypted consistent PostgreSQL + immutable private attachment snapshot.

Restore always creates a new explicitly named local database and separate media
directory. It refuses to overwrite an existing or configured live database.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from cryptography.fernet import Fernet
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.conf import settings
from release_check import database_tag

def pgtool(name):
    found=shutil.which(name)
    if found: return found
    candidate=Path('C:/Program Files/PostgreSQL/18/bin')/(name+'.exe')
    if candidate.exists(): return str(candidate)
    raise SystemExit('PostgreSQL client utility unavailable: '+name)

def connection(dbname=None):
    conf=settings.DATABASES['default']
    return dict(host=conf['HOST'],port=conf['PORT'],user=conf['USER'],password=conf['PASSWORD'],dbname=dbname or conf['NAME'])

def pg_environment():
    env=os.environ.copy(); conf=connection()
    for key,source in [('PGHOST','host'),('PGPORT','port'),('PGUSER','user'),('PGPASSWORD','password')]: env[key]=str(conf[source])
    return env

def backup(output,keyfile):
    if not keyfile.exists(): keyfile.parent.mkdir(parents=True,exist_ok=True); keyfile.write_bytes(Fernet.generate_key())
    encryptor=Fernet(keyfile.read_bytes().strip())
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists(): raise SystemExit('Backup output already exists; choose a new filename.')
    archive=io.BytesIO()
    with tempfile.TemporaryDirectory(prefix='erp-backup-') as temp:
        dump=Path(temp)/'database.dump'
        with psycopg.connect(**connection(),autocommit=True) as conn:
            conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            try:
                snapshot=conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
                files=conn.execute('SELECT file FROM erp_attachment ORDER BY id').fetchall()
                counts=conn.execute("SELECT (SELECT count(*) FROM erp_document),(SELECT COALESCE(sum(value),0) FROM erp_stockpool),(SELECT COALESCE(sum(debit-credit),0) FROM erp_entry)").fetchone()
                subprocess.run([pgtool('pg_dump'),'--format=custom','--no-owner','--snapshot='+snapshot,'--file='+str(dump),settings.DATABASES['default']['NAME']],check=True,env=pg_environment())
                manifest={'created_at':datetime.now(timezone.utc).isoformat(),'database':settings.DATABASES['default']['NAME'],'source_database_tag':database_tag(settings.DATABASES['default']),'documents':counts[0],'inventory_value':str(counts[1]),'journal_difference':str(counts[2]),'files':[],'configuration_references':['.env.local or securely provided deployment configuration','Django secret key','backup encryption key stored separately']}
                with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
                    bundle.write(dump,'database.dump')
                    for (name,) in files:
                        source=(Path(settings.MEDIA_ROOT)/name).resolve()
                        if not source.is_relative_to(Path(settings.MEDIA_ROOT).resolve()) or not source.is_file(): raise RuntimeError('Missing or unsafe attachment: '+name)
                        content=source.read_bytes(); manifest['files'].append({'name':name,'sha256':hashlib.sha256(content).hexdigest()})
                        bundle.writestr('media/'+name,content)
                    bundle.writestr('manifest.json',json.dumps(manifest,indent=2))
            finally: conn.execute('ROLLBACK')
    output.write_bytes(encryptor.encrypt(archive.getvalue()))
    print(json.dumps({'backup':str(output),'key_file':str(keyfile),'documents':manifest['documents'],'attachments':len(manifest['files']),'inventory_value':manifest['inventory_value']}))

def restore(source,keyfile,target):
    if not re.fullmatch(r'restore_[a-z0-9_]{1,45}',target) or target==settings.DATABASES['default']['NAME']:
        raise SystemExit('Restore database must be a NEW name starting restore_; live targets are forbidden.')
    conf=connection('postgres')
    if conf['host'] not in ('127.0.0.1','localhost'): raise SystemExit('This restore tool only creates local verification databases.')
    archive=Fernet(keyfile.read_bytes().strip()).decrypt(source.read_bytes())
    storage=(ROOT/'.local'/'restores'/target).resolve()
    if storage.exists(): raise SystemExit('Restore storage already exists; choose a new database name.')
    if not storage.is_relative_to((ROOT/'.local'/'restores').resolve()): raise SystemExit('Unsafe restore storage path.')
    with psycopg.connect(**conf,autocommit=True) as conn:
        if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(target,)).fetchone(): raise SystemExit('Database exists; overwriting is forbidden.')
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
    storage.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        for item in bundle.infolist():
            destination=(storage/item.filename).resolve()
            if not destination.is_relative_to(storage): raise SystemExit('Unsafe backup entry path.')
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(bundle.read(item))
    manifest=json.loads((storage/'manifest.json').read_text())
    for item in manifest['files']:
        path=storage/'media'/item['name']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']: raise SystemExit('Attachment checksum mismatch.')
    subprocess.run([pgtool('pg_restore'),'--exit-on-error','--no-owner','--no-privileges','--dbname='+target,str(storage/'database.dump')],check=True,env=pg_environment())
    with psycopg.connect(**connection(target)) as conn:
        restored=conn.execute("SELECT (SELECT count(*) FROM erp_document),(SELECT COALESCE(sum(value),0) FROM erp_stockpool),(SELECT COALESCE(sum(debit-credit),0) FROM erp_entry)").fetchone()
    if restored[0]!=manifest['documents'] or str(restored[1])!=manifest['inventory_value'] or str(restored[2])!=manifest['journal_difference']:
        raise SystemExit('Restore reconciliation differs from the captured snapshot.')
    print(json.dumps({'restored_database':target,'media_root':str(storage/'media'),'documents':restored[0],'inventory_value':str(restored[1]),'journal_difference':str(restored[2]),'attachments':len(manifest['files']),'verified':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['backup','restore']); parser.add_argument('--output',type=Path); parser.add_argument('--input',type=Path); parser.add_argument('--key-file',type=Path,default=ROOT/'.local'/'backup.key'); parser.add_argument('--database')
    args=parser.parse_args()
    if args.action=='backup': backup(args.output or ROOT/'.local'/'backups'/('erp-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.fernet'),args.key_file)
    else:
        if not args.input or not args.database: parser.error('restore requires --input and --database')
        restore(args.input,args.key_file,args.database)
