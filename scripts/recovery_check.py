"""One guarded, local-only restore drill with snapshot and ledger verification.

Creates a new restore_* database and private media directory via backup.py.
Never changes the backup schedule/destination or overwrites a database. Failure
preserves the diagnostic copy for inspection; no automatic destructive cleanup.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parent.parent

def checked_target(target):
    if not re.fullmatch(r'restore_[a-z0-9_]{1,45}',target or ''):
        raise ValueError('Use a new local restore_* verification database name.')
    return target

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--database',required=True)
    parser.add_argument('--key-file',type=Path,default=ROOT/'.local'/'backup.key')
    parser.add_argument('--migrate',action='store_true',help='Apply current migrations only to the newly restored verification copy before ledger checks.')
    args=parser.parse_args(argv)
    try:target=checked_target(args.database)
    except ValueError as error:parser.error(str(error))
    source=args.input.resolve();key=args.key_file.resolve()
    if not source.is_file() or not key.is_file():parser.error('An existing encrypted backup and its separate encryption key are required.')
    evidence=ROOT/'.local'/'recovery-checks';evidence.mkdir(parents=True,exist_ok=True)
    report_path=evidence/(target+'.json');log_path=evidence/(target+'.log')
    if report_path.exists() or log_path.exists():parser.error('Evidence for this target already exists. Choose a new restore database name.')
    result={'database':target,'started_at':datetime.now(timezone.utc).isoformat(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scope':'same-machine local recovery drill','off_device_verified':False,'steps':[],'verified':False}
    env=os.environ.copy();env['PGDATABASE']=target;env['PRIVATE_MEDIA_ROOT']=str(ROOT/'.local'/'restores'/target/'media')
    # backup.restore sees the configured active DB and independently refuses live
    # targets/existing DBs/remote hosts. Only subsequent child checks use target.
    commands=[('restore',[sys.executable,str(ROOT/'scripts/backup.py'),'restore','--input',str(source),'--key-file',str(key),'--database',target],os.environ.copy())]
    if args.migrate:commands.append(('migrate-copy',[sys.executable,str(ROOT/'backend/manage.py'),'migrate','--noinput'],env))
    commands.append(('verify-snapshot-and-attachments',[sys.executable,str(ROOT/'scripts/recovery_verify.py'),'--database',target],env))
    commands.append(('reconcile-ledgers',[sys.executable,str(ROOT/'scripts/recovery_verify.py'),'--database',target,'--ledger'],env))
    with log_path.open('x',encoding='utf-8') as log:
        for name,command,command_env in commands:
            started=datetime.now(timezone.utc).isoformat()
            try:
                completed=subprocess.run(command,cwd=ROOT,env=command_env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
                code=completed.returncode
            except subprocess.TimeoutExpired:code=124
            result['steps'].append({'name':name,'started_at':started,'returncode':code,'passed':code==0})
            if name=='restore' and not code:
                restored_manifest=ROOT/'.local'/'restores'/target/'manifest.json'
                try:
                    metadata=json.loads(restored_manifest.read_text(encoding='utf-8'))
                    tag=metadata.get('source_database_tag')
                    if isinstance(tag,str) and re.fullmatch(r'[a-f0-9]{24}',tag):result['source_database_tag']=tag
                except (OSError,ValueError):pass
            if code:
                result['finished_at']=datetime.now(timezone.utc).isoformat();report_path.write_text(json.dumps(result,indent=2),encoding='utf-8')
                print(json.dumps({'verified':False,'failed_step':name,'database':target,'evidence':str(report_path),'note':'Preserved the new verification copy and private operator log; active database was not overwritten.'}))
                return 1
    result['verified']=True;result['finished_at']=datetime.now(timezone.utc).isoformat();result['migrations_applied_to_copy']=args.migrate
    report_path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'verified':True,'database':target,'evidence':str(report_path),'off_device_verified':False}))
    return 0

if __name__=='__main__':raise SystemExit(main())
