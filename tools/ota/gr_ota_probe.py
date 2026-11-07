"""SAM | 2026-11-06 +08:00 | Preserve raw OTA evidence and decode offline because a heuristic SRAM match is not a confirmed symbol.
Live capture retains owner.bin/journal.bin/sram.bin in a NEW --output-dir; no explicit reset/halt/write commands.
Offline: --offline-dir DIR [--install-error-address 0x20000000 --firmware-provenance 'matching b16 map ...'].
Address provenance is user supplied, not independently verified by this tool. Snapshot reads are not atomic."""
import argparse
import json
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

JLINK = r'C:\Program Files\SEGGER\JLink\JLink.exe'
PHASE = ['IDLE', 'DOWNLOADING', 'PREPARED', 'INSTALL_PENDING', 'COMPLETE']
BOOT = {0: 'EMPTY', 1: 'PREPARED', 2: 'INSTALL', 3: 'TRIAL', 4: 'ROLLBACK', 5: 'CONFIRMED', 6: 'REVERTED'}
STAGE = {1: 'owner not INSTALL_PENDING', 2: 'boot open', 3: 'validation receipt missing', 4: 'boot generation changed',
         5: 'boot images changed', 6: 'commit gates', 7: 'boot activate', 10: 'prevalidation owner/progress/boot',
         11: 'running image/source version', 12: 'candidate image validation', 13: 'prevalidation owner changed',
         14: 'flash lease active', 15: 'prevalidation boot generation', 16: 'prevalidation state'}
GATES = ['!known', '!stable', 'power', 'battery', 'alarm', 'call', 'activity', '!peer_stable']
# SAM | 2026-11-06 +08:00 | Match the current native Boot layout; CRC is integrity evidence, not signed-image authentication.
BOOT_LAYOUT_CRC = zlib.crc32(struct.pack('<10I', 0x100000, 4096, 0x2000, 0x80000, 442368,
                                       0xf6000, 0xf7000, 0xf8000, 0xfe000, 0x2000))
SRAM_BASE, SRAM_SIZE = 0x20000000, 0x80000


# SAM | 2026-11-06 +08:00 | Keep capture and J-Link output in the fresh evidence directory; do not reuse existing files.
def dump(tmp):
    t = Path(tmp).as_posix()
    script = Path(tmp) / 'probe.jlink'
    with script.open('x') as f:
        f.write(f'savebin "{t}/owner.bin",0x2F9000,0x2000\nsavebin "{t}/journal.bin",0x2F7000,0x2000\n'
                f'savebin "{t}/sram.bin",0x20000000,0x80000\nmem32 0xE000EDF0,1\nexit\n')
    result = subprocess.run([JLINK, '-NoGui', '1', '-ExitOnError', '1', '-device', 'CORTEX-M4', '-if', 'SWD', '-speed', '4000',
                             '-autoconnect', '1', '-CommandFile', str(script)], capture_output=True, text=True, errors='replace')
    out = result.stdout
    with (Path(tmp) / 'jlink.txt').open('x', encoding='utf-8') as f:
        f.write(out + '\n' + result.stderr)
    if result.returncode:
        raise RuntimeError(f'J-Link exited {result.returncode}; raw evidence retained in {tmp}')
    dhcsr = next((l.split('=')[1].strip() for l in out.splitlines() if 'E000EDF0' in l), None)
    return dhcsr


# SAM | 2026-11-06 +08:00 | Validate complete saved captures and exact-address bounds without accessing a probe.
def validate_install_error_address(address):
    if address is not None and (address % 4 or not SRAM_BASE <= address <= SRAM_BASE + SRAM_SIZE - 64):
        raise ValueError('install-error address must be word-aligned and contain 64 bytes within 0x20000000..0x2007ffff')


