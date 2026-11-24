"""Freshness, operator isolation and safe launcher checks; database cases use PostgreSQL."""
import json,sys,threading
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from types import SimpleNamespace
import pytest
from django.test import override_settings
from erp.tests.test_api import environment,client_for
from erp.core import Context
from erp.models import Document,Entry,StockMovement
from erp.backup_health import summary,record_attempt
from erp.backup_settings import configuration,config_path,write_json,tag
from erp.daily_v6 import attention
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import open_erp


def test_backup_health_distinguishes_no_config_never_due_failure_and_revision(tmp_path):
    now=datetime(2026,11,21,10,tzinfo=timezone.utc)
    with override_settings(ROOT_DIR=tmp_path):
        assert summary({},now)['state']=='not_configured'
        config={'destination':str(tmp_path),'interval_hours':24,'revision':'one'}
        assert summary(config,now)['state']=='never_completed'
        success=record_attempt(config,{'state':'succeeded','archive_verified':True,'finished_at':(now-timedelta(hours=23)).isoformat()},'manual');config=configuration()
        assert summary(config,now)['state']=='current'
        assert summary(config,now+timedelta(hours=2))['state']=='overdue'
        record_attempt(config,{'state':'failed','finished_at':now.isoformat()},'scheduled');failed=summary(configuration(),now)
        assert failed['state']=='failed' and failed['last_success_at']==success['finished_at']
        assert [r['state'] for r in failed['history']]==['failed','succeeded']
        changed={**configuration(),'destination':'another-private-folder','revision':'two','last':{},'last_success':{}}
        assert summary(changed,now)['state']=='never_completed'
        assert 'another-private-folder' not in json.dumps(summary(changed,now))


def test_health_exposes_no_paths_or_secrets_and_opaque_identity(environment,monkeypatch):
    user,business,*_=environment;monkeypatch.setenv('ERP_RUNNING_RELEASE','a'*64)
    c=client_for(user,business);r=c.get('/api/health/');assert r.status_code==200
    data=r.json();assert data['status']=='ok' and len(data['installation_id'])==24 and data['running_release']=='a'*64
    assert r['Cache-Control']=='no-store' and str(ROOT) not in str(data)


def test_backup_warning_is_for_authorized_owner_and_cannot_leak_paths(environment,tmp_path):
    user,business,member,*_=environment
    with override_settings(ROOT_DIR=tmp_path):
        write_json(config_path(),{'destination':'PRIVATE_NETWORK_LOCATION','revision':'one'})
        owner=attention(Context(user,business));group=next(g for g in owner['groups'] if g['key']=='system')
        assert group['results'][0]['href']=='/settings?section=security'
        assert 'PRIVATE_NETWORK_LOCATION' not in str(owner)
        member.permissions=['sales.view'];member.save(update_fields=['permissions'])
        assert not any(g['key']=='system' for g in attention(Context(user,business))['groups'])


def test_backup_settings_history_requires_local_host_operator_and_has_no_ledger_effect(environment,tmp_path):
    user,biz,member,*_=environment;c=client_for(user,biz)
    with override_settings(ROOT_DIR=tmp_path):
        folder=tmp_path/'.local';folder.mkdir()
        (folder/'host-operators.json').write_text(json.dumps({'databases':{tag():[user.pk]}}))
        counts=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
        res=c.get('/api/backup-settings/');assert res.status_code==200 and res.json()['health']['state']=='not_configured'
        assert c.get('/api/backup-settings/',REMOTE_ADDR='192.168.1.20').status_code==403
        member.permissions=['settings.manage'];member.save()
        assert c.get('/api/backup-settings/').status_code==403
        assert counts==(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())


def test_launcher_checks_actual_http_identity_and_preserves_other_installation(tmp_path):
    data={'status':'ok','database':'postgresql','installation_id':open_erp.instance_id(tmp_path),'running_release':'b'*64}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(json.dumps(data).encode())
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        assert open_erp.inspect(server.server_port,tmp_path)['state']=='ready'
        assert open_erp.inspect(server.server_port,ROOT)['state']=='different_installation'
        data['installation_id']='wrong';assert open_erp.inspect(server.server_port,tmp_path)['state']=='different_installation'
    finally:server.shutdown();server.server_close();thread.join()


def test_launcher_never_stops_or_opens_unknown_occupied_port(monkeypatch):
    import release_check
    monkeypatch.setattr(release_check,'check_release',lambda root:{'state':'verified','dependencies_matched':True,'release_id':'a'*64})
    monkeypatch.setattr(open_erp,'inspect',lambda port:{'state':'different_installation'})
    monkeypatch.setattr(open_erp,'occupied',lambda port:True)
    monkeypatch.setattr(open_erp.subprocess,'Popen',lambda *a,**k:pytest.fail('Must not launch over occupied port'))
    monkeypatch.setattr(open_erp.webbrowser,'open',lambda *a,**k:pytest.fail('Must not open another installation'))
    with pytest.raises(SystemExit,match='occupied'):open_erp.main(['--no-browser'])
