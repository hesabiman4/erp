"""Operator boundaries and database-bound evidence, without applying an update."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate
from erp.tests.test_api import environment,client_for
from erp.core import Context
from erp.models import Business,Location,Product,Document,Entry,StockMovement
from erp.runtime_management import workspace,recovery_history,update_history,RuntimeManagementAPI

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import release_check
import build_release
import update_release


def fake_root(tmp_path):
    (tmp_path/'frontend/dist').mkdir(parents=True)
    (tmp_path/'backend').mkdir()
    (tmp_path/'scripts').mkdir()
    (tmp_path/'requirements.txt').write_text('Django==5.2.18\n',encoding='utf-8')
    (tmp_path/'frontend/package.json').write_text('{"version":"1.2.3"}',encoding='utf-8')
    (tmp_path/'backend/app.py').write_text('release = 1\n',encoding='utf-8')
    (tmp_path/'frontend/dist/index.html').write_text('<h1>Verified built application</h1>',encoding='utf-8')
    return tmp_path


def seal(root):
    return build_release.build(root,run=lambda *args,**kwargs:SimpleNamespace(returncode=0))


def test_release_seal_detects_changed_source_and_changed_asset(tmp_path):
    root=fake_root(tmp_path);sealed=seal(root)
    assert sealed['sealed'] and release_check.check_release(root)['state']=='verified'
    (root/'backend/app.py').write_text('release = 2\n',encoding='utf-8')
    assert release_check.check_release(root)['state']=='changed'
    seal(root)
    (root/'frontend/dist/index.html').write_text('<p>Changed output after sealing</p>',encoding='utf-8')
    assert release_check.check_release(root)['assets_aligned'] is False


def test_failed_or_concurrently_changed_build_never_seals(tmp_path):
    root=fake_root(tmp_path)
    with pytest.raises(ValueError):build_release.build(root,run=lambda *a,**k:SimpleNamespace(returncode=1))
    assert not release_check.manifest_path(root).exists()
    def concurrent(*args,**kwargs):
        (root/'backend/app.py').write_text('release = 2\n',encoding='utf-8');return SimpleNamespace(returncode=0)
    with pytest.raises(ValueError):build_release.build(root,run=concurrent)
    assert not release_check.manifest_path(root).exists()


def test_manifest_tampering_or_escaping_paths_is_not_trusted(tmp_path):
    root=fake_root(tmp_path);seal(root);path=release_check.manifest_path(root)
    value=json.loads(path.read_text());value['release_id']='f'*64;path.write_text(json.dumps(value))
    assert release_check.check_release(root)['state']=='invalid'
    seal(root);value=json.loads(path.read_text());value['assets']['../secret']='a'*64
    value['release_id']=release_check.canonical_hash({key:value[key] for key in ['sources','assets','version']});path.write_text(json.dumps(value))
    assert release_check.check_release(root)['state']=='invalid'


@pytest.mark.parametrize('config,target,confirmation',[
    ({'HOST':'remote.example','PORT':'55432','NAME':'sponge_erp'},'sponge_erp','sponge_erp'),
    ({'HOST':'127.0.0.1','PORT':'5432','NAME':'sponge_erp'},'sponge_erp','sponge_erp'),
    ({'HOST':'127.0.0.1','PORT':'55432','NAME':'sponge_erp'},'postgres','postgres'),
    ({'HOST':'127.0.0.1','PORT':'55432','NAME':'sponge_erp'},'another_db','another_db'),
    ({'HOST':'127.0.0.1','PORT':'55432','NAME':'sponge_erp'},'sponge_erp','wrong'),
    ({'HOST':'127.0.0.1','PORT':'55432','NAME':'sponge_erp'},'sponge_erp;delete','sponge_erp;delete'),
])
def test_update_rejects_remote_system_mismatched_or_unconfirmed_target(config,target,confirmation):
    with pytest.raises(ValueError):update_release.checked_target(config,target,confirmation,True)


def test_local_apply_target_needs_exact_repeated_name_and_cannot_run_with_live_port(tmp_path,monkeypatch):
    conf={'HOST':'127.0.0.1','PORT':'55432','NAME':'sponge_erp'}
    assert update_release.checked_target(conf,'sponge_erp','sponge_erp',True)=='sponge_erp'
    monkeypatch.setattr(update_release,'listening',lambda port:True)
    def forbidden(*args,**kwargs):pytest.fail('A live application must never start an update child process.')
    with pytest.raises(ValueError):update_release.apply_update(conf,{'state':'verified','dependencies_matched':True,'release_id':'a'*64},root=tmp_path,run=forbidden)


def test_snapshot_failure_or_missing_artifact_prevents_any_migration(tmp_path,monkeypatch):
    monkeypatch.setattr(update_release,'listening',lambda port:False);calls=[]
    def fake_run(command,**kwargs):calls.append(command);return SimpleNamespace(returncode=0)
    result=update_release.apply_update({'HOST':'127.0.0.1','PORT':'55432','NAME':'sponge_erp'},
        {'state':'verified','dependencies_matched':True,'release_id':'a'*64},root=tmp_path,run=fake_run)
    assert result['state']=='failed' and result['failed_step']=='encrypted-snapshot'
    assert len(calls)==1 and 'backup.py' in str(calls[0][1])
    assert list((tmp_path/'.local/updates').glob('*.json'))


def test_migration_failure_preserves_snapshot_and_never_calls_live_restore(tmp_path,monkeypatch):
    monkeypatch.setattr(update_release,'listening',lambda port:False);calls=[]
    def fake_run(command,**kwargs):
        calls.append(command)
        if 'backup.py' in str(command[1]):
            path=Path(command[command.index('--output')+1]);path.parent.mkdir(parents=True);path.write_bytes(b'synthetic encrypted snapshot')
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1)
    result=update_release.apply_update({'HOST':'127.0.0.1','PORT':'55432','NAME':'sponge_erp'},
        {'state':'verified','dependencies_matched':True,'release_id':'a'*64},root=tmp_path,run=fake_run)
    assert result['state']=='failed' and result['failed_step']=='apply-migrations' and result['snapshot_retained']
    assert len(calls)==2 and not any('restore' in command for command in calls)


def test_recovery_and_update_history_require_current_database_provenance_and_real_steps(tmp_path):
    tag='a'*24;folder=tmp_path/'.local/recovery-checks';folder.mkdir(parents=True)
    steps=[{'name':name,'passed':True,'returncode':0} for name in ['restore','verify-snapshot-and-attachments','reconcile-ledgers']]
    record={'source_database_tag':tag,'verified':True,'steps':steps,'source_sha256':'b'*64,'finished_at':'2026-11-02T08:00:00+00:00'}
    (folder/'matching.json').write_text(json.dumps(record));(folder/'other.json').write_text(json.dumps({**record,'source_database_tag':'c'*24}))
    old={key:value for key,value in record.items() if key!='source_database_tag'};(folder/'legacy.json').write_text(json.dumps(old))
    (folder/'incomplete.json').write_text(json.dumps({**record,'steps':steps[:1]}))
    rows=recovery_history(tmp_path,tag)
    assert len(rows)==2 and sum(row['state']=='verified' for row in rows)==1
    assert all(row['off_device_verified'] is False for row in rows)
    assert not any('database' in row or 'source_database_tag' in row for row in rows)
    update=tmp_path/'.local/updates';update.mkdir();(update/'fake.json').write_text(json.dumps({'database_tag':tag,'state':'verified','steps':[]}))
    assert update_history(tmp_path,tag)[0]['state']=='failed'


def test_runtime_api_requires_explicit_permission_complete_scope_and_never_exposes_paths(environment,tmp_path,monkeypatch):
    user,business,member,loc,*_=environment;ctx=Context(user,business)
    from erp import runtime_management as module
    checker=SimpleNamespace(check_release=lambda root:{'state':'not_sealed','dependencies':[]},
        database_tag=release_check.database_tag,database_preflight=release_check.database_preflight)
    monkeypatch.setattr(module,'release_module',lambda:checker)
    with override_settings(ROOT_DIR=tmp_path):
        counts=(Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())
        data=workspace(ctx)
        assert data['database']['state']=='connected' and data['database']['schema_current']
        assert data['actions_available_over_http'] is False and not data['backup']['destination_configured']
        assert (Document.objects.count(),Entry.objects.count(),StockMovement.objects.count())==counts
        serialized=json.dumps(data);assert str(tmp_path) not in serialized and 'PASSWORD' not in serialized and '127.0.0.1' not in serialized
        member.permissions=['settings.manage'];member.save()
        with pytest.raises(PermissionDenied):workspace(Context(user,business))
        member.permissions=['settings.manage','runtime.manage'];member.all_locations=False;member.location_ids=[loc.id];member.save()
        with pytest.raises(PermissionDenied):workspace(Context(user,business))


def test_runtime_http_endpoint_is_read_only_and_database_ledger_check_is_user_independent(environment,monkeypatch,tmp_path):
    user,business,*_=environment
    from erp import runtime_management as module
    checker=SimpleNamespace(check_release=lambda root:{'state':'not_sealed','dependencies':[]},database_tag=release_check.database_tag,database_preflight=release_check.database_preflight)
    monkeypatch.setattr(module,'release_module',lambda:checker)
    factory=APIRequestFactory()
    with override_settings(ROOT_DIR=tmp_path):
        request=factory.get('/api/runtime-management/',HTTP_X_BUSINESS_ID=str(business.pk));force_authenticate(request,user)
        result=RuntimeManagementAPI.as_view()(request);assert result.status_code==200
        request=factory.post('/api/runtime-management/',{},format='json',HTTP_X_BUSINESS_ID=str(business.pk));force_authenticate(request,user)
        assert RuntimeManagementAPI.as_view()(request).status_code==405
    assert release_check.ledger_preflight()['state']=='verified'
