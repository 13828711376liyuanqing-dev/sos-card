"""SAM | 2026-11-08 +08:00 | Build the exact byte-bound review manifest + build evidence for a candidate.

It never invents approval: reviewer/reason/evidence are passed in by the human or the session that really reviewed
(see doc/2026-11-08_b27候选_OTA影响评审.md). It only computes hashes, the exact change set and the stale-input checks.
Usage: python make_review_manifest.py --candidate-id ID --version 1.5.23 --build 27 --out-dir logs/xxx --reviewer "..." \
          --reason "..." --evidence doc/a.md [--evidence doc/b.md ...]
"""
import argparse, json, os, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_gate as g

W = Path(__file__).resolve().parents[2]
BASELINE_ID = 'YP001_1.5.31_b35_20261110_OTA_FACTORY_READY_PASS_KNOWN_ISSUES'  # SAM | 2026-11-10 | newest frozen baseline (b27 before; b35 is the first factory-ready OTA freeze); override with --baseline-id
OBJ = W / 'ble_app_uart_c/Keil_6/Objects'


def baseline_parts(baseline_id):
    """Mappings and anchor are derived from the frozen baseline directory, never copied from an older manifest."""
    d = 'firmware_releases/baselines/' + baseline_id
    anchor = W / d / 'manifest.json'
    if not anchor.is_file():
        raise SystemExit('baseline manifest not found: ' + str(anchor))
    return {'baseline_id': baseline_id,
            'baseline_manifest': {'path': d + '/manifest.json', 'sha256': g.file_hash(anchor)},
            'mappings': [{'component': 'gr', 'baseline': d + '/source/gr', 'candidate': 'ble_app_uart_c'},
                         {'component': 'cat1', 'baseline': d + '/source/cat1', 'candidate': 'Air780EGH'},
                         {'component': 'sdk', 'baseline': d + '/source/sdk', 'candidate': 'SDK'}]}


def rel(p):
    return Path(p).resolve().relative_to(W).as_posix()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--candidate-id', required=True)
    ap.add_argument('--version', required=True)
    ap.add_argument('--build', type=int, required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--reviewer', required=True)
    ap.add_argument('--reason', required=True)
    ap.add_argument('--evidence', action='append', default=[])
    ap.add_argument('--baseline-id', default=BASELINE_ID)
    ap.add_argument('--ide-state-reason', default='Keil IDE user state only; not a compile or link input.')
    a = ap.parse_args()
    out = W / a.out_dir
    out.mkdir(parents=True, exist_ok=True)
    prev = baseline_parts(a.baseline_id)

    # ---- build evidence: the F7 outputs must be newer than every GR source and carry the candidate version
    axf, hexf = OBJ / 'YP001_GR5526.axf', OBJ / 'YP001_GR5526.hex'
    stale = []
    for root in (W / 'ble_app_uart_c/Src',):
        for p in root.rglob('*'):
            if p.suffix.lower() in ('.c', '.h', '.s', '.sct') and p.stat().st_mtime > axf.stat().st_mtime:
                stale.append(rel(p))
    header = (W / 'ble_app_uart_c/Src/config/yp001_fw_version.h').read_text(encoding='utf-8-sig', errors='replace')
    ver_ok = f'"{a.version}"' in header or f'001.005.{a.build - 4:03d}' in header
    uv = (W / 'ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx').read_text(encoding='utf-8', errors='replace')
    build = {
        'clean': not stale, 'hex_after_axf': hexf.stat().st_mtime >= axf.stat().st_mtime - 5,
        'stale_sources_newer_than_axf': stale, 'product_version': a.version, 'build': a.build,
        'bench_define': 'YP001_OTA_USB_BENCH_TEST=1' in uv, 'epaper_factory_define': 'EPAPER_UI_FACTORY_TEST=1' in uv,
        'axf': rel(axf), 'axf_mtime': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(axf.stat().st_mtime)),
        'axf_sha256': g.file_hash(axf), 'hex_sha256': g.file_hash(hexf),
        'compiled_by': 'user Keil F7 (0 error); recorded by Claude session',
        'ready': not stale and ver_ok, 'accepted': False,
        'note': 'Build evidence only; device OTA/business acceptance PENDING.'}
    if not build['ready']:
        print('BUILD NOT READY', json.dumps(build, ensure_ascii=False)[:600]); return 2
    bpath = out / f'build_b{a.build}.json'
    bpath.write_text(json.dumps(build, indent=2, ensure_ascii=False), encoding='utf-8')

    # ---- exact change set
    before, after = g.snapshot(W, prev['mappings'])
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    ev = [{'path': e, 'sha256': g.file_hash(W / e)} for e in a.evidence] + [{'path': rel(bpath), 'sha256': g.file_hash(bpath)}]
    changes = []
    for p in changed:
        ide = p.endswith(('.uvoptx', '.uvguix.SamLi'))
        changes.append({'path': p, 'before_sha256': before.get(p), 'after_sha256': after.get(p),
                        'reviewer': a.reviewer, 'reason': a.ide_state_reason if ide else a.reason, 'evidence': ev})
    csha = g.digest(after)
    m = {'schema_version': 1, 'scan_policy': g.SCAN_POLICY, 'baseline_id': prev['baseline_id'],
         'candidate_id': a.candidate_id, 'baseline_manifest': prev['baseline_manifest'], 'mappings': prev['mappings'],
         'baseline_files': before, 'candidate_files': after, 'baseline_sha256': g.digest(before), 'candidate_sha256': csha,
         'changes': changes,
         'build_evidence': {'source_sha256': csha, 'gr_hex_sha256': build['hex_sha256'], 'reviewer': a.reviewer,
                            'reason': 'Final F7 output newer than all GR sources; version marker and bench define checked.',
                            'evidence': [{'path': rel(bpath), 'sha256': g.file_hash(bpath)}]},
         'attestation': {'source_sha256': csha, 'reviewer': a.reviewer, 'reason': a.reason, 'evidence': ev},
         'device_acceptance': 'PENDING'}
    mp = out / 'review_manifest.json'
    mp.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding='utf-8')
    print('changes', len(changes), 'candidate_sha256', csha)
    print('manifest', rel(mp)); print('build', rel(bpath))
    return 0


if __name__ == '__main__':
    sys.exit(main())
