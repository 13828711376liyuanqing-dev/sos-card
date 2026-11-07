"""Exact byte-bound release reviews; does not grant device acceptance.

SAM | 2026-11-07 09:31 +08:00 | Bind review/build evidence to GR, SDK and CAT1 inputs because bool bypasses hide stale content.
"""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

SCAN_POLICY = 'yp001-inputs-v1'
TRUSTED = ('ble_app_uart_c', 'SDK', 'Air780EGH', 'firmware_releases', 'logs/version_control_20261107')
PRIVATE_DIRS = {'.git', '.svn', '.aws', '.ssh', 'ota_keys', 'test_keys'}
EXCLUDED_DIRS = {'objects', 'listings', '__pycache__'} | PRIVATE_DIRS
PRIVATE_SUFFIXES = {'.pem', '.key', '.p12', '.pfx'}


class GateError(ValueError):
    pass


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(files):
    data = {'scan_policy': SCAN_POLICY, 'excluded_dirs': sorted(EXCLUDED_DIRS),
            'private_suffixes': sorted(PRIVATE_SUFFIXES), 'cat1_scope': 'root-files-and-soc', 'files': files}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def safe_path(workspace, name, trusted=False):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise GateError(f'invalid relative schema path: {name!r}')
    p = PurePosixPath(name)
    if p.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
        raise GateError(f'path escape: {name!r}')
    if any(x != x.rstrip(' .') or x.casefold() in PRIVATE_DIRS for x in p.parts):
        raise GateError(f'private or Windows-aliased path rejected: {name}')
    if p.suffix.lower() in PRIVATE_SUFFIXES:
        raise GateError(f'private file rejected: {name}')
    if trusted and not any(name == r or name.startswith(r + '/') for r in TRUSTED):
        raise GateError(f'not a trusted source root: {name}')
    root = Path(workspace).resolve()
    target = root.joinpath(*p.parts)
    for part in [target, *target.parents]:
        if part == root: break
        # Windows junctions and other reparse points must not redirect inputs.
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise GateError(f'link/reparse point rejected: {name}')
    if not target.resolve().is_relative_to(root):
        raise GateError(f'outside workspace: {name}')
    return target


def tree_files(root, component):
    if root.is_symlink() or (root.exists() and getattr(root.lstat(), 'st_file_attributes', 0) & 0x400):
        raise GateError(f'link/reparse source root rejected: {root}')
    if not root.is_dir(): raise GateError(f'missing source root: {root}')
    files = {}
    def fail_walk(exc):
        raise GateError(f'unreadable source input: {exc}')
    for parent, dirs, names in os.walk(root, followlinks=False, onerror=fail_walk):
        parent = Path(parent)
        for name in dirs + names:
            path = parent / name
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                raise GateError(f'link/reparse point rejected: {path}')
        dirs[:] = sorted(d for d in dirs if d.casefold() not in EXCLUDED_DIRS and
                         (component != 'cat1' or parent != root or d == 'soc'))
        for name in sorted(names):
            path = parent / name
            if path.suffix.lower() in PRIVATE_SUFFIXES: continue
            if path.is_file(): files[path.relative_to(root).as_posix()] = file_hash(path)
    return files


def snapshot(workspace, mappings):
    before, after, seen = {}, {}, set()
    for item in mappings:
        component = item['component']
        if not isinstance(component, str) or not re.fullmatch(r'[a-z][a-z0-9_]*', component) or component in seen:
            raise GateError('duplicate/invalid component')
        seen.add(component)
        for field, result in [('baseline', before), ('candidate', after)]:
            root = safe_path(workspace, item[field], trusted=True)
            entries = tree_files(root, component)
            if not entries: raise GateError(f'empty input component: {component}')
            result.update({component + '/' + name: sha for name, sha in entries.items()})
    if not {'gr', 'cat1', 'sdk'} <= seen: raise GateError('gr/cat1/sdk mappings required')
    return before, after


def evidence(workspace, record):
    for field in ('reviewer', 'reason'):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise GateError(f'missing {field}')
    entries = record.get('evidence')
    if not isinstance(entries, list) or not entries: raise GateError('hashed evidence required')
    for item in entries:
        path = safe_path(workspace, item['path'])
        if not path.is_file() or path.stat().st_size == 0 or file_hash(path) != item['sha256']:
            raise GateError(f'evidence stale/missing: {item["path"]}')


