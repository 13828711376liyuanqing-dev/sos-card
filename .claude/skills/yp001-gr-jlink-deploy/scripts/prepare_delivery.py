"""SAM | 2026-10-28 18:55 +08:00 | Generic GR paired-delivery preparation (generalized from tools/ota/prepare_motion_sampling_delivery.py) because every app change must be signed and rebound to the live Boot journal. Never compiles firmware or touches hardware.

Usage (Python 3.11, needs `cryptography`):
  python prepare_delivery.py --previous firmware_releases/<last_delivery> --out firmware_releases/<new> \
      --audit logs/<new_round> --frozen <previous frozen_inputs.json> --snapshot logs/<new_round>/pre_flash_2.bin \
      --allow ble_app_uart_c/Src/user/a.c --allow ...
"""
from pathlib import Path
import argparse, hashlib, json, re, shutil, struct, sys, zlib

R = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(R / 'tools/ota'))
import pair_gr_adc_resync_build as pair  # noqa: E402  (signing, carrier and Boot descriptor rebind)

# SAM | 2026-10-28 19:15 +08:00 | Keil_6 now keeps one project: the verified UART_RECOVERY project renamed to YP001_GR5526.uvprojx (same content/output dir). pair_* still names the old file, so point it here explicitly.
pair.PROJECT = R / 'ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx'
SCOPE_AT = 0x2F30C8 - 0x2EC000
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_build(frozen_path, allowed, audit):
    frozen = json.loads(Path(frozen_path).read_text())['dependencies']
    deps, stale = {}, []
    for dep in pair.OBJECTS.glob('*.d'):
        obj = dep.with_suffix('.o')
        if not obj.exists(): continue
        text = dep.read_text(errors='replace').partition(': ')[2].replace('\\\n', ' ')
        for token in re.findall(r'"[^\"]+"|(?:\\ |[^\s])+', text):
            token = token.strip('"').replace('\\ ', ' ')
            if token == '\\': continue
            p = Path(token); p = (p if p.is_absolute() else pair.PROJECT.parent / p).resolve()
            assert p.is_file(), 'DEPENDENCY_MISSING: ' + str(p)
            deps.setdefault(str(p), sha(p))
            if p.stat().st_mtime > obj.stat().st_mtime: stale.append(obj.name)
    changed = sorted(p for p, d in deps.items() if frozen.get(p) != d)
    assert set(changed) == allowed, ('UNEXPECTED_INPUT_SET: review and pass every changed file with --allow', changed)
    axf, hexf = pair.OBJECTS / 'YP001_GR5526.axf', pair.OBJECTS / 'YP001_GR5526.hex'
    linked = max(p.stat().st_mtime for p in pair.OBJECTS.glob('*.o')) <= axf.stat().st_mtime
    clean = '0 Error(s), 0 Warning(s)' in (pair.OBJECTS / 'YP001_GR5526.build_log.htm').read_text(errors='replace')
    ready = not stale and linked and clean and hexf.stat().st_mtime >= axf.stat().st_mtime
    audit.mkdir(parents=True, exist_ok=True)
    (audit / 'build_acceptance.json').write_text(json.dumps({'ready': ready, 'stale': sorted(set(stale)), 'changed_inputs': changed,
        'dependencies': len(deps), 'axf_sha256': sha(axf), 'hex_sha256': sha(hexf), 'device_written': False}, indent=2))
    return ready, deps


