"""Build the frontend and record an integrity manifest for unchanged ERP source."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from release_check import ROOT, FORMAT, source_files, built_files, canonical_hash, manifest_path


def build(root=ROOT, run=subprocess.run):
    root = Path(root).resolve()
    before = source_files(root)
    npm = shutil.which('npm.cmd') or shutil.which('npm')
    if not npm: raise ValueError('Node/npm is required to build the existing frontend.')
    completed = run([npm, '--prefix', str(root / 'frontend'), 'run', 'build'], cwd=root, check=False)
    if completed.returncode: raise ValueError('Frontend build failed; no release was sealed.')
    after = source_files(root)
    if before != after: raise ValueError('Source changed during the build. Stop edits and rebuild; no release was sealed.')
    assets = built_files(root)
    if not assets: raise ValueError('Built frontend assets are missing; no release was sealed.')
    version = str(json.loads((root / 'frontend/package.json').read_text(encoding='utf-8'))['version'])
    identity = {'sources': after, 'assets': assets, 'version': version}
    result = {'format': FORMAT, 'release_id': canonical_hash(identity), 'version': version,
              'built_at': datetime.now(timezone.utc).isoformat(), 'sources': after, 'assets': assets,
              'build_command': 'npm --prefix frontend run build',
              'scope': 'Locally built unchanged source and assets; no signed package or rollback guarantee.'}
    current = manifest_path(root); current.parent.mkdir(parents=True, exist_ok=True)
    archive = current.parent / (result['release_id'] + '.json')
    if not archive.exists(): archive.write_text(json.dumps(result, indent=2), encoding='utf-8')
    temporary = current.with_suffix('.tmp'); temporary.write_text(json.dumps(result, indent=2), encoding='utf-8'); temporary.replace(current)
    return {'sealed': True, 'release_id': result['release_id'], 'version': version, 'assets': len(assets), 'source_count': len(after)}


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    try: result = build()
    except (OSError, ValueError) as error:
        print(json.dumps({'sealed': False, 'error': str(error)})); return 1
    print(json.dumps(result)); return 0


if __name__ == '__main__': raise SystemExit(main())
