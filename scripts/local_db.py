"""Initialize/start only this workspace's isolated PostgreSQL development cluster."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parent.parent
def binary(name):
    found=shutil.which(name)
    candidate=Path('C:/Program Files/PostgreSQL/18/bin')/(name+'.exe')
    if found: return found
    if candidate.exists(): return str(candidate)
    raise SystemExit('Install PostgreSQL 18 client/server binaries and add them to PATH.')

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['init','start','stop','status'])
    args=parser.parse_args(); local=ROOT/'.local'; data=local/'pgdata'
    config=ROOT/'.env.local'
    local.mkdir(exist_ok=True)
    if args.action=='init':
        if not config.exists():
            pw=secrets.token_urlsafe(32)
            config.write_text('DJANGO_SECRET_KEY='+secrets.token_urlsafe(48)+'\nPGHOST=127.0.0.1\nPGPORT=55432\nPGDATABASE=sponge_erp\nPGUSER=erp_dev\nPGPASSWORD='+pw+'\n',encoding='utf-8')
        env=dotenv_values(config)
        if env.get('PGHOST')!='127.0.0.1' or env.get('PGDATABASE')!='sponge_erp' or env.get('PGPORT')!='55432':
            raise SystemExit('Local init is restricted to 127.0.0.1:55432/sponge_erp.')
        if not (data/'PG_VERSION').exists():
            pwfile=local/'pg-password.txt'; pwfile.write_text(env['PGPASSWORD'],encoding='utf-8')
            try: subprocess.run([binary('initdb'),'-D',str(data),'-U',env['PGUSER'],'--auth-local=trust','--auth-host=scram-sha-256','--pwfile='+str(pwfile),'--encoding=UTF8','--locale=C'],check=True)
            finally: pwfile.unlink(missing_ok=True)
        start(data,local)
        import psycopg
        with psycopg.connect(host='127.0.0.1',port=55432,user=env['PGUSER'],password=env['PGPASSWORD'],dbname='postgres',autocommit=True) as conn:
            if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',('sponge_erp',)).fetchone():
                conn.execute('CREATE DATABASE sponge_erp')
        print('Local development PostgreSQL is ready on 127.0.0.1:55432.')
    elif args.action=='start': start(data,local)
    else: subprocess.run([binary('pg_ctl'),'-D',str(data),args.action],check=True)

def start(data,local):
    if not (data/'PG_VERSION').exists(): raise SystemExit('Run local_db.py init first.')
    check=subprocess.run([binary('pg_ctl'),'-D',str(data),'status'],capture_output=True)
    if check.returncode==0: print('Project PostgreSQL is already running.'); return
    subprocess.run([binary('pg_ctl'),'-D',str(data),'-t','180','-l',str(local/'postgres.log'),'-o','-p 55432 -h 127.0.0.1','start'],check=True)

if __name__=='__main__': main()
