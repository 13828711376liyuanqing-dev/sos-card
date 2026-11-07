"""SAM | 2026-10-13 +08:00 | Check the selected Luatools files still match the current CAT1 sources."""
from pathlib import Path
import hashlib
import json

from prepare_cat1_luatools import ROOT, SOURCE, OUTPUT, strip_comments


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest = json.loads((OUTPUT.parent / 'manifest.json').read_text(encoding='utf-8'))
selected = {item['name'] for item in manifest['files']}
actual = {path.name for path in OUTPUT.iterdir() if path.is_file()}
assert selected == actual, (selected - actual, actual - selected)
assert len(selected) == manifest['lua_count'] + 1
assert sum((OUTPUT / name).stat().st_size for name in selected) == manifest['total_selected_bytes']

for item in manifest['files']:
    source = SOURCE / item['name']
    package = OUTPUT / item['name']
    assert source.is_file() and digest(source) == item['source_sha256'], item['name'] + ' source changed'
    assert digest(package) == item['package_sha256'], item['name'] + ' package changed'
    if item['type'] == 'lua':
        assert strip_comments(source.read_text(encoding='utf-8-sig')) == package.read_text(encoding='utf-8'), item['name']
    else:
        assert source.read_bytes() == package.read_bytes(), item['name']

print(f"PASS {manifest['lua_count']} Lua and audio: exact comment-only transform; "
      f"{manifest['total_selected_bytes']} selected bytes, "
      f"{manifest['raw_headroom_bytes']} raw bytes under recorded 512 KiB")
