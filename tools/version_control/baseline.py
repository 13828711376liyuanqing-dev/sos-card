"""SAM | 2026-11-07 09:20 +08:00 | Freeze recoverable local inputs; never restore firmware or infer device acceptance."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat


EXCLUDED_DIRS = {'.git', '.svn', '__pycache__', 'Objects', 'Listings'}
PRIVATE_SUFFIXES = {'.pem', '.key', '.p12', '.pfx'}
FORBIDDEN = {'.git', '.aws', 'ota_keys', 'test_keys'}
WORKERS = 4
EXCLUDED_CASE = {x.casefold() for x in EXCLUDED_DIRS} | FORBIDDEN


def checked(info, path: Path):
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError(f'Link/junction refused: {path}')
    return info


def scan(directory: Path):
    # SAM | 2026-11-07 09:40 +08:00 | Inspect each directory entry once, retaining no ancestor-per-file resolve cost; never follow reparse points.
    with os.scandir(directory) as entries:
        for entry in entries:
            path = Path(entry.path)
            info = checked(entry.stat(follow_symlinks=False), path)
            yield path, info


def stamp(info):
    # Windows Python 3.12 lstat/fstat ctime can use different creation/change semantics.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def relative(value: str) -> Path:
    p = PurePosixPath(value)
    if not value or '\\' in value or ':' in value or p.is_absolute() or any(x in ('', '.', '..') for x in value.split('/')):
        raise ValueError(f'Unsafe relative path: {value}')
    if any(x.endswith(('.', ' ')) for x in p.parts):
        raise ValueError('Windows trailing-dot/space path alias refused')
    if any(x.casefold() in FORBIDDEN for x in p.parts):
        raise ValueError(f'Protected/private input: {value}')
    return Path(*p.parts)


def safe_path(root: Path, value: str, validated=None) -> Path:
    # SAM | 2026-11-07 09:44 +08:00 | Cache validated components only within one scan, including explicit-file input batches; later scans start fresh.
    if not root.is_absolute():
        raise ValueError('Canonical absolute root required')
    p = root / relative(value)
    validated = {} if validated is None else validated
    for part in reversed([p, *p.parents][:len(p.relative_to(root).parts) + 1]):
        if part in validated:
            continue
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        checked(info, part)
        validated[part] = info
    return p


def collect(root: Path, inputs: list[dict], validated=None) -> tuple[list[tuple[Path, str]], list[str]]:
    result, omitted, destinations = [], [], set()
    validated = {} if validated is None else validated
    for item in inputs:
        origin = safe_path(root, item['path'], validated)
        destination = relative(item['destination']).as_posix()
        if origin not in validated:
            raise ValueError(f'Missing required input: {origin}')
        is_directory = stat.S_ISDIR(validated[origin].st_mode)
        if is_directory:
            files, pending = [], [origin]
            while pending:
                for child, info in scan(pending.pop()):
                    if child.name.casefold() not in FORBIDDEN:
                        relative(child.relative_to(root).as_posix())
                    if stat.S_ISDIR(info.st_mode):
                        if child.name.casefold() not in EXCLUDED_CASE:
                            pending.append(child)
                    elif stat.S_ISREG(info.st_mode):
                        files.append(child)
                    else:
                        raise ValueError(f'Non-regular input refused: {child}')
        else:
            if not stat.S_ISREG(validated[origin].st_mode):
                raise ValueError(f'Non-regular input refused: {origin}')
            files = [origin]
        for source in sorted(files):
            if source.suffix.lower() in PRIVATE_SUFFIXES:
                omitted.append(source.relative_to(root).as_posix())
                continue
            tail = source.relative_to(origin).as_posix() if is_directory else ''
            target = destination + ('/' + tail if tail else '')
            relative(target)
            if target.casefold() in destinations or target.casefold() == 'manifest.json':
                raise ValueError(f'Duplicate/reserved output: {target}')
            destinations.add(target.casefold())
            result.append((source, target))
    return result, sorted(omitted)


def copy_one(root: Path, output: Path, pair):
    # SAM | 2026-11-07 09:40 +08:00 | Hash exactly the bytes streamed into an exclusive new file; detect replacement or modification around the open handle.
    source, target = pair
    before = checked(source.lstat(), source)
    dst = output / relative(target)
    h = hashlib.sha256()
    size = 0
    with source.open('rb') as src, dst.open('xb') as dest:
        if stamp(before) != stamp(os.fstat(src.fileno())):
            raise ValueError(f'Input changed before copy: {source}')
        for chunk in iter(lambda: src.read(1024 * 1024), b''):
            h.update(chunk)
            dest.write(chunk)
            size += len(chunk)
        if stamp(before) != stamp(os.fstat(src.fileno())):
            raise ValueError(f'Input changed during freeze: {source}; incomplete directory retained')
    if stamp(before) != stamp(checked(source.lstat(), source)) or size != before.st_size:
        raise ValueError(f'Input changed during freeze: {source}; incomplete directory retained')
    os.utime(dst, ns=(before.st_atime_ns, before.st_mtime_ns))
    return {'path': target, 'origin': source.relative_to(root).as_posix(), 'sha256': h.hexdigest(), 'bytes': size}


def freeze(root: Path, spec: dict, output: Path) -> dict:
    root = root.absolute()
    for part in [root, *root.parents]:
        checked(part.lstat(), part)
    root, output = root.resolve(), output.absolute()
    if not output.is_relative_to(root) or output == root:
        raise ValueError('Output must be a new directory inside workspace')
    safe_path(root, output.relative_to(root).as_posix())
    if output.exists():
        raise ValueError('Refusing to overwrite an existing baseline')
    validated = {}
    for item in spec['inputs']:
        origin = safe_path(root, item['path'], validated)
        if origin in validated and stat.S_ISDIR(validated[origin].st_mode) and output.is_relative_to(origin):
            raise ValueError('Output is inside an input directory')
    files, omitted = collect(root, spec['inputs'], validated)
    for source, _ in files:
        if source.is_relative_to(output) or output.is_relative_to(source):
            raise ValueError('Output overlaps an input')
    if not files or not spec.get('release_id') or not isinstance(spec.get('verification'), dict) or not spec.get('verification') or not isinstance(spec.get('rollback_plan'), str) or not spec.get('rollback_plan'):
        raise ValueError('Identity, verification scope and rollback plan are required')
    targets = {target.casefold() for _, target in files}
    for target in targets:
        if any(p.as_posix().casefold() in targets for p in Path(target).parents if p != Path('.')):
            raise ValueError(f'File/directory output collision: {target}')
    output.mkdir(parents=True, exist_ok=False)
    for parent in sorted({(output / target).parent for _, target in files}):
        parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        inventory = list(pool.map(lambda pair: copy_one(root, output, pair), files))
    if collect(root, spec['inputs']) != (files, omitted):
        raise ValueError('Input file set changed during freeze; incomplete directory retained')
    # A second source pass catches edits to earlier files while later files were copied.
    def validate_source(pair):
        (source, _), entry = pair
        before = checked(source.lstat(), source)
        if sha(source) != entry['sha256'] or stamp(before) != stamp(checked(source.lstat(), source)):
            raise ValueError(f'Input drift during freeze: {source}; incomplete directory retained')
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(validate_source, zip(files, inventory)))
    if collect(root, spec['inputs']) != (files, omitted):
        raise ValueError('Input file set changed during final validation; incomplete directory retained')
    manifest = {**spec, 'schema': 'YP001_LOCAL_BASELINE_V1',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'scan_exclusions': {'directories': sorted(EXCLUDED_DIRS | FORBIDDEN), 'private_suffixes': sorted(PRIVATE_SUFFIXES)},
                'omitted_private_files': omitted, 'files': inventory}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    verify(output, sha(output / 'manifest.json'))
    return manifest


def verify(directory: Path, expected_manifest_sha256: str) -> dict:
    # SAM | 2026-11-07 09:27 +08:00 | Validate lexical root before resolve, which would hide a junction. This verifies frozen bytes, not device acceptance.
    directory = directory.absolute()
    for part in [directory, *directory.parents]:
        checked(part.lstat(), part)
    directory = directory.resolve()
    safe_path(directory, 'manifest.json')
    if sha(directory / 'manifest.json') != expected_manifest_sha256:
        raise ValueError('Manifest differs from external SHA256 anchor')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 'YP001_LOCAL_BASELINE_V1':
        raise ValueError('Unknown baseline schema')
    expected = {'manifest.json'}
    seen = {'manifest.json'}
    for item in manifest['files']:
        if item['path'].casefold() in seen:
            raise ValueError('Duplicate manifest path')
        expected.add(item['path'])
        seen.add(item['path'].casefold())
        relative(item['path'])
    def scan_members():
        sizes, pending = {}, [directory]
        while pending:
            for p, info in scan(pending.pop()):
                name = p.relative_to(directory).as_posix()
                relative(name)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(p)
                elif stat.S_ISREG(info.st_mode):
                    sizes[name] = info.st_size
                else:
                    raise ValueError(f'Non-regular baseline member: {p}')
        return sizes
    sizes = scan_members()
    actual = set(sizes)
    if actual != expected:
        raise ValueError('Unexpected or missing baseline members')
    def validate_member(item):
        p = directory / item['path']
        before = checked(p.lstat(), p)
        if sizes[item['path']] != item['bytes'] or sha(p) != item['sha256'] or stamp(before) != stamp(checked(p.lstat(), p)):
            raise ValueError(f'Baseline hash/size mismatch: {item["path"]}')
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(validate_member, manifest['files']))
    if scan_members() != sizes:
        raise ValueError('Baseline members changed during verification')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('freeze')
    command.add_argument('--spec', type=Path, required=True)
    command.add_argument('--output', type=Path, required=True)
    command.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[2])
    command = sub.add_parser('verify')
    command.add_argument('--directory', type=Path, required=True)
    command.add_argument('--expected-manifest-sha256', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'freeze':
            m = freeze(args.workspace, json.loads(args.spec.read_text(encoding='utf-8')), args.output)
        else:
            m = verify(args.directory, args.expected_manifest_sha256)
        print(json.dumps({'release_id': m['release_id'], 'files': len(m['files']), 'file_integrity_verified': True, 'manifest_sha256': sha((args.output if args.command == 'freeze' else args.directory) / 'manifest.json')}))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f'BLOCK: {error}\n')


if __name__ == '__main__':
    main()