def live_scope(previous, snapshot):
    snap = Path(snapshot).read_bytes(); assert len(snap) == 0x100000
    app = (previous / 'baseline/baseline_signed.bin').read_bytes(); boot = (previous / 'boot/BOOT_BOUND.bin').read_bytes()
    assert snap[0x2000:0x2000 + len(app)] == app and snap[0xEC000:0xEC000 + len(boot)] == boot, 'LIVE_NOT_PREVIOUS_DELIVERY'
    best = None
    for page in (0xF7000, 0xF8000):
        rec = snap[page:page + 124]; w = struct.unpack('<31I', rec)
        if w[0] == 0x59504231 and w[29] == zlib.crc32(rec[:116]) and w[30] == 0 and (not best or w[1] > best[1][1]): best = (rec, w)
    assert best, 'NO_VALID_BOOT_JOURNAL'
    j, w = best; gen = w[1]
    assert w[3:7] == (1, 0, 0, 0), 'STOP: latest journal is not a clean PREPARED record; this procedure only rebinds PREPARED'
    desc = struct.pack('<II', len(app) - 904, 1000002) + hashlib.sha256(app[:-904]).digest()
    assert j[28:68] == desc, 'LATEST_OLD_IMAGE_NOT_LIVE_A'
    old = boot[SCOPE_AT:SCOPE_AT + 148]
    owner = hashlib.sha256(snap[0xF9000:0xFB000]).digest()
    cand = old[36:68]; size = struct.unpack_from('<I', j, 68)[0] + 904
    assert hashlib.sha256(snap[0x80000:0x80000 + size]).digest() == cand, 'B_CANDIDATE_CHANGED'
    assert struct.unpack_from('<I', old)[0] == gen - 1 and old[108:148] == j[68:108], 'PREVIOUS_SCOPE_NOT_CHAINED_TO_LIVE_JOURNAL'
    assert old[4:36] == owner, 'STOP: owner pages changed since last delivery; Boot would refuse start with a stale owner hash. Investigate first.'
    new = struct.pack('<I', gen) + owner + cand + j[28:108]
    patched = boot[:SCOPE_AT] + new + boot[SCOPE_AT + 148:]
    return patched, desc, {'scope_data_offset': SCOPE_AT, 'old_scope_hex': old.hex(), 'new_scope_hex': new.hex(),
        'expected_prepared_generation': gen, 'next_prepared_generation': gen + 1, 'owner_pages_sha256': owner.hex(),
        'candidate_sha256': cand.hex(), 'snapshot_sha256': hashlib.sha256(snap).hexdigest(), 'boot_code_changed': False}


def main():
    ap = argparse.ArgumentParser()
    for k in ('--previous', '--out', '--audit', '--frozen', '--snapshot'): ap.add_argument(k, required=True)
    ap.add_argument('--allow', action='append', default=[])
    a = ap.parse_args()
    previous, out, audit = (R / a.previous).resolve(), (R / a.out).resolve(), (R / a.audit).resolve()
    allowed = {str((R / x).resolve()) for x in a.allow}
    ready, deps = check_build(R / a.frozen, allowed, audit); assert ready, 'AWAIT_MATCHING_BUILD'
    patched, desc, scope = live_scope(previous, R / a.snapshot)
    prev = audit / 'pair_input'; assert not prev.exists() and not out.exists(), 'PRESERVE_PRIOR_OUTPUT'
    (prev / 'boot').mkdir(parents=True); (prev / 'baseline/SIGNED_DOWNLOAD').mkdir(parents=True)
    (prev / 'boot/BOOT_BOUND.bin').write_bytes(patched)
    at = json.loads((previous / 'paired_downloads.json').read_text())['provision_offset']
    assert patched[at:at + 40] == desc and at != SCOPE_AT + 68
    (prev / 'paired_downloads.json').write_text(json.dumps({'provision_offset': at, 'boot_sha256': hashlib.sha256(patched).hexdigest(), 'new_descriptor_hex': desc.hex()}))
    for ext in ('.uvprojx', '.uvoptx'):
        name = 'DOWNLOAD_SIGNED_APP_ONLY' + ext; shutil.copy2(previous / 'baseline/SIGNED_DOWNLOAD' / name, prev / 'baseline/SIGNED_DOWNLOAD' / name)
    pair.PREVIOUS = prev; pair.OUT = out; pair.AUDIT = audit; pair.check_build = lambda: (ready, deps); sys.argv = sys.argv[:1]; pair.main()
    manifest = json.loads((out / 'paired_downloads.json').read_text())
    final = (out / 'boot/BOOT_BOUND.bin').read_bytes(); original = (previous / 'boot/BOOT_BOUND.bin').read_bytes()
    assert len(final) == len(original)
    for i, (x, y) in enumerate(zip(original, final)):
        if x != y: assert SCOPE_AT <= i < SCOPE_AT + 148 or at <= i < at + 40, 'BOOT_CODE_CHANGED'
    new_desc = bytes.fromhex(manifest['new_descriptor_hex']); assert final[at:at + 40] == new_desc and new_desc != desc
    manifest.update(scope); manifest.update({'only_boot_scope_and_baseline_data_changed': True, 'device_written': False, 'new_ota_trial': False})
    (out / 'paired_downloads.json').write_text(json.dumps(manifest, indent=2))
    # Freeze this build's full input hashes so the next round can prove exactly which sources changed.
    (out / 'frozen_inputs.json').write_text(json.dumps({'dependencies': deps}, indent=2))
    print('PASS', json.dumps({k: manifest[k] for k in ('app_bytes', 'slot_spare', 'app_sha256', 'boot_sha256', 'next_prepared_generation', 'projects')}, indent=1))


if __name__ == '__main__':
    main()
