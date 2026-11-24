"""Backup freshness and private attempt history. No financial data or host paths
are returned to the business UI. Caller enforces operator/runtime authority.
"""
from datetime import datetime,timedelta,timezone
import json,uuid
from pathlib import Path
from django.conf import settings

def parsed(value):
    try:
        result=datetime.fromisoformat(str(value))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError,ValueError):return None

def history_dir():
    from .backup_settings import tag
    return settings.ROOT_DIR/'.local'/('backup-history-'+tag())

def record_attempt(config,result,source):
    from .backup_settings import write_json,config_path
    entry={**result,'id':uuid.uuid4().hex,'source':source,'revision':config.get('revision'),'finished_at':result.get('finished_at') or datetime.now(timezone.utc).isoformat()}
    write_json(history_dir()/(entry['id']+'.json'),entry)
    # Preserve failure as the latest attempt while retaining the last success.
    saved={**config,'last':entry}
    if entry.get('state')=='succeeded':saved['last_success']=entry
    write_json(config_path(),saved)
    return entry

def summary(config,now=None):
    now=now or datetime.now(timezone.utc);rows=[]
    folder=history_dir()
    if folder.is_dir():
        for file in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:50]:
            try:
                if file.stat().st_size>32768 or not file.resolve().is_relative_to(folder.resolve()):continue
                item=json.loads(file.read_text(encoding='utf8'))
                if isinstance(item,dict):rows.append(item)
            except (OSError,ValueError):continue
    # Do not count a successful copy at a previous destination as protection at
    # the newly configured destination. Legacy records remain visible honestly.
    applicable=[r for r in rows if r.get('revision')==config.get('revision')]
    attempts=applicable+[r for r in [config.get('last',{})] if isinstance(r,dict) and r.get('state')]
    attempts.sort(key=lambda r:parsed(r.get('finished_at')) or datetime.min.replace(tzinfo=timezone.utc),reverse=True)
    successes=[r for r in attempts+[config.get('last_success',{})] if isinstance(r,dict) and r.get('state')=='succeeded' and r.get('revision')==config.get('revision') and parsed(r.get('finished_at'))]
    success=max(successes,key=lambda r:parsed(r['finished_at']),default=None)
    # Older manual/scheduler receipts did not store revision: display the last
    # receipt, but never fabricate a verified history for a new destination.
    if not success and config.get('last',{}).get('state')=='succeeded' and not rows:success=config['last']
    interval=config.get('interval_hours') or 24
    try:interval=int(interval)
    except (TypeError,ValueError):interval=24
    if not 1<=interval<=168:interval=24
    last=attempts[0] if attempts else {};last_at=parsed(success.get('finished_at')) if success else None
    due=last_at+timedelta(hours=interval) if last_at else None
    state='not_configured' if not config.get('destination') else 'failed' if last.get('state') in ('failed','blocked') else 'never_completed' if not last_at else 'overdue' if last_at>now+timedelta(minutes=5) or now>=due else 'current'
    def public(item):return {k:item.get(k) for k in ('id','source','state','finished_at','archive_verified','attachment_count','database_restore_verified','off_device_verified')}
    return {'state':state,'last_success_at':last_at.isoformat() if last_at else None,'next_due_at':due.isoformat() if due else None,'interval_hours':interval,'history':[public(r) for r in rows],'off_device_verified':False,'database_restore_verified':False}
