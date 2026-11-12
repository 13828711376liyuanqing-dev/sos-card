"""SAM | 2026-10-13 +08:00 | Build an offline, immutable CAT1 Luatools import set from the current Air780EGH sources."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / 'Air780EGH'
# SAM | 2026-10-13 09:20 +08:00 | Keep generated import sets under Air780EGH because operators maintain this one project directory.
DEFAULT_RELEASES = DEFAULT_SOURCE / '_luatools_release/releases'
DEFAULT_STATE = DEFAULT_SOURCE / '_luatools_release'
DEFAULT_SOC = 'soc/LuatOS-SoC_V2052_Air780EGH_113.soc'
CAPACITY = 512 * 1024
RESERVE = 32 * 1024
sys.path.insert(0, str(ROOT / 'tools/ota'))
from prepare_cat1_luatools import strip_comments


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def snapshot(source: Path) -> tuple[dict[str, bytes], dict[str, str]]:
    if not source.is_dir():
        raise ValueError('Air780EGH source directory missing')
    scripts = sorted(source.glob('*.lua'))
    if not (source / 'main.lua').is_file() or not scripts:
        raise ValueError('main.lua or Lua sources missing')
    audio = sorted(path for path in source.iterdir() if path.is_file() and
                   path.suffix.lower() in {'.mp3', '.wav', '.amr'})
    if not (source / 'sample-6s.mp3').is_file():
        raise ValueError('required sample-6s.mp3 missing')
    paths = scripts + audio
    data = {path.name: path.read_bytes() for path in paths}
    hashes = {name: digest(raw) for name, raw in data.items()}
    return data, hashes


def compare(previous: dict | None, hashes: dict[str, str]) -> dict[str, list[str]]:
    old = previous.get('source_sha256', {}) if previous else {}
    return {
        'added': sorted(set(hashes) - set(old)),
        'changed': sorted(name for name in set(hashes) & set(old) if hashes[name] != old[name]),
        'removed': sorted(set(old) - set(hashes)),
    }


def prepare(source: Path, releases: Path, state: Path, capacity: int = CAPACITY,
            reserve: int = RESERVE) -> dict:
    from lupa.lua54 import LuaRuntime

    if not 0 < reserve < capacity:
        raise ValueError('invalid capacity/reserve')
    soc = source / DEFAULT_SOC
    if not soc.is_file():
        raise ValueError('approved LuatOS .soc missing')
    # SAM | 2026-10-13 09:10 +08:00 | Pin the .soc digest too because a changed bottom package must invalidate the prepared set.
    soc_hash = digest(soc.read_bytes())
    data, hashes = snapshot(source)
    names = sorted(data)
    previous_path = state / 'latest_ready.json'
    previous = json.loads(previous_path.read_text(encoding='utf-8')) if previous_path.exists() else None
    delta = compare(previous, hashes)
    lua = LuaRuntime(unpack_returned_tuples=True)
    compile_lua = lua.eval('function(s,n) local f,e=load(s,n); return f~=nil,e end')
    prepared: dict[str, bytes] = {}
    details = []
    for name in names:
        raw = data[name]
        if name.endswith('.lua'):
            original = raw.decode('utf-8-sig')
            compact = strip_comments(original)
            for label, value in [('source', original), ('release', compact)]:
                ok, error = compile_lua(value, name)
                if not ok:
                    raise ValueError(f'{name} {label} Lua syntax: {error}')
            payload = compact.encode('utf-8')
        else:
            payload = raw
        prepared[name] = payload
        details.append({'name': name, 'source_bytes': len(raw), 'release_bytes': len(payload),
                        'source_sha256': hashes[name], 'release_sha256': digest(payload)})
    selected_bytes = sum(len(payload) for payload in prepared.values())
    if selected_bytes > capacity - reserve:
        raise ValueError(f'size exceeds safe budget: {selected_bytes} > {capacity-reserve} bytes')
    # SAM | 2026-10-13 +08:00 | Reject a mixed release if another task changes any source during the build.
    _, latest_hashes = snapshot(source)
    if latest_hashes != hashes or digest(soc.read_bytes()) != soc_hash:
        raise RuntimeError('Air780EGH changed during preparation; rerun after edits settle')
    source_fingerprint = digest(json.dumps(hashes, sort_keys=True).encode('utf-8'))
    release_dir = releases / source_fingerprint[:16]
    release_dir.parent.mkdir(parents=True, exist_ok=True)
    if release_dir.exists():
        actual = {path.name for path in release_dir.iterdir() if path.is_file()}
        if actual != set(names) or any(digest((release_dir / name).read_bytes()) != digest(prepared[name]) for name in names):
            raise RuntimeError('existing immutable release differs; refusing overwrite')
    else:
        staging = releases / ('.stage-' + source_fingerprint[:16])
        if staging.exists():
            raise RuntimeError('previous staging directory exists; inspect it before retry')
        staging.mkdir()
        try:
            for name, payload in prepared.items():
                (staging / name).write_bytes(payload)
            for name, payload in prepared.items():
                if (staging / name).read_bytes() != payload:
                    raise RuntimeError('release readback failed: ' + name)
            staging.rename(release_dir)
        except Exception:
            # Keep the stage for inspection rather than recursively deleting files.
            raise
    # SAM | 2026-10-13 09:04 +08:00 | Record an explicit local offset because release timestamps must be auditable.
    report = {
        'status': 'READY_FOR_LUATOOLS_IMPORT',
        'created_local': datetime.now().astimezone().isoformat(timespec='seconds'),
        'source': str(source), 'release_directory': str(release_dir),
        'soc': str(soc), 'soc_sha256': soc_hash,
        'capacity_bytes': capacity, 'reserve_bytes': reserve,
        'selected_bytes': selected_bytes, 'budget_headroom_bytes': capacity - reserve - selected_bytes,
        'file_count': len(names), 'lua_count': sum(name.endswith('.lua') for name in names),
        'source_sha256': hashes, 'source_fingerprint': source_fingerprint,
        'changes_since_previous_ready': delta,
        'files': details,
        'boundary': 'This is a host import set. Luatools actual used space, module download, boot and OTA function remain unverified.'
    }
    write_json(state / 'latest_ready.json', report)
    (state / 'luatools-file-list.txt').write_text(
        '\n'.join(str(release_dir / name) for name in names) + '\n', encoding='utf-8')
    (state / 'LATEST_READY.txt').write_text(str(release_dir) + '\n', encoding='utf-8')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Offline Air780EGH Luatools release check')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--releases', type=Path, default=DEFAULT_RELEASES)
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--capacity', type=int, default=CAPACITY)
    parser.add_argument('--reserve', type=int, default=RESERVE)
    args = parser.parse_args()
    state = args.state.resolve()
    try:
        report = prepare(args.source.resolve(), args.releases.resolve(), state,
                         args.capacity, args.reserve)
    except Exception as exc:
        state.mkdir(parents=True, exist_ok=True)
        blocked = {'status': 'BLOCKED', 'reason': str(exc),
                   'source': str(args.source.resolve()),
                   'boundary': 'No new ready pointer was published; previous release was retained.'}
        write_json(state / 'last_run.json', blocked)
        print('BLOCKED:', str(exc))
        return 1
    write_json(state / 'last_run.json', report)
    print(f"READY_FOR_LUATOOLS_IMPORT: {report['release_directory']}")
    print(f"{report['file_count']} files / {report['selected_bytes']} bytes; "
          f"safe-budget headroom {report['budget_headroom_bytes']} bytes")
    for kind, names in report['changes_since_previous_ready'].items():
        print(f'{kind}: ' + (', '.join(names) if names else '(none)'))
    print('Actual Luatools used space and module download remain to be checked in Luatools.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
