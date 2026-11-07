"""SAM | 2026-10-28 18:40 +08:00 | Read-only post-download acceptance for the motion-sampling paired delivery: exact A/Boot bytes, PREPARED gen3->gen4 rebind to the new A, and no other protected/user page change."""
from pathlib import Path
import hashlib, json, struct, sys, zlib

R = Path(__file__).resolve().parents[2]
OUT = R / 'firmware_releases/gr_motion_sampling_20261028'
AUDIT = R / 'logs/motion_sampling_delivery_20261028'


def records(snap):
    out = []
    for page in (0xF7000, 0xF8000):
        rec = snap[page:page + 124]; w = struct.unpack('<31I', rec)
        if w[0] == 0x59504231 and w[29] == zlib.crc32(rec[:116]) and w[30] == 0:
            out.append((w[1], page, rec, w))
    return sorted(out)


def main(after):
    pre = (AUDIT / 'pre_flash_2.bin').read_bytes(); post = Path(after).read_bytes()
    app = (OUT / 'baseline/baseline_signed.bin').read_bytes(); boot = (OUT / 'boot/BOOT_BOUND.bin').read_bytes()
    m = json.loads((OUT / 'paired_downloads.json').read_text())
    a_end = 0x2000 + len(app); b_end = 0xEC000 + len(boot)
    res = {'a_exact': post[0x2000:a_end] == app, 'boot_exact': post[0xEC000:b_end] == boot}
    gen = records(post); top = gen[-1]
    desc = bytes.fromhex(m['new_descriptor_hex'])
    res['latest_generation'] = top[0]; res['latest_state'] = top[3][3]
    res['latest_index_stage_attempts'] = list(top[3][4:7])
    res['latest_old_is_new_app'] = top[2][28:68] == desc
    res['latest_candidate_unchanged'] = top[2][68:108] == bytes.fromhex(m['new_scope_hex'])[108:148]
    # Pages allowed to differ: A sectors written, Boot sectors written, and exactly one journal page.
    allowed = set(range(0x2000 // 4096, (a_end + 4095) // 4096)) | set(range(0xEC000 // 4096, (b_end + 4095) // 4096))
    changed = [i for i in range(256) if pre[i * 4096:(i + 1) * 4096] != post[i * 4096:(i + 1) * 4096]]
    other = [hex(0x200000 + i * 4096) for i in changed if i not in allowed]
    res['changed_outside_a_boot'] = other
    res['owner_pages_unchanged'] = pre[0xF9000:0xFB000] == post[0xF9000:0xFB000]
    res['candidate_b_unchanged'] = pre[0x80000:0xEC000] == post[0x80000:0xEC000]
    res['nvds_unchanged'] = pre[0xFE000:] == post[0xFE000:]
    # SAM | 2026-10-28 18:45 +08:00 | The flash algorithm refreshes SCA word1 (Boot byte-sum checksum, word0=Boot length) when Boot bytes change; ROM needs it. Allow only that word and only the exact new sum.
    sca_ok = (pre[:4] == post[:4] and pre[8:0x2000] == post[8:0x2000] and struct.unpack_from('<I', post, 0)[0] == len(boot)
              and struct.unpack_from('<I', post, 4)[0] == sum(boot))
    res['sca_only_boot_checksum_updated'] = sca_ok
    if sca_ok and '0x200000' in other: other.remove('0x200000')
    res['sca_unchanged'] = sca_ok
    res['pass'] = (res['a_exact'] and res['boot_exact'] and top[0] == 4 and top[3][3] == 1 and list(top[3][4:7]) == [0, 0, 0]
                   and res['latest_old_is_new_app'] and res['latest_candidate_unchanged'] and len(other) == 1
                   and other[0] in ('0x2f7000', '0x2f8000') and res['owner_pages_unchanged'] and res['candidate_b_unchanged']
                   and res['nvds_unchanged'] and res['sca_unchanged'])
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
