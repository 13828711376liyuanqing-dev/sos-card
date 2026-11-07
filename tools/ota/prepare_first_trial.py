"""SAM | 2026-10-24 +08:00 | Stage explicit first-OTA baseline/target from current sources without changing root versions or claiming device acceptance."""
from pathlib import Path
import hashlib
import json
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
CORE = '29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec'
SOC = 'LuatOS-SoC_V2052_Air780EGH_113.soc'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def render_main(text, component, product, build, evidence):
    for name, value in [('VERSION', json.dumps(component)), ('PRODUCT_VERSION', json.dumps(product)), ('FW_RELEASE_BUILD', str(build))]:
        text, count = re.subn(r'^' + name + r'\s*=.*$', name + ' = ' + value, text, flags=re.M)
        if count != 1:
            raise ValueError('Missing or ambiguous version declaration: ' + name)
    anchor = 'require("ota_runtime").instance():observe_boot_data()'
    if text.count(anchor) != 1 or 'first_trial_profile' in text:
        raise ValueError('Unexpected boot entry; refusing duplicate injection')
    injected = '''-- SAM | 2026-10-24 +08:00 | Explicit reviewed first-test runtime, before business startup; normal root firmware remains closed.
local first_trial_profile={source='1.0.2',target='1.5.0',core_sha256='%s',evidence_sha256='%s'}
local trial_runtime=require('ota_runtime')
trial_runtime.set_instance(trial_runtime.new(require('ota_device_options').new(first_trial_profile)))
''' % (CORE, evidence)
    return text.replace(anchor, injected + anchor)

def prepare(destination):
    source = ROOT / 'Air780EGH'
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Immutable trial directory already exists')
    if sha(source / 'soc' / SOC) != CORE:
        raise ValueError('Exact core mismatch')
    files = sorted(source.glob('*.lua')) + [source / 'sample-6s.mp3']
    before = {p.name: sha(p) for p in files}
    evidence_paths = [ROOT / 'logs/ota_sequential_20261024/device_readonly/round5_acceptance.json',
                      ROOT / 'logs/ota_v2052_tool_review_20261024/result.json',
                      ROOT / 'logs/ota_readable_scope_20261024/step2_final_run_faults.txt',
                      ROOT / 'logs/ota_readable_scope_20261024/test_first_trial.py.txt',
                      ROOT / 'logs/ota_readable_scope_20261024/test_trial_wiring.py.txt',
                      # SAM | 2026-10-24 +08:00 | Bind the native JSON transport regression to the refreshed controlled candidate.
                      ROOT / 'logs/ota_readable_scope_20261024/test_platform_native_json.py.txt']
    review = dict(schema=1, purpose='FIRST_CONTROLLED_OTA_REVIEW_NOT_INSTALLATION_ACCEPTANCE',
                  source_version='1.0.2', target_version='1.5.0', cat_core_sha256=CORE,
                  native_installation_accepted=False, raw_kv_accepted=False,
                  readable_data_comparison_required=True, data_scope='readable_files_and_initialized_kv',
                  source_sha256=before, evidence={p.relative_to(ROOT).as_posix(): sha(p) for p in evidence_paths})
    raw = (json.dumps(review, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    destination.mkdir(parents=True)
    (destination / 'review.json').write_bytes(raw)
    main = (source / 'main.lua').read_text(encoding='utf-8-sig')
    for label, component, product, build in [('baseline', '001.000.002', '1.0.2', 3), ('target', '001.005.000', '1.5.0', 4)]:
        stage = destination / label / 'source'
        stage.mkdir(parents=True)
        for p in files:
            shutil.copy2(p, stage / p.name)
        (stage / 'soc').mkdir()
        shutil.copy2(source / 'soc' / SOC, stage / 'soc' / SOC)
        (stage / 'main.lua').write_text(render_main(main, component, product, build, digest), encoding='utf-8')
    if before != {p.name: sha(p) for p in files}:
        raise ValueError('Source changed during staging; do not use this trial directory')
    (destination / 'staging.json').write_text(json.dumps(dict(schema=1, review_sha256=digest,
        root_source_unchanged=True, flashed=False, installation_accepted=False), indent=2), encoding='utf-8')
    return destination

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        raise SystemExit('Usage: prepare_first_trial.py NEW_OUTPUT_DIRECTORY')
    print(prepare(sys.argv[1]))