def baseline_anchor(workspace, manifest, before=None):
    """SAM | 2026-11-07 09:33 +08:00 | Bind G0 to frozen metadata because arbitrary baseline aliases are not verified inputs."""
    anchor = manifest['baseline_manifest']
    expected_path = 'firmware_releases/baselines/' + manifest['baseline_id'] + '/manifest.json'
    if anchor['path'] != expected_path: raise GateError('baseline manifest is not its immutable release path')
    path = safe_path(workspace, anchor['path'], trusted=True)
    if file_hash(path) != anchor['sha256']: raise GateError('baseline metadata anchor mismatch')
    frozen = json.loads(path.read_text(encoding='utf-8-sig'))
    if frozen.get('schema') != 'YP001_LOCAL_BASELINE_V1' or frozen.get('release_id') != manifest['baseline_id']:
        raise GateError('wrong frozen baseline schema/identity')
    alignment = frozen['source_alignment']
    if alignment.get('status') != 'verified_build_inputs':
        raise GateError('baseline source alignment pending/unproven; publication cannot proceed')
    evidence(workspace, alignment)
    if before is None:
        return
    inventory = frozen['files']
    if not isinstance(inventory, list): raise GateError('baseline inventory must be a list')
    indexed = {}
    for item in inventory:
        relative = item['path']
        if relative in indexed: raise GateError('duplicate baseline inventory path')
        target = safe_path(workspace, path.parent.relative_to(Path(workspace).resolve()).as_posix() + '/' + relative)
        if not target.is_relative_to(path.parent): raise GateError('baseline inventory path escape')
        indexed[relative] = item['sha256']
    for mapping in manifest['mappings']:
        base = safe_path(workspace, mapping['baseline'], trusted=True)
        if not base.is_relative_to(path.parent): raise GateError('baseline mapping is outside anchored release')
        prefix = mapping['component'] + '/'
        for key, sha in before.items():
            if key.startswith(prefix):
                inventory_path = (base / key[len(prefix):]).relative_to(path.parent).as_posix()
                if indexed.get(inventory_path) != sha:
                    raise GateError(f'input is not in anchored baseline inventory: {inventory_path}')


def validate(workspace, manifest, cat_src, baseline, gr_hex, findings):
    """Return content identity; only R1 content differences may be reviewed.

    attestation = review of activation + baseline Boot switch/rollback evidence;
    it never declares the target candidate's device OTA/business tests passed.
    """
    try:
        if not isinstance(manifest, dict): raise GateError('review manifest must be an object')
        if manifest.get('schema_version') != 1 or manifest.get('scan_policy') != SCAN_POLICY:
            raise GateError('unsupported review schema/scan policy')
        for key in ('baseline_id', 'candidate_id'):
            if not isinstance(manifest.get(key), str) or not manifest[key].strip(): raise GateError(f'missing {key}')
        hard = [r for r in findings if r[0] == 'BLOCK' and r[1] != 'R1 OTA文件']
        if hard: raise GateError('non-reviewable OTA BLOCK: ' + repr(hard[:8]))
        # SAM | 2026-11-07 09:50 +08:00 | Reject incomplete G0 before hashing source trees; full inventory check remains after snapshot.
        baseline_anchor(workspace, manifest)
        mappings = manifest['mappings']
        by_component = {m['component']: m for m in mappings}
        cm = by_component['cat1']
        if safe_path(workspace, cm['candidate']).resolve() != Path(cat_src).resolve():
            raise GateError('CAT1 review mapping does not match selected inputs')
        if tree_files(safe_path(workspace, cm['baseline'], trusted=True), 'cat1') != tree_files(Path(baseline), 'cat1'):
            raise GateError('CAT1 baseline copy does not match selected verified baseline')
        if safe_path(workspace, by_component['gr']['candidate']).resolve() != Path(workspace).resolve() / 'ble_app_uart_c':
            raise GateError('GR candidate must be the active main project')
        if safe_path(workspace, by_component['sdk']['candidate']).resolve() != Path(workspace).resolve() / 'SDK':
            raise GateError('SDK candidate must be the active SDK')
        before, after = snapshot(workspace, mappings)
        baseline_anchor(workspace, manifest, before)
        if before != manifest['baseline_files'] or after != manifest['candidate_files']:
            raise GateError('source inputs changed since review')
        bsha, csha = digest(before), digest(after)
        if bsha != manifest['baseline_sha256'] or csha != manifest['candidate_sha256']:
            raise GateError('source digest mismatch')
        expected = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
        reviewed = set()
        for item in manifest['changes']:
            path = item['path']
            if path in reviewed or path not in expected or item['before_sha256'] != before.get(path) or item['after_sha256'] != after.get(path):
                raise GateError(f'inexact or duplicate change: {path}')
            evidence(workspace, item)
            reviewed.add(path)
        if reviewed != expected: raise GateError('review must cover the exact full change set')
        for field in ('build_evidence', 'attestation'):
            record = manifest[field]
            if record.get('source_sha256') != csha: raise GateError(f'stale {field} source binding')
            evidence(workspace, record)
        gsha = file_hash(gr_hex)
        if manifest['build_evidence'].get('gr_hex_sha256') != gsha: raise GateError('GR HEX not bound to build evidence')
        return dict(candidate_sha256=csha, gr_hex_sha256=gsha)
    except (KeyError, TypeError, OSError, AttributeError, json.JSONDecodeError) as exc:
        raise GateError(f'incomplete/invalid review manifest: {exc}') from exc


