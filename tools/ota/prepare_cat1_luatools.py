"""SAM | 2026-10-13 +08:00 | Prepare an explicit Luatools file set without touching product sources or user data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Air780EGH'
OUTPUT = ROOT / 'logs/cat1_luatools_20261013/package'
SPACE = 512 * 1024
PY_DEPS = ROOT / 'logs/cat1_antenna_20261010/python_deps'
sys.path.insert(0, str(PY_DEPS))
from lupa.lua54 import LuaRuntime


def marker(source: str, pos: int, left: str) -> int | None:
    if pos >= len(source) or source[pos] != left:
        return None
    idx = pos + 1
    while idx < len(source) and source[idx] == '=':
        idx += 1
    if idx < len(source) and source[idx] == '[':
        return idx - pos - 1
    return None


def strip_comments(source: str) -> str:
    """Replace Lua comments with whitespace, preserving all source tokens and line breaks."""
    out = []
    idx = 0
    while idx < len(source):
        char = source[idx]
        long_equals = marker(source, idx, '[')
        if long_equals is not None:
            end_marker = ']' + '=' * long_equals + ']'
            close = source.find(end_marker, idx + long_equals + 2)
            if close < 0:
                raise ValueError('unclosed Lua long string')
            end = close + len(end_marker)
            out.append(source[idx:end])
            idx = end
        elif char in "\"'":
            end = idx + 1
            while end < len(source):
                if source[end] == '\\':
                    end += 2
                elif source[end] == char:
                    end += 1
                    break
                else:
                    end += 1
            else:
                raise ValueError('unclosed Lua quoted string')
            out.append(source[idx:end])
            idx = end
        elif source.startswith('--', idx):
            equals = marker(source, idx + 2, '[')
            if equals is not None:
                end_marker = ']' + '=' * equals + ']'
                close = source.find(end_marker, idx + equals + 4)
                if close < 0:
                    raise ValueError('unclosed Lua long comment')
                end = close + len(end_marker)
            else:
                end = source.find('\n', idx)
                if end < 0:
                    end = len(source)
            removed = source[idx:end]
            out.append(' ' + ''.join(char for char in removed if char in '\r\n'))
            idx = end
        else:
            out.append(char)
            idx += 1
    return ''.join(out)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    lua = LuaRuntime(unpack_returned_tuples=True)
    compile_lua = lua.eval('function(s,n) local f,e=load(s,n); return f~=nil,e end')
    files = []
    # SAM | 2026-10-13 +08:00 | Freeze this OTA handoff set because other independent user work may appear in the same source directory.
    before = json.loads((ROOT / 'logs/ota_impl_20261012/before.json').read_text(encoding='utf-8'))
    original_names = {Path(name).name for name in before['files']
                      if name.replace('\\', '/').startswith('Air780EGH/') and name.endswith('.lua')}
    selected_names = original_names | {f'ota_{name}.lua' for name in
                                      ('store', 'manager', 'download', 'runtime', 'platform')}
    # SAM | 2026-10-13 +08:00 | Follow newly referenced local modules so a changing main.lua cannot yield an incomplete package.
    require_pattern = re.compile(r'''\brequire\s*(?:\(\s*)?["']([A-Za-z_][A-Za-z_0-9.]*)["']''')
    checked = set()
    while checked != selected_names:
        name = sorted(selected_names - checked)[0]
        path = SOURCE / name
        if not path.is_file():
            raise FileNotFoundError(f'missing required Lua file: {path}')
        for module in require_pattern.findall(path.read_text(encoding='utf-8-sig')):
            local = SOURCE / (module.replace('.', '/') + '.lua')
            if local.is_file() and local.parent == SOURCE:
                selected_names.add(local.name)
        checked.add(name)
    unexpected_names = sorted({path.name for path in SOURCE.glob('*.lua')} - selected_names)
    for name in sorted(selected_names):
        path = SOURCE / name
        if not path.is_file():
            raise FileNotFoundError(f'missing required Lua file: {path}')
        text = path.read_text(encoding='utf-8-sig')
        compact = strip_comments(text)
        for label, content in [('source', text), ('package', compact)]:
            valid, error = compile_lua(content, path.name)
            if not valid:
                raise RuntimeError(f'{path.name} {label} syntax: {error}')
        target = OUTPUT / path.name
        target.write_text(compact, encoding='utf-8', newline='\n')
        files.append({'name': path.name, 'type': 'lua', 'source_bytes': path.stat().st_size,
                      'package_bytes': target.stat().st_size,
                      'source_sha256': sha(path), 'package_sha256': sha(target)})
    for item in files:
        if sha(SOURCE / item['name']) != item['source_sha256']:
            raise RuntimeError(f'source changed while preparing: {item["name"]}')
    audio = SOURCE / 'sample-6s.mp3'
    audio_target = OUTPUT / audio.name
    shutil.copy2(audio, audio_target)
    files.append({'name': audio.name, 'type': 'audio', 'source_bytes': audio.stat().st_size,
                  'package_bytes': audio_target.stat().st_size, 'source_sha256': sha(audio),
                  'package_sha256': sha(audio_target), 'source_path': str(audio)})
    generated = {path.name for path in OUTPUT.iterdir() if path.is_file()}
    expected = {item['name'] for item in files}
    if generated != expected:
        raise RuntimeError(f'package file list changed; extra={sorted(generated-expected)}, missing={sorted(expected-generated)}')
    for item in files:
        if (sha(SOURCE / item['name']) != item['source_sha256'] or
                sha(OUTPUT / item['name']) != item['package_sha256']):
            raise RuntimeError(f'source/package changed while preparing: {item["name"]}')
    lua_bytes = sum(f['package_bytes'] for f in files if f['type'] == 'lua')
    total_bytes = sum(f['package_bytes'] for f in files)
    manifest = {'soc': str(SOURCE / 'soc/LuatOS-SoC_V2052_Air780EGH_113.soc'),
                'script_directory': str(OUTPUT), 'audio_path': str(audio_target),
                'other_source_lua_excluded': unexpected_names,
                'lua_count': len(files) - 1, 'lua_bytes': lua_bytes,
                'total_selected_bytes': total_bytes, 'reported_capacity_bytes': SPACE,
                'raw_headroom_bytes': SPACE - total_bytes,
                'files': files,
                'limit': 'Raw byte comparison only; Luatools compilation and device free space are unverified.'}
    manifest_path = OUTPUT.parent / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUTPUT.parent / 'luatools-file-list.txt').write_text(
        '\n'.join(str(OUTPUT / f['name']) for f in files) + '\n', encoding='utf-8')
    print(f"{len(files)-1} Lua files, {lua_bytes} Lua bytes; with audio {total_bytes} bytes; "
          f"raw headroom {SPACE-total_bytes} bytes")
    if unexpected_names:
        print('Excluded independent files: ' + ', '.join(unexpected_names))
    print(f'Package: {OUTPUT}')
    print(f'Manifest: {manifest_path}')


if __name__ == '__main__':
    main()
