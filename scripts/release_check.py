"""Read-only release identity, installed dependency and PostgreSQL preflight.

Manifests are local integrity evidence, not signed distribution certificates.
Only build_release.py seals a build after verifying unchanged source inputs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FORMAT = 1


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def database_tag(config):
    host = str(config.get('HOST', config.get('PGHOST', '127.0.0.1'))).lower()
    if host == 'localhost': host = '127.0.0.1'
    port = str(config.get('PORT', config.get('PGPORT', '55432')))
    name = str(config.get('NAME', config.get('PGDATABASE', 'sponge_erp')))
    return hashlib.sha256(f'{host}:{port}:{name}'.encode()).hexdigest()[:24]


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def source_files(root=ROOT):
    root = Path(root).resolve()
    candidates = []
    for directory in ('backend', 'frontend/src', 'frontend/public', 'scripts'):
        folder = root / directory
        if folder.is_dir():
            candidates += [p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                           and not (directory == 'backend' and 'tests' in p.parts)
                           and p.suffix not in {'.pyc', '.log'}]
    for relative in ('Open Nawa ERP.cmd','Open Nawa LAN.cmd','requirements.txt', 'frontend/package.json', 'frontend/package-lock.json', 'frontend/index.html',
                     'frontend/vite.config.ts', 'frontend/tsconfig.json', 'frontend/tsconfig.app.json', 'frontend/tsconfig.node.json'):
        if (root / relative).is_file(): candidates.append(root / relative)
    candidates += list((root / 'output/pdf').glob('*.pdf')) if (root / 'output/pdf').is_dir() else []
    result = {}
    for path in sorted(set(candidates)):
        resolved = path.resolve()
        if not resolved.is_relative_to(root): raise ValueError('A release input resolves outside the project.')
        result[path.relative_to(root).as_posix()] = sha256(path)
    if not result or 'frontend/package.json' not in result or 'requirements.txt' not in result:
        raise ValueError('A complete existing ERP workspace is required.')
    return result


def built_files(root=ROOT):
    root = Path(root).resolve(); dist = root / 'frontend/dist'
    if not (dist / 'index.html').is_file(): return {}
    result = {}
    for path in sorted(dist.rglob('*')):
        if not path.is_file(): continue
        if not path.resolve().is_relative_to(dist.resolve()): raise ValueError('A built asset resolves outside the release.')
        result[path.relative_to(dist).as_posix()] = sha256(path)
    return result


def installed_dependencies(root=ROOT):
    results = []
    for line in (Path(root) / 'requirements.txt').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^ ;]+)', line)
        if not match:
            results.append({'package': line.split('=')[0][:60], 'state': 'unsupported_requirement'}); continue
        name, expected = match.groups()
        try: actual = metadata.version(name)
        except metadata.PackageNotFoundError: actual = None
        results.append({'package': name, 'expected': expected, 'installed': actual,
                        'state': 'matched' if actual == expected else 'missing' if actual is None else 'mismatch'})
    return results


def manifest_path(root=ROOT):
    return Path(root) / '.local/releases/current.json'


def load_manifest(root=ROOT):
    path = manifest_path(root)
    if not path.is_file(): return None
    if path.stat().st_size > 5 * 1024 * 1024: raise ValueError('Release manifest is too large.')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('format') != FORMAT or not isinstance(data.get('sources'), dict) or not isinstance(data.get('assets'), dict):
        raise ValueError('Unsupported release manifest.')
    identity = canonical_hash({'sources': data['sources'], 'assets': data['assets'], 'version': data.get('version')})
    if identity != data.get('release_id'): raise ValueError('Release manifest identity is inconsistent.')
    for mapping in (data['sources'], data['assets']):
        for name, digest in mapping.items():
            if not isinstance(name, str) or '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts or not re.fullmatch(r'[a-f0-9]{64}', str(digest)):
                raise ValueError('Unsafe or malformed release manifest entry.')
    return data


def check_release(root=ROOT):
    root = Path(root)
    dependencies = installed_dependencies(root)
    try:
        manifest = load_manifest(root)
        sources = source_files(root); assets = built_files(root)
        source_aligned = bool(manifest and sources == manifest['sources'])
        assets_aligned = bool(manifest and assets and assets == manifest['assets'])
        state = 'verified' if source_aligned and assets_aligned else 'not_sealed' if not manifest else 'changed'
        note = 'Source and built-asset checksums match the recorded build.' if state == 'verified' else 'Build and seal the final stable source before applying an update.'
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        manifest = None; assets = {}; source_aligned = assets_aligned = False; state = 'invalid'
        note = 'Release integrity could not be verified. Review the private operator manifest.'
    return {'format': FORMAT, 'state': state, 'version': manifest.get('version') if manifest else None,
            'release_id': manifest.get('release_id') if manifest else None,
            'built_at': manifest.get('built_at') if manifest else None,
            'source_aligned': source_aligned, 'assets_aligned': assets_aligned,
            'asset_count': len(assets), 'dependencies': dependencies,
            'dependencies_matched': bool(dependencies) and all(row['state'] == 'matched' for row in dependencies),
            'note': note, 'integrity_scope': 'Local checksums, not publisher signature verification.'}


def database_preflight():
    """Only SELECTs; never initialize, migrate, seed or repair the database."""
    try:
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1'); cursor.fetchone()
        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        return {'state': 'connected', 'engine': 'postgresql', 'pending_migrations': len(pending), 'schema_current': not pending}
    except Exception:
        return {'state': 'unavailable', 'engine': 'postgresql', 'pending_migrations': None, 'schema_current': False,
                'note': 'Database/schema inspection failed. Inspect the private operator log; connection details are omitted.'}


def ledger_preflight():
    """Core ledger/stock integrity in one consistent SQL snapshot; no demo user."""
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
WITH bad_journal AS (
 SELECT d.id FROM erp_document d LEFT JOIN erp_entry e ON e.document_id=d.id
 WHERE d.state='posted' GROUP BY d.id HAVING COALESCE(sum(e.debit-e.credit),0)<>0
), bad_control AS (
 SELECT b.id FROM erp_business b WHERE
 round(COALESCE((SELECT sum(e.debit-e.credit) FROM erp_entry e JOIN erp_document d ON d.id=e.document_id JOIN erp_account a ON a.id=e.account_id WHERE d.business_id=b.id AND d.state='posted' AND a.code IN ('RAW','FG','TRIM','TRANSIT')),0),2)
 <>round(COALESCE((SELECT sum(s.value) FROM erp_stockpool s WHERE s.business_id=b.id),0),2)
), bad_pool AS (
 SELECT p.id FROM erp_stockpool p LEFT JOIN erp_stockmovement s ON s.pool_id=p.id LEFT JOIN erp_document d ON d.id=s.document_id
 GROUP BY p.id HAVING p.quantity<>COALESCE(sum(s.quantity) FILTER(WHERE d.state='posted'),0)
 OR p.value<>COALESCE(sum(s.value) FILTER(WHERE d.state='posted'),0)
)
SELECT (SELECT count(*) FROM bad_journal), (SELECT count(*) FROM bad_control), (SELECT count(*) FROM bad_pool),
 (SELECT count(*) FROM erp_stockpool WHERE quantity<0 OR value<0),
 (SELECT count(*) FROM erp_block WHERE remaining_height_mm<0 OR reserved_height_mm<0 OR reserved_height_mm>remaining_height_mm)
""")
            values = cursor.fetchone()
        return {'state': 'verified' if not any(values) else 'failed',
                'checks': [dict(check=name, passed=count == 0) for name, count in zip(
                    ['posted_journals', 'inventory_controls', 'stock_pool_cache', 'nonnegative_stock', 'block_reservations'], values)],
                'scope': 'Core journal and physical inventory controls; not a full statutory or foreign monetary subledger review.'}
    except Exception:
        return {'state': 'unavailable', 'checks': [], 'scope': 'Core ledger inspection failed; review the private operator log.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', action='store_true', help='Also read the configured database/schema state.')
    parser.add_argument('--ledger', action='store_true', help='Read core journal/stock controls without any demo-account assumptions.')
    args = parser.parse_args(argv)
    result = check_release()
    if args.database or args.ledger:
        import os
        sys.path.insert(0, str(ROOT / 'backend')); os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
        import django
        django.setup()
        if args.database: result['database'] = database_preflight()
        if args.ledger: result['ledger'] = ledger_preflight()
    print(json.dumps(result, indent=2))
    return 0 if result['state'] == 'verified' and result['dependencies_matched'] and (not args.database or result['database']['schema_current']) and (not args.ledger or result['ledger']['state'] == 'verified') else 1


if __name__ == '__main__': raise SystemExit(main())
