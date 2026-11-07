"""SAM | 2026-10-12 19:40 +08:00 | Verify synchronized inputs and parse Lua without target execution."""
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua54 import LuaRuntime

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

before = json.loads((ROOT / 'logs/ota_impl_20261012/before.json').read_text(encoding='utf-8-sig'))
changed = []
for name, old_hash in before['files'].items():
    path = ROOT / name
    if not path.exists() or digest(path) != old_hash:
        changed.append(name)
for directory, pattern in [('Air780EGH', 'ota_*.lua'), ('ble_app_uart_c/Src/user/ota', '*')]:
    for path in (ROOT / directory).glob(pattern):
        if path.is_file() and str(path.relative_to(ROOT)) not in before['files']:
            changed.append(str(path.relative_to(ROOT)))

copies = []
for name in changed:
    if name.startswith('ble_app_uart_c\\') or name.startswith('SDK\\'):
        main = ROOT / name
        delivery = ROOT / 'SVN交付_YP001_GR5526_20261001' / name
        if not delivery.exists() or digest(main) != digest(delivery):
            raise AssertionError(f'delivery mismatch: {name}')
        copies.append(name)

lua = LuaRuntime(unpack_returned_tuples=True)
parse = lua.eval('function(s,n) local f,e=load(s,n); return f~=nil,e end')
files = sorted((ROOT / 'Air780EGH').glob('*.lua'))
for path in files:
    ok, error = parse(path.read_text(encoding='utf-8-sig'), path.name)
    if not ok:
        raise AssertionError(f'{path.name}: {error}')
result = {'changed_from_snapshot': sorted(set(changed)), 'synchronized_inputs': copies,
          'lua_syntax_files': len(files), 'scope': 'source/host only; no hardware writes'}
(ROOT / 'logs/ota_impl_20261012/source_verification.json').write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'PASS {len(files)} Lua syntax files; {len(copies)} synchronized firmware inputs')
