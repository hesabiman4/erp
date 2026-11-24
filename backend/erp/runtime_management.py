"""Owner-reviewed release metadata, without an HTTP deployment or shell endpoint."""
from datetime import datetime, timezone as utc
from functools import lru_cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
from django.conf import settings
from django.core.exceptions import PermissionDenied
from .api import Boundary, response
from .models import Product


@lru_cache(maxsize=1)
def release_module():
    path = Path(__file__).resolve().parents[2] / 'scripts/release_check.py'
    spec = importlib.util.spec_from_file_location('erp_release_check', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def authorize(ctx):
    ctx.require('settings.manage'); ctx.require('runtime.manage')
    if not ctx.membership.all_locations: raise PermissionDenied('Complete business scope is required for release/recovery management.')
    if not ctx.has('documents.all_lines') and Product.objects.filter(business=ctx.business).exclude(line__in=ctx.membership.product_lines).exists():
        raise PermissionDenied('Complete business product scope is required for release/recovery management.')


def read_evidence(folder, limit=50):
    folder = Path(folder)
    if not folder.is_dir(): return []
    result = []
    for path in sorted(folder.glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            if not path.resolve().is_relative_to(folder.resolve()) or path.stat().st_size > 1024 * 1024: continue
            value = json.loads(path.read_text(encoding='utf-8'))
            if isinstance(value, dict): result.append(value)
        except (OSError, ValueError): continue
    return result


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None: return None
        return parsed.isoformat()
    except (TypeError, ValueError): return None


def recovery_history(root, tag):
    rows = []
    for item in read_evidence(Path(root) / '.local/recovery-checks'):
        if item.get('source_database_tag') != tag: continue
        steps = item.get('steps', [])
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps): continue
        names = {step.get('name') for step in steps if step.get('passed') is True and step.get('returncode') == 0}
        passed = item.get('verified') is True and {'restore', 'verify-snapshot-and-attachments', 'reconcile-ledgers'}.issubset(names)
        rows.append({'id': str(item.get('source_sha256', ''))[:12], 'started_at': timestamp(item.get('started_at')),
                     'finished_at': timestamp(item.get('finished_at')), 'state': 'verified' if passed else 'failed',
                     'steps_passed': len(names), 'off_device_verified': False,
                     'migrated_copy': item.get('migrations_applied_to_copy') is True,
                     'scope': 'Same-machine restored copy; original database was not overwritten.'})
    return rows


def update_history(root, tag):
    rows = []
    for item in read_evidence(Path(root) / '.local/updates'):
        if item.get('database_tag') != tag: continue
        steps = item.get('steps', [])
        if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps): continue
        names = {step.get('name') for step in steps if step.get('passed') is True and step.get('returncode') == 0}
        verified = item.get('state') == 'verified' and {'encrypted-snapshot', 'apply-migrations', 'django-check', 'core-ledger-check'}.issubset(names)
        rows.append({'id': str(item.get('release_id', ''))[:12], 'started_at': timestamp(item.get('started_at')),
                     'finished_at': timestamp(item.get('finished_at')), 'state': 'verified' if verified else 'failed',
                     'steps_passed': len(names), 'scope': 'Reviewed local forward migration; no automatic rollback.'})
    return rows


def workspace(ctx):
    authorize(ctx)
    checker = release_module(); root = settings.ROOT_DIR
    release = checker.check_release(root)
    config = settings.DATABASES['default']; tag = checker.database_tag(config)
    recoveries = recovery_history(root, tag); updates = update_history(root, tag)
    # Reuse the existing scheduler's exact database tag. A stale worker is not
    # reported as running just because its last invocation once succeeded.
    scheduler_tag = hashlib.sha256(str(config['NAME']).encode()).hexdigest()[:12]
    try:
        state_path = Path(root) / f'.local/runtime-status-{scheduler_tag}.json'
        worker = json.loads(state_path.read_text(encoding='utf-8')) if state_path.stat().st_size <= 1024 * 1024 else {}
    except (OSError, ValueError): worker = {}
    if not isinstance(worker, dict): worker = {}
    checked = timestamp(worker.get('checked_at')); fresh = False
    if checked:
        delta = (datetime.now(utc.utc) - datetime.fromisoformat(checked)).total_seconds(); fresh = 0 <= delta < 180
    from .backup_settings import configuration
    configured = bool(configuration().get('destination'))
    backup = worker.get('backup', {}) if configured else {'state': 'not_configured'}
    if not isinstance(backup, dict): backup = {}
    backup_state = backup.get('state') if backup.get('state') in {'succeeded', 'failed', 'blocked', 'not_configured'} else 'not_verified'
    from .backup_health import summary
    from .installation import running_release
    active_release=running_release()
    return {'running_release':active_release,'running_release_matches':bool(active_release and active_release==release.get('release_id')),'backup_health':summary(configuration()),'release': release, 'database': checker.database_preflight(),
            'worker': {'state': 'running' if fresh else 'not_verified', 'checked_at': checked},
            'backup': {'destination_configured': configured, 'state': backup_state,
                       'last_finished_at': timestamp(backup.get('finished_at')), 'off_device_verified': False},
            'recovery_history': recoveries, 'update_history': updates,
            'recovery_verified_for_this_database': any(row['state'] == 'verified' for row in recoveries),
            'actions_available_over_http': False,
            'notes': ['This page only reads metadata. No installation, migration, backup, restore or shell command can be started here.',
                      'Old recovery reports without a matching source-database fingerprint are not counted as evidence for this database.',
                      'No scheduled destination, startup task, external service or public deployment is configured by opening this page.']}


class RuntimeManagementAPI(Boundary):
    def get(self, request): return response(workspace(self.ctx(request)))
