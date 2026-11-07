"""SAM | 2026-10-28 18:20 +08:00 | Decode a read-only 1MiB GR flash snapshot against the last delivered app/Boot because a new paired download must bind the live PREPARED journal and owner pages exactly."""
from pathlib import Path
import hashlib, json, struct, sys, zlib

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = ROOT / 'firmware_releases/gr_query_readonly_20261027'
JOURNALS = (0xF7000, 0xF8000)
SCOPE_AT = 0x2F30C8 - 0x2EC000


def journal_records(snap):
    out = []
    for page in JOURNALS:
        for off in range(0, 4096, 124):
            rec = snap[page + off:page + off + 124]
            if len(rec) < 124: break
            w = struct.unpack('<31I', rec)
            if w[0] != 0x59504231: continue
            ok = w[29] == zlib.crc32(rec[:116]) and w[30] == 0
            out.append({'page': hex(0x200000 + page), 'offset': off, 'generation': w[1], 'state': w[3], 'index': w[4],
                        'stage': w[5], 'attempts': w[6], 'valid': ok, 'old_desc': rec[28:68].hex(), 'new_desc': rec[68:108].hex(),
                        'raw': rec.hex()})
    return out


def main(path):
    snap = Path(path).read_bytes(); assert len(snap) == 0x100000
    app = (PREVIOUS / 'baseline/baseline_signed.bin').read_bytes()
    boot = (PREVIOUS / 'boot/BOOT_BOUND.bin').read_bytes()
    q_desc = struct.pack('<II', len(app) - 904, 1000002) + hashlib.sha256(app[:-904]).digest()
    recs = journal_records(snap); valid = [r for r in recs if r['valid']]
    latest = max(valid, key=lambda r: r['generation']) if valid else None
    old_scope = boot[SCOPE_AT:SCOPE_AT + 148]
    result = {
        'snapshot_sha256': hashlib.sha256(snap).hexdigest(),
        'a_matches_previous_signed_app': snap[0x2000:0x2000 + len(app)] == app,
        'boot_matches_previous_paired_boot': snap[0xEC000:0xEC000 + len(boot)] == boot,
        'previous_app_sha256': hashlib.sha256(app).hexdigest(),
        'previous_app_descriptor': q_desc.hex(),
        'owner_pages_sha256': hashlib.sha256(snap[0xF9000:0xFB000]).hexdigest(),
        'candidate_native_sha256_432328': hashlib.sha256(snap[0x80000:0x80000 + 432328]).hexdigest(),
        'nvds_sha256': hashlib.sha256(snap[0xFE000:0x100000]).hexdigest(),
        'journal_records': [{k: v for k, v in r.items() if k != 'raw'} for r in recs],
        'latest': {k: v for k, v in latest.items() if k != 'raw'} if latest else None,
        'latest_old_is_previous_app': bool(latest and latest['old_desc'] == q_desc.hex()),
        'boot_scope_in_previous_boot': {'version': struct.unpack_from('<I', old_scope)[0], 'owner': old_scope[4:36].hex(),
                                        'candidate': old_scope[36:68].hex(), 'old_desc': old_scope[68:108].hex(), 'cand_desc': old_scope[108:148].hex()},
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