def decode_capture(o, j, ram, epoch=None, install_error_address=None, firmware_provenance=None):
    validate_install_error_address(install_error_address)
    if (len(o), len(j), len(ram)) != (8192, 8192, SRAM_SIZE):
        raise ValueError('expected complete owner=8192, journal=8192, sram=524288 byte captures')
    rep = {'owner': [], 'owner_latest': None, 'journal': [], 'journal_latest': None, 'install_error': None,
           'install_error_candidates': [], 'firmware_provenance': firmware_provenance or 'unspecified; firmware association unverified',
           'limitations': ['non-atomic snapshot; RAM may change during reads',
                           'native short-enum owner ABI and current Boot layout assumed; CRC does not authenticate images',
                           'supplied symbol address/provenance is not independently verified']}
    owner_states, owner_bytes = [], []
    for p in (0, 0x1000):
        page = o[p:p + 4096]
        r = page[:368]
        magic, generation = struct.unpack_from('<2I', r)
        v1 = magic == 0x594F5431
        crc_at, size = (352, 360) if v1 else (360, 368)
        crc, commit = struct.unpack_from('<2I', r, crc_at)
        crc_ok = magic in (0x594F5431, 0x594F5432) and crc == zlib.crc32(r[:crc_at])
        tail_ok = all(b == 255 for b in page[size:])
        body_ok = crc_ok and tail_ok and generation != 0
        state = 'erased' if page == b'\xff' * 4096 else ('committed' if body_ok and commit == 0 else
                'uncommitted' if body_ok and commit == 0xffffffff else 'invalid')
        owner_states.append(state)
        owner_bytes.append(r[:size])
        s = lambda off, n: r[off:off + n].split(b'\0')[0].decode('latin1')
        total, durable = (None, None) if v1 else struct.unpack_from('<2I', r, 352)
        rep['owner'].append(dict(addr=hex(0x2F9000 + p), magic=hex(magic), format='v1' if v1 else 'v2' if magic == 0x594F5432 else 'unknown',
                                 generation=generation, epoch=struct.unpack_from('<I', r, 8)[0],
                                 phase=PHASE[r[12]] if r[12] < 5 else r[12], target=s(143, 8), version=s(151, 64), source=s(215, 64),
                                 actual=s(279, 64), outcome=s(343, 8), total=None if total is None else total & 0x7FFFFFFF,
                                 b_owned=None if total is None else bool(total >> 31), durable=durable,
                                 crc_ok=crc_ok, commit=commit, tail_erased=tail_ok, record_status=state, valid=state == 'committed'))
    committed = [i for i, state in enumerate(owner_states) if state == 'committed']
    if committed and 'invalid' not in owner_states:
        selected = max(committed, key=lambda i: rep['owner'][i]['generation'])
        gen = rep['owner'][selected]['generation']
        conflict = len(committed) == 2 and rep['owner'][0]['generation'] == rep['owner'][1]['generation'] and owner_bytes[0] != owner_bytes[1]
        unfinished_bad = any(state == 'uncommitted' and (gen == 0xffffffff or rep['owner'][i]['generation'] != gen + 1)
                             for i, state in enumerate(owner_states))
        if not conflict and not unfinished_bad:
            rep['owner_latest'] = rep['owner'][selected]
    rep['owner_selection_status'] = 'selected committed record' if rep['owner_latest'] else 'no usable committed owner (erased, invalid or conflicting)'
    # Boot opens only the first 124 bytes of each page; later magic-looking bytes are not journal records.
    for page in (0, 0x1000):
        rec = j[page:page + 124]
        w = struct.unpack('<31I', rec)
        crc_ok = w[29] == zlib.crc32(rec[:116])
        layout_ok = w[2] == BOOT_LAYOUT_CRC
        fields_ok = 1 <= w[3] <= 6 and w[4] <= 108 and w[5] <= 2 and 0 < w[7] <= 442368 and 0 < w[17] <= 442368 and w[27:29] == (1, 0)
        rep['journal'].append(dict(addr=hex(0x2f7000 + page), generation=w[1], state=BOOT.get(w[3], w[3]), attempts=w[6],
                                   crc_ok=crc_ok, commit=w[30], layout_crc_ok=layout_ok, fields_ok=fields_ok,
                                   valid=w[0] == 0x59504231 and crc_ok and w[30] == 0 and layout_ok and fields_ok))
    valid_journal = [r for r in rep['journal'] if r['valid']]
    if valid_journal and not (len(valid_journal) == 2 and valid_journal[0]['generation'] == valid_journal[1]['generation']):
        rep['journal_latest'] = max(valid_journal, key=lambda r: r['generation'])
    rep['journal_selection_status'] = 'selected current-layout CRC/commit/fields-valid page head' if rep['journal_latest'] else 'no usable journal or equal-generation conflict'

    def error_at(off, selection):
        w = struct.unpack_from('<16I', ram, off)
        return dict(addr=hex(SRAM_BASE + off), raw16=list(w), marker=w[0], selection=selection,
                    record_status='absent_marker' if w[0] == 0 else 'present_marker' if w[0] == 1 else 'unknown_marker',
                    count=w[1], stage=w[2], stage_name=STAGE.get(w[2], '?'), epoch=w[3],
                    owner_phase=PHASE[w[4]] if w[4] < len(PHASE) else w[4], boot_state=BOOT.get(w[5], w[5]), boot_generation=w[6],
                    gate_mask=w[7], gates_failed=[g for i, g in enumerate(GATES) if w[7] >> i & 1],
                    evidence=dict(now_ms=w[8], battery_age_ms=w[9], keys_age_ms=w[10], motion_age_ms=w[11], flags=w[12]),
                    old_version=w[13], new_version=w[14], at_ms=w[15])

    if install_error_address is not None:
        rep['install_error'] = error_at(install_error_address - SRAM_BASE, 'supplied address; symbol association unverified')
        rep['install_error_status'] = rep['install_error']['record_status'] + '; zero marker alone does not prove the failed path was never entered'
    else:
        for off in range(0, len(ram) - 64 + 1, 4):
            w = struct.unpack_from('<16I', ram, off)
            if w[0] == 1 and w[1] and w[2] in STAGE and w[4] < len(PHASE) and (w[5] in BOOT or w[5] == 0xffffffff) and (epoch is None or w[3] == epoch):
                rep['install_error_candidates'].append(error_at(off, 'heuristic candidate; symbol association unverified'))
        rep['install_error_status'] = f"{len(rep['install_error_candidates'])} unverified heuristic candidates; none promoted to a confirmed symbol"
    return rep


