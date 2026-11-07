"""SAM | 2026-11-07 09:44 +08:00 | Compare retained old/new engines on synthetic inputs; retain all evidence without deleting files."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time
import uuid

import baseline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old-engine', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence_root.absolute() / ('synthetic_' + uuid.uuid4().hex)
    source = root / 'source'
    source.mkdir(parents=True, exist_ok=False)
    for number in range(250):
        directory = source / f'group_{number % 10}' / 'nested'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f'{number:04}.c').write_bytes((f'synthetic file {number}\n'.encode() * 64))
    for number in range(4):
        (source / f'large_{number}.bin').write_bytes(bytes([number]) * 1024 * 1024)
    spec = {'release_id': 'synthetic-performance-only', 'verification': {'host': 'synthetic'},
            'rollback_plan': 'Retain evidence; no device operation',
            'inputs': [{'path': path.relative_to(root).as_posix(),
                        'destination': path.relative_to(root).as_posix()}
                       for path in sorted(source.rglob('*')) if path.is_file()]}
    loader = importlib.util.spec_from_file_location('baseline_before', args.old_engine)
    old = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(old)
    measurements, inventories = [], []
    # Alternate run order to expose cache/order effects; every run has a fresh exclusive output.
    for label, engine in [('old', old), ('new', baseline), ('new', baseline), ('old', old)]:
        output = root / f'{len(measurements)}_{label}'
        start = time.perf_counter()
        manifest = engine.freeze(root, spec, output)
        elapsed = time.perf_counter() - start
        inventories.append(manifest['files'])
        measurements.append({'engine': label, 'seconds': elapsed, 'output': str(output),
                             'manifest_sha256': baseline.sha(output / 'manifest.json')})
    identical = all(inventory == inventories[0] for inventory in inventories)
    if not identical:
        raise ValueError('Old/new inventories differ')
    old_mean = sum(x['seconds'] for x in measurements if x['engine'] == 'old') / 2
    new_mean = sum(x['seconds'] for x in measurements if x['engine'] == 'new') / 2
    result = {'created_utc': datetime.now(timezone.utc).isoformat(), 'fixture': str(root),
              'files': len(inventories[0]), 'bytes': sum(x['bytes'] for x in inventories[0]),
              'workers': baseline.WORKERS, 'old_mean_seconds': old_mean,
              'new_mean_seconds': new_mean, 'speedup': old_mean / new_mean,
              'identical_path_origin_size_sha256_inventory': identical, 'measurements': measurements,
              'limitations': 'Synthetic warm-cache local run; no guarantee of full-tree or other-volume speed. Not an atomic filesystem snapshot or hardware acceptance.'}
    (root / 'benchmark.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