def check_identity(out_root, version, build, identity, artifacts=None):
    """Legacy releases without input identity reserve their version conservatively."""
    root = Path(out_root)
    if not root.exists(): return
    for path in sorted(root.glob('baselines/*/manifest.json')):
        try: frozen = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as exc: raise GateError(f'unreadable baseline identity: {path}') from exc
        fw = frozen.get('firmware', {})
        if any((fw.get(v), fw.get(b)) == (version, build) for v, b in [('gr_version', 'gr_build'), ('cat_version', 'cat_build')]):
            raise GateError(f'version/build reserved by immutable baseline: {path}')
    for path in sorted(root.glob('*/run.json')):
        try: record = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as exc: raise GateError(f'unreadable release identity: {path}') from exc
        if (record.get('to_version'), record.get('to_build')) == (version, build):
            if record.get('input_identity') != identity:
                raise GateError(f'version/build already reserved by different or unbound content: {path}')
            if artifacts is not None and record.get('artifact_identity') != artifacts:
                raise GateError(f'version/build already has different or unbound artifacts: {path}')


def reserve_output(out):
    try: Path(out).mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc: raise GateError(f'release_id already exists: {out}') from exc


def validate_device(workspace, proof, last_run):
    """Verify a separately supplied record, not automatic inference from host tests."""
    try:
        if not isinstance(proof, dict) or proof.get('schema_version') != 1 or proof.get('purpose') != 'device_ota_acceptance':
            raise GateError('invalid device evidence schema/purpose')
        for key in ('input_identity', 'artifact_identity'):
            if not last_run.get(key) or proof.get(key) != last_run[key]:
                raise GateError(f'device evidence is not bound to last_run {key}')
        for source, target in [('to_version', 'to_version'), ('to_build', 'to_build'), ('package_md5', 'md5')]:
            if proof.get(source) != last_run[target]: raise GateError(f'wrong device task: {source}')
        version, build = last_run['to_version'], last_run['to_build']
        observed = proof['observations']
        expected = dict(gr=dict(version=version, build=build),
            cat1=dict(version=version, build=build, native_phase='IDLE', outbox=0),
            owner=dict(phase='COMPLETE', result='success', actual_version=version, target='CAT1'),
            boot=dict(state='CONFIRMED'))
        for component, fields in expected.items():
            for field, value in fields.items():
                if observed[component].get(field) != value:
                    raise GateError(f'device terminal state mismatch: {component}.{field}')
        evidence(workspace, proof)
        return proof
    except (KeyError, TypeError, OSError, AttributeError, json.JSONDecodeError) as exc:
        raise GateError(f'incomplete device evidence: {exc}') from exc


DELIVERY_DIRS = ('1_GR烧写文件', '2_CAT1刷机目录', '3_上传平台的升级包')


def delivery_files(out):
    files = {}
    for name in DELIVERY_DIRS:
        files.update({name + '/' + rel: sha for rel, sha in tree_files(Path(out) / name, 'delivery').items()})
    return files


def verify_run_files(workspace, last_run):
    try:
        root = Path(workspace).resolve()
        def selected_path(value):
            path = Path(value)
            if not path.is_absolute(): path = root / path
            return safe_path(root, path.relative_to(root).as_posix(), trusted=True)
        out, source = selected_path(last_run['out']), selected_path(last_run['target_source'])
        if not out.is_relative_to(root / 'firmware_releases') or source != out / 'work/target_source':
            raise GateError('done must reference the frozen release target_source')
        actual = tree_files(source, 'cat1')
        if actual != last_run['target_source_files'] or digest(actual) != last_run['target_source_sha256']:
            raise GateError('last_run target source drifted/missing')
        if delivery_files(out) != last_run['artifact_files']:
            raise GateError('last_run deliverables drifted/missing')
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise GateError(f'unbound/missing release files: {exc}') from exc


def check_known_identity(workspace, out_root, version, build, identity, artifacts=None):
    canonical = Path(workspace) / 'firmware_releases'
    check_identity(canonical, version, build, identity, artifacts)
    if Path(out_root).resolve() != canonical.resolve():
        check_identity(out_root, version, build, identity, artifacts)
