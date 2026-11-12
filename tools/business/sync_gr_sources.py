"""SAM | 2026-10-13 09:02 +08:00 | Synchronize only reviewed files because delivery settings and unrelated work must be preserved."""
from pathlib import Path
import hashlib, json, shutil
root=Path(__file__).resolve().parents[2]
main=root/'ble_app_uart_c'
delivery=root/'SVN交付_YP001_GR5526_20261001/ble_app_uart_c'
backup=root/'logs/business_20261013/before'
files=['Src/platform/bsp.c','Src/platform/user_periph_setup.c','Src/platform/user_periph_setup.h',
       'Src/user/epaper_depg0150.c','Src/user/gui/epaper_ui.c','Src/user/gui/epaper_ui.h',
       'Src/user/gui/epaper_lvgl.c','Src/external/lvgl_8.3.1/lv_conf.h',
       'Src/user/business/yp001_business.c','Src/user/business/yp001_business.h','GCC/Makefile']
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
manifest_path=root/'logs/business_20261013/gr_source_manifest.json'
previous={item['path']:item['sha256'] for item in json.loads(manifest_path.read_text())} if manifest_path.exists() else {}
# Validate EVERY target before the first mutation.
for rel in files:
    source,target=main/rel,delivery/rel
    if not source.exists(): raise RuntimeError('Missing source '+rel)
    if target.exists() and sha(target)!=sha(source):
        prior=backup/'ble_app_uart_c'/rel
        # Accept only original baseline or the exact last verified delivery hash.
        if (not prior.exists() or sha(prior)!=sha(target)) and previous.get(rel)!=sha(target):
            raise RuntimeError('Independent delivery change; refuse overwrite: '+rel)
manifest=[]
for rel in files:
    source,target=main/rel,delivery/rel
    if target.exists():
        prior=backup/'SVN交付_YP001_GR5526_20261001/ble_app_uart_c'/rel
        if not prior.exists():
            prior.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(target,prior)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    assert sha(source)==sha(target)
    manifest.append({'path':rel,'sha256':sha(source),'delivery_identical':True})
(root/'logs/business_20261013/gr_source_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(f'PASS: {len(files)} specific source/config files identical; independent Keil settings preserved')
