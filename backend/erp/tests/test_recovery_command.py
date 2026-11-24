"""Safety boundary for the operator wrapper without executing a restore."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('recovery_check',ROOT/'scripts/recovery_check.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)

@pytest.mark.parametrize('name',['sponge_erp','postgres','restore_../active','restore_','restore_Test','restore_a;drop_database','restore_'+'a'*46])
def test_recovery_wrapper_rejects_nonisolated_targets(name):
    with pytest.raises(ValueError):recovery.checked_target(name)

def test_recovery_wrapper_accepts_only_explicit_new_restore_prefix():
    assert recovery.checked_target('restore_operator_drill_20261102')=='restore_operator_drill_20261102'

def test_recovery_command_refuses_live_name_before_any_child_process(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No restore process may start for a live database target.')
    monkeypatch.setattr(recovery.subprocess,'run',forbidden)
    with pytest.raises(SystemExit) as failure:
        recovery.main(['--input','nonexistent-backup.fernet','--database','sponge_erp'])
    assert failure.value.code==2
