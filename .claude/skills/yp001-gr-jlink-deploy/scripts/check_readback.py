"""SAM | 2026-10-28 18:55 +08:00 | Generic read-only post-download acceptance (generalized from tools/ota/check_motion_sampling_readback.py): exact A/Boot bytes, PREPARED gen+1 rebind to the new A, SCA only Boot checksum, no other protected/user page change.

Usage: python check_readback.py --out firmware_releases/<new> --pre logs/<round>/pre_flash_2.bin --post logs/<round>/post_flash_1.bin
"""
from pathlib import Path
import argparse, json, struct, zlib

R = Path(__file__).resolve().parents[4]


def latest(snap):
    best = None
    for page in (0xF7000, 0xF8000):
        rec = snap[page:page + 124]; w = struct.unpack('<31I', rec)
        if w[0] == 0x59504231 and w[29] == zlib.crc32(rec[:116]) and w[30] == 0 and (not best or w[1] > best[1][1]): best = (rec, w)
    return best


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--pre', required=True); ap.add_argument('--post', required=True)
    a = ap.parse_args(); out = R / a.out
    pre = (R / a.pre).read_bytes(); post = (R / a.post).read_bytes()
    app = (out / 'baseline/baseline_signed.bin').read_bytes(); boot = (out / 'boot/BOOT_BOUND.bin').read_bytes()
    m = json.loads((out / 'paired_downloads.json').read_text())
    a_end = 0x2000 + len(app); b_end = 0xEC000 + len(boot)
    rec, w = latest(post); desc = bytes.fromhex(m['new_descriptor_hex'])
    res = {'a_exact': post[0x2000:a_end] == app, 'boot_exact': post[0xEC000:b_end] == boot,
           'latest_generation': w[1], 'expected_generation': m['next_prepared_generation'], 'latest_state_prepared': w[3] == 1,
           'index_stage_attempts_zero': list(w[4:7]) == [0, 0, 0], 'latest_old_is_new_app': rec[28:68] == desc,
           'latest_candidate_unchanged': rec[68:108] == bytes.fromhex(m['new_scope_hex'])[108:148]}
    allowed = set(range(0x2000 // 4096, (a_end + 4095) // 4096)) | set(range(0xEC000 // 4096, (b_end + 4095) // 4096))
    other = [hex(0x200000 + i * 4096) for i in range(256) if pre[i * 4096:(i + 1) * 4096] != post[i * 4096:(i + 1) * 4096] and i not in allowed]
    # The flash algorithm refreshes SCA word1 (Boot byte-sum; word0 = Boot length) when Boot changes. ROM needs it.
    sca_ok = (pre[:4] == post[:4] and pre[8:0x2000] == post[8:0x2000] and struct.unpack_from('<I', post, 0)[0] == len(boot)
              and struct.unpack_from('<I', post, 4)[0] == sum(boot))
    if sca_ok and '0x200000' in other: other.remove('0x200000')
    res.update({'sca_only_boot_checksum_updated': sca_ok, 'changed_outside_a_boot': other,
                'owner_pages_unchanged': pre[0xF9000:0xFB000] == post[0xF9000:0xFB000],
                'candidate_b_unchanged': pre[0x80000:0xEC000] == post[0x80000:0xEC000], 'nvds_unchanged': pre[0xFE000:] == post[0xFE000:]})
    res['pass'] = (res['a_exact'] and res['boot_exact'] and w[1] == m['next_prepared_generation'] and res['latest_state_prepared']
                   and res['index_stage_attempts_zero'] and res['latest_old_is_new_app'] and res['latest_candidate_unchanged'] and sca_ok
                   and len(other) == 1 and other[0] in ('0x2f7000', '0x2f8000') and res['owner_pages_unchanged']
                   and res['candidate_b_unchanged'] and res['nvds_unchanged'])
    print(json.dumps(res, indent=2))
    raise SystemExit(0 if res['pass'] else 1)


if __name__ == '__main__':
    main()
