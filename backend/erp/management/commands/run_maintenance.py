"""One idempotent scheduler tick; a host operator configures backup destinations."""
import json,os,subprocess,sys,hashlib
from datetime import datetime,timedelta,timezone
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from django.db import connection

class Command(BaseCommand):
    def handle(self,*args,**options):
        root=settings.ROOT_DIR;database_tag=hashlib.sha256(str(settings.DATABASES['default']['NAME']).encode()).hexdigest()[:12];state_path=root/f'.local/runtime-status-{database_tag}.json';state_path.parent.mkdir(exist_ok=True)
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)',[817290301]);locked=cursor.fetchone()[0]
        if not locked:self.stdout.write('Another maintenance tick is running.');return
        try:
            previous=json.loads(state_path.read_text()) if state_path.exists() else {}
            now=datetime.now(timezone.utc);result={'checked_at':now.isoformat(),'database':'postgresql','backup':previous.get('backup',{}),'reconciliation':previous.get('reconciliation',{})}
            from erp.messaging import send_queued
            result['messages']=send_queued()
            from erp.customer_notices import send_notices
            result['customer_notices']=send_notices()
            def due(item,hours):
                if item.get('state') not in {'succeeded','not_configured'}:hours=min(hours,.25)
                try:return datetime.fromisoformat(item.get('finished_at',''))<now-timedelta(hours=hours)
                except (TypeError,ValueError):return True
            from erp.backup_settings import configuration,verified_archive
            from erp.backup_health import record_attempt
            backup_config=configuration()
            destination=backup_config.get('destination','')
            if previous.get('backup_configuration_revision')!=backup_config.get('revision'):result['backup']={}
            manual=backup_config.get('last',{})
            if isinstance(manual,dict) and manual.get('finished_at','')>result['backup'].get('finished_at',''):result['backup']=manual
            result['backup_configuration_revision']=backup_config.get('revision')
            if not destination:result['backup']={'state':'not_configured','reason':'Configure the encrypted backup destination before enabling scheduled backups.'}
            elif due(result['backup'],int(backup_config.get('interval_hours') or os.environ.get('ERP_BACKUP_INTERVAL_HOURS','24'))):
                path=Path(destination).expanduser().resolve()
                if not path.is_dir():result['backup']={'state':'blocked','reason':'Configured backup directory does not exist.'}
                else:
                    target=path/('erp-'+now.strftime('%Y%m%d-%H%M%S')+'.fernet')
                    try:
                        run=subprocess.run([sys.executable,str(root/'scripts/backup.py'),'backup','--output',str(target)],capture_output=True,text=True,timeout=600)
                        if run.returncode:raise ValueError('Backup process failed.')
                        result['backup']={'state':'succeeded','finished_at':datetime.now(timezone.utc).isoformat(),**verified_archive(target)}
                    except Exception:
                        result['backup']={'state':'failed','finished_at':datetime.now(timezone.utc).isoformat(),'reason':'Backup verification failed; inspect the private operator log.','off_device_verified':False}
                        with (root/'.local/maintenance-errors.log').open('a',encoding='utf8') as log:log.write(now.isoformat()+' backup failed\n')
                record_attempt(backup_config,result['backup'],'scheduled')
            if due(result['reconciliation'],24):
                env={**os.environ,'ERP_RECONCILE_OUTPUT':str(root/f'.local/reconciliation-{database_tag}.json')}
                run=subprocess.run([sys.executable,str(root/'scripts/reconcile.py')],env=env,capture_output=True,text=True,timeout=600)
                result['reconciliation']={'state':'succeeded' if run.returncode==0 else 'failed','finished_at':datetime.now(timezone.utc).isoformat(),'reason':'' if run.returncode==0 else 'Ledger reconciliation failed; operator review required.'}
            temp=state_path.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2),encoding='utf-8');temp.replace(state_path)
            self.stdout.write(json.dumps(result))
        finally:
            with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_unlock(%s)',[817290301])
