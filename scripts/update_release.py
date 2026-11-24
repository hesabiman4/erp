"""Review or apply a sealed release to one explicitly named local database.

Dry run is the default. Apply takes an encrypted snapshot before migrations,
requires the runtime to be stopped, and preserves every failed update report.
It never restores over the active database or installs a startup task.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from release_check import ROOT, check_release, database_preflight, database_tag


def checked_target(config, requested, confirmation=None, apply=False):
    host = str(config.get('HOST', '')).lower()
    if host not in {'127.0.0.1', 'localhost'}: raise ValueError('Updates are restricted to the explicitly configured loopback database.')
    if str(config.get('PORT', '')) != '55432': raise ValueError('This local updater is restricted to the project PostgreSQL port 55432.')
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', requested or '') or requested in {'postgres', 'template0', 'template1'}:
        raise ValueError('Select a named application database, not a system database.')
    if requested != config.get('NAME'): raise ValueError('Requested database does not match the configured application database.')
    if apply and confirmation != requested: raise ValueError('Apply requires --confirm-database to exactly repeat the target database name.')
    return requested


def listening(port):
    if not 1 <= port <= 65535: raise ValueError('Invalid reviewed runtime port.')
    with socket.socket() as probe:
        probe.settimeout(.35)
        return probe.connect_ex(('127.0.0.1', port)) == 0


def apply_update(config, release, *, ports=(8080, 8000), root=ROOT, run=subprocess.run):
    """Caller already performed explicit target confirmation and release check."""
    root = Path(root).resolve()
    if release.get('state') != 'verified' or not release.get('dependencies_matched'):
        raise ValueError('A stable sealed release with matching installed dependencies is required.')
    if any(listening(port) for port in ports):
        raise ValueError('A reviewed runtime port is listening. Stop the app before applying migrations; no process was stopped automatically.')
    tag = database_tag(config); stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    folder = root / '.local/updates'; folder.mkdir(parents=True, exist_ok=True)
    report_path = folder / f'{stamp}-{tag}.json'; log_path = report_path.with_suffix('.log')
    snapshot = root / '.local/backups' / f'pre-update-{stamp}.fernet'
    report = {'format': 1, 'database_tag': tag, 'release_id': release['release_id'],
              'started_at': datetime.now(timezone.utc).isoformat(), 'state': 'running', 'steps': [],
              'scope': 'Local forward migration; snapshot retained for separate recovery. No automatic live restore.'}
    commands = [
        ('encrypted-snapshot', [sys.executable, str(root / 'scripts/backup.py'), 'backup', '--output', str(snapshot)]),
        ('apply-migrations', [sys.executable, str(root / 'backend/manage.py'), 'migrate', '--noinput']),
        ('django-check', [sys.executable, str(root / 'backend/manage.py'), 'check']),
        ('core-ledger-check', [sys.executable, str(root / 'scripts/release_check.py'), '--database', '--ledger']),
    ]
    try:
        with log_path.open('x', encoding='utf-8') as log:
            for name, command in commands:
                try: code = run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, timeout=900, check=False).returncode
                except (OSError, subprocess.TimeoutExpired): code = 124
                # A fake successful child must not allow migration without a
                # real completed encrypted backup artifact.
                if name == 'encrypted-snapshot' and (not snapshot.is_file() or snapshot.stat().st_size == 0): code = code or 125
                report['steps'].append({'name': name, 'passed': code == 0, 'returncode': code})
                if code:
                    report['state'] = 'failed'; report['failed_step'] = name
                    break
            else: report['state'] = 'verified'
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return {'state': report['state'], 'release_id': report['release_id'], 'database_tag': tag,
            'failed_step': report.get('failed_step'), 'snapshot_retained': snapshot.is_file(),
            'note': 'A failed forward migration is not automatically rolled back. Inspect private evidence and use a separate recovery copy.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-database')
    parser.add_argument('--port', action='append', type=int, help='Every local runtime port to check; defaults 8080 and 8000.')
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / 'backend')); os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    from django.conf import settings
    config = settings.DATABASES['default']
    try: checked_target(config, args.database, args.confirm_database, args.apply)
    except ValueError as error: parser.error(str(error))
    release = check_release()
    database = database_preflight()
    ports = args.port or [8080, 8000]
    if not args.apply:
        stopped = not any(listening(port) for port in ports)
        ready = release['state'] == 'verified' and release['dependencies_matched'] and database['state'] == 'connected' and stopped
        print(json.dumps({'mode': 'dry_run', 'release': release, 'database': database,
                          'runtime_stopped': stopped, 'ready_for_apply': ready,
                          'actions': ['encrypted snapshot', 'forward migrations', 'Django check', 'ledger reconciliation'],
                          'changes_applied': False, 'requires_explicit_target_confirmation': True}, indent=2))
        return 0 if ready else 1
    if database['state'] != 'connected':
        print(json.dumps({'state': 'blocked', 'reason': 'Database inspection failed.'})); return 1
    # Serialize operator updates and refuse another updater without terminating it.
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [817290302]); locked = cursor.fetchone()[0]
    if not locked:
        print(json.dumps({'state': 'blocked', 'reason': 'Another reviewed update is running.'})); return 1
    try:
        try: result = apply_update(config, release, ports=ports)
        except ValueError as error:
            print(json.dumps({'state': 'blocked', 'reason': str(error)})); return 1
        print(json.dumps(result)); return 0 if result['state'] == 'verified' else 1
    finally:
        with connection.cursor() as cursor: cursor.execute('SELECT pg_advisory_unlock(%s)', [817290302])


if __name__ == '__main__': raise SystemExit(main())