# SAM | 2026-11-06 +08:00 | Offline mode never invokes J-Link; live evidence directories and reports use exclusive creation.
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--epoch', type=int)
    ap.add_argument('--json', help='new JSON report path; existing files are never overwritten')
    ap.add_argument('--offline-dir', type=Path, help='decode existing owner.bin, journal.bin and sram.bin only')
    ap.add_argument('--output-dir', type=Path, help='NEW directory for retained live raw dumps (default: new system temp directory)')
    ap.add_argument('--install-error-address', type=lambda s: int(s, 0), help='exact SRAM symbol address from matching firmware evidence')
    ap.add_argument('--firmware-provenance', help='source/build/map provenance for the supplied address')
    a = ap.parse_args(argv)
    try:
        validate_install_error_address(a.install_error_address)
        if a.offline_dir and a.output_dir:
            ap.error('--offline-dir and --output-dir are mutually exclusive')
        if a.json and Path(a.json).exists():
            ap.error('--json path already exists; choose a new evidence file')
        dhcsr = None
        if a.offline_dir:
            directory = a.offline_dir
        else:
            directory = a.output_dir
            if directory is None:
                directory = Path(tempfile.mkdtemp(prefix='gr_ota_probe_'))
            else:
                directory.mkdir(parents=True, exist_ok=False)
            dhcsr = dump(directory)
        o, j, ram = (Path(directory, n).read_bytes() for n in ('owner.bin', 'journal.bin', 'sram.bin'))
        rep = decode_capture(o, j, ram, a.epoch, a.install_error_address, a.firmware_provenance)
    except (OSError, ValueError, RuntimeError) as exc:
        ap.error(str(exc))
    rep.update(dhcsr=dhcsr, halted=None if dhcsr is None else bool(int(dhcsr, 16) & (1 << 17)),
               capture_dir=str(directory.resolve()), capture_mode='offline' if a.offline_dir else 'live')
    text = json.dumps(rep, indent=1, ensure_ascii=False)
    if a.json:
        with Path(a.json).open('x', encoding='utf-8') as f:
            f.write(text)
    print(text)


if __name__ == '__main__':
    main()
