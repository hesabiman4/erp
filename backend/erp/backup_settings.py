"""Host-operator backup settings; never a business-owner filesystem capability."""
import hashlib,json,os,subprocess,sys,uuid,io,zipfile
from datetime import datetime,timezone
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import connection
from .api import Boundary,response
from .models import AuditEvent

def tag():return hashlib.sha256(str(settings.DATABASES['default']['NAME']).encode()).hexdigest()[:12]
def config_path():return settings.ROOT_DIR/'.local'/f'backup-settings-{tag()}.json'
def operators_path():return settings.ROOT_DIR/'.local'/'host-operators.json'
def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
def configuration():
    saved=read_json(config_path());return {**saved,'destination':saved.get('destination') or os.environ.get('ERP_BACKUP_DIRECTORY','').strip(),'interval_hours':saved.get('interval_hours',os.environ.get('ERP_BACKUP_INTERVAL_HOURS','24'))}
def authorize(ctx,request):
    ctx.require('settings.manage');ctx.require('runtime.manage')
    allowed=read_json(operators_path()).get('databases',{}).get(tag(),[])
    if ctx.user.pk not in allowed or not ctx.membership.all_locations or not ctx.has('documents.all_lines'):raise PermissionDenied('Backup configuration requires a locally provisioned host operator with complete business scope.')
    if request.META.get('REMOTE_ADDR') not in ('127.0.0.1','::1','testserver'):raise PermissionDenied('Configure host backup folders from the local computer.')
def safe_directory(value):
    if not isinstance(value,str) or not value.strip() or len(value)>1000 or '\x00' in value:raise ValidationError('Choose an existing backup folder.')
    path=Path(value).expanduser().resolve()
    if not path.is_dir():raise ValidationError('The selected backup folder does not exist or is not available.')
    return path
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
def verified_archive(path):
    archive=Fernet((settings.ROOT_DIR/'.local'/'backup.key').read_bytes().strip()).decrypt(path.read_bytes())
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        manifest=json.loads(bundle.read('manifest.json'))
        if not bundle.read('database.dump').startswith(b'PGDMP'):raise ValidationError('The backup does not contain a PostgreSQL archive.')
        for item in manifest['files']:
            if hashlib.sha256(bundle.read('media/'+item['name'])).hexdigest()!=item['sha256']:raise ValidationError('Backup attachment verification failed.')
    return {'archive_verified':True,'attachment_count':len(manifest['files']),'database_restore_verified':False,'off_device_verified':False}

class BackupSettingsAPI(Boundary):
    def get(self,request):
        ctx=self.ctx(request);authorize(ctx,request);config=configuration()
        if request.query_params.get('browse')=='1':
            current=request.query_params.get('path','')
            if not current:
                roots=[str(Path(f'{letter}:/')) for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{letter}:/').is_dir()] if os.name=='nt' else ['/']
                return response({'folders':roots,'parent':None,'path':''})
            path=safe_directory(current)
            try:folders=[str(p) for p in path.iterdir() if p.is_dir() and not p.is_symlink() and not p.name.startswith('.')][:200]
            except (OSError,PermissionError):raise PermissionDenied('This host folder cannot be listed.')
            return response({'folders':sorted(folders),'parent':str(path.parent) if path.parent!=path else '', 'path':str(path),'bounded':len(folders)>=200})
        from .backup_health import summary
        return response({'health':summary(config),'can_configure':True,'destination':config.get('destination',''),'interval_hours':config.get('interval_hours',24),'state':'configured' if config.get('destination') else 'not_configured','last':config.get('last',{}),'off_device_verified':False})
    def post(self,request):
        ctx=self.ctx(request);authorize(ctx,request);action=request.data.get('action');config=configuration()
        if action=='save':
            path=safe_directory(request.data.get('destination'))
            try:interval=int(request.data.get('interval_hours',24))
            except (TypeError,ValueError):raise ValidationError('Use an interval from1 to168 hours.')
            if not 1<=interval<=168:raise ValidationError('Use an interval from1 to168 hours.')
            probe=(path/('.erp-write-check-'+uuid.uuid4().hex)).resolve()
            if probe.parent!=path:raise ValidationError('Unsafe backup probe path.')
            try:
                with probe.open('xb') as stream:stream.write(b'ERP backup destination write check')
                probe.unlink()
            except OSError:raise ValidationError('The application cannot write to this folder.')
            with connection.cursor() as cursor:cursor.execute('SELECT pg_try_advisory_lock(%s)',[817290301]);locked=cursor.fetchone()[0]
            if not locked:raise ValidationError('A backup is running; wait before changing its destination.')
            try:
                config={**config,'destination':str(path),'interval_hours':interval,'revision':config.get('revision') or uuid.uuid4().hex if str(path)==config.get('destination') else uuid.uuid4().hex,'last':config.get('last',{}) if str(path)==config.get('destination') else {},'last_success':config.get('last_success',{}) if str(path)==config.get('destination') else {}}
                write_json(config_path(),config)
            finally:
                with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_unlock(%s)',[817290301])
            AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='backup.configure',target=tag(),details={'interval_hours':interval,'destination_configured':True})
            return response({'configured':True,'write_tested':True,'off_device_verified':False})
        if action!='backup_now':raise ValidationError('Choose a supported backup action.')
        path=safe_directory(config.get('destination',''))
        with connection.cursor() as cursor:cursor.execute('SELECT pg_try_advisory_lock(%s)',[817290301]);locked=cursor.fetchone()[0]
        if not locked:raise ValidationError('Maintenance or another backup is already running. Try again shortly.')
        try:
            target=path/('erp-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.fernet')
            from .backup_health import record_attempt
            try:
                run=subprocess.run([sys.executable,str(settings.ROOT_DIR/'scripts'/'backup.py'),'backup','--output',str(target)],capture_output=True,text=True,timeout=600)
                if run.returncode:raise ValidationError('The backup failed. Review the private host log; no successful backup was reported.')
                result={'state':'succeeded','finished_at':datetime.now(timezone.utc).isoformat(),**verified_archive(target)}
            except Exception as error:
                record_attempt(config,{'state':'failed','archive_verified':False},'manual')
                raise ValidationError('The backup failed. Review the private host log; no successful backup was reported.') from error
            record_attempt(config,result,'manual')
            AuditEvent.objects.create(business=ctx.business,user=ctx.user,action='backup.created',target=tag(),details=result)
            return response(result)
        finally:
            with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_unlock(%s)',[817290301])
