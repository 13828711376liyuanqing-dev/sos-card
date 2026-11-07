"""SAM | 2026-10-29 12:33 +08:00 | Local GR5526 post-F7 tool (user request: stop spending assistant tokens on the same steps).
Wraps the board-verified skill .claude/skills/yp001-gr-jlink-deploy: build acceptance, test-key signing, Boot pairing, export of the final
images as HEX and/or BIN, Keil Download-only flashing through J-Link, one SYSRESETREQ, readback acceptance and a GR CLI check.

  python tools/gr_release/gr_build_tool.py check                       # read-only: build log, freshness, version, changed sources
  python tools/gr_release/gr_build_tool.py sign  --format hex|bin|both # any version: signed app for OTA packaging (no device access)
  python tools/gr_release/gr_build_tool.py prepare --format both       # 1.0.2 bench baseline only: 2 read-only snapshots + pair + export
  python tools/gr_release/gr_build_tool.py flash firmware_releases/<out>  # writes Flash: asks you to type FLASH, then download/reset/verify
  python tools/gr_release/gr_build_tool.py auto  --format both         # prepare then flash (two confirmations)

Rules kept from the skill/AGENTS.md: never flash the unsigned Keil HEX; pairing only rebinds a clean Boot PREPARED journal with unchanged
owner pages (any assert = stop and investigate); J-Link Commander is used only for read/reset (no GR5526 flash algorithm); CAT1 power-on
after the reset is NOT automatic (check `business status`; use the skill's start_cat1_once.py only with your authorization)."""
import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
OBJECTS = ROOT / 'firmware_releases/gr_uart_recovery_20261025/baseline/Objects'
RELEASES = ROOT / 'firmware_releases'
SKILL = ROOT / '.claude/skills/yp001-gr-jlink-deploy/scripts'
JLINK = r'C:\Program Files\SEGGER\JLink\JLink.exe'
UV4 = r'C:\Keil_v5\UV4\UV4.exe'
# SAM | 2026-10-30 10:42 +08:00 | One signing implementation: the standalone file tool (tools/gr_release/GR5526_Tool), also used by colleagues.
SIGNER = HERE / 'GR5526_Tool/Gr5526Tool.exe'
PY = sys.executable
BENCH_VERSION = ('001.000.002', 3)  # the only version whose Boot pairing (descriptor version 1000002) is board-verified
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def say(*a):
    print(*a, flush=True)


def stop(msg):
    say('STOP:', msg); raise SystemExit(2)


def identity():
    axf = OBJECTS / 'YP001_GR5526.axf'
    m = re.search(rb'YP001_FW\|GR5526\|(\d{3}\.\d{3}\.\d{3})\|(\d+)\|END', axf.read_bytes())
    if not m: stop('no YP001_FW identity in ' + str(axf))
    comp = m.group(1).decode(); product = '.'.join(str(int(x)) for x in comp.split('.'))
    return comp, int(m.group(2)), product


def build_acceptance():
    axf, hexf, log = OBJECTS / 'YP001_GR5526.axf', OBJECTS / 'YP001_GR5526.hex', OBJECTS / 'YP001_GR5526.build_log.htm'
    for p in (axf, hexf, log):
        if not p.exists(): stop('missing ' + str(p))
    text = log.read_text(errors='replace')
    clean = '0 Error(s), 0 Warning(s)' in text
    objs = list(OBJECTS.glob('*.o'))
    linked = bool(objs) and max(p.stat().st_mtime for p in objs) <= axf.stat().st_mtime
    hex_fresh = hexf.stat().st_mtime >= axf.stat().st_mtime
    stale = []
    for dep in OBJECTS.glob('*.d'):
        obj = dep.with_suffix('.o')
        if not obj.exists(): continue
        body = dep.read_text(errors='replace').partition(': ')[2].replace('\\\n', ' ')
        for tok in re.findall(r'"[^\"]+"|(?:\\ |[^\s])+', body):
            tok = tok.strip('"').replace('\\ ', ' ')
            if tok == '\\': continue
            p = Path(tok); p = p if p.is_absolute() else (ROOT / 'ble_app_uart_c/Keil_6' / p)
            if p.is_file() and p.stat().st_mtime > obj.stat().st_mtime: stale.append(obj.name); break
    comp, build, product = identity()
    bench = re.search(rb'YP001_OTA_USB_BENCH_TEST=1', (ROOT / 'ble_app_uart_c/Keil_6/YP001_GR5526.uvprojx').read_bytes()) is not None
    units = re.search(r'(\d+)\s+(?:of\s+\d+\s+)?(?:file|unit)', text)
    res = dict(clean=clean, linked_after_objects=linked, hex_after_axf=hex_fresh, stale_objects=sorted(set(stale)),
               component_version=comp, build=build, product_version=product, bench_define=bench,
               axf=str(axf.relative_to(ROOT)), axf_mtime=datetime.fromtimestamp(axf.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
               axf_sha256=sha(axf), hex_sha256=sha(hexf))
    res['ready'] = clean and linked and hex_fresh and not stale
    return res


def latest_delivery():
    best = None
    for d in RELEASES.iterdir():
        if (d / 'paired_downloads.json').exists() and (d / 'baseline/baseline_signed.bin').exists() and (d / 'boot/BOOT_BOUND.bin').exists():
            if not best or d.stat().st_mtime > best.stat().st_mtime: best = d
    return best


def changed_sources(frozen):
    deps = json.loads(Path(frozen).read_text())['dependencies']; out = []
    for p, h in deps.items():
        q = Path(p)
        if not q.exists() or sha(q) != h: out.append(p)
    # New dependencies not in the frozen set are caught by prepare_delivery's own exact check.
    return sorted(out)


def jlink(cmds, log=None):
    tmp = ROOT / 'logs' / '_gr_tool.jlink'
    tmp.write_text('\n'.join(cmds + ['exit']) + '\n')
    out = subprocess.run([JLINK, '-NoGui', '1', '-ExitOnError', '1', '-device', 'CORTEX-M4', '-if', 'SWD', '-speed', '4000',
                          '-autoconnect', '1', '-CommandFile', str(tmp)], capture_output=True, text=True, errors='replace').stdout
    tmp.unlink(missing_ok=True)
    if log: Path(log).write_text(out, encoding='utf-8')
    if 'VTref' not in out: stop('J-Link did not connect (check probe/USB/power)')
    return out


def snapshot(path):
    out = jlink([f'savebin {Path(path).as_posix()},0x200000,0x100000', 'mem32 0xE000EDF0,1'])
    d = re.search(r'E000EDF0 = ([0-9A-F]{8})', out)
    if not Path(path).exists() or Path(path).stat().st_size != 0x100000: stop('snapshot failed')
    if d and int(d.group(1), 16) & (1 << 17): stop('core is HALTED (DHCSR=%s); recover normal start first' % d.group(1))
    return Path(path).read_bytes()


def journal_state(snap):
    best = None
    for page in (0xF7000, 0xF8000):
        for off in range(0, 4096 - 123, 124):
            rec = snap[page + off:page + off + 124]; w = struct.unpack('<31I', rec)
            if w[0] == 0x59504231 and w[29] == zlib.crc32(rec[:116]) and (not best or w[1] > best[1]): best = w
    names = {0: 'EMPTY', 1: 'PREPARED', 2: 'INSTALL', 3: 'TRIAL', 4: 'ROLLBACK', 5: 'CONFIRMED', 6: 'REVERTED'}
    return (best[1], names.get(best[3], best[3]), tuple(best[4:7])) if best else None


def export(out, fmt, comp, build):
    flash = out / 'FLASH'; flash.mkdir(exist_ok=True)
    pairs = [(out / 'baseline/SIGNED_DOWNLOAD/STAGE1_SIGNED_BASELINE_ONLY', f'APP_SIGNED_{comp}_b{build}'),
             (out / 'boot/PAIRED_BOOT_EXACT', 'BOOT_PAIRED')]
    made = []
    for src, name in pairs:
        for ext in (['hex', 'bin'] if fmt == 'both' else [fmt]):
            s = src.with_suffix('.' + ext); d = flash / f'{name}.{ext}'
            shutil.copy2(s, d); made.append((d.name, sha(d)))
    (flash / 'README.txt').write_text(
        'SAM | generated by tools/gr_release/gr_build_tool.py\n'
        'APP_SIGNED: signed app for the A slot (starts 0x00202000). BOOT_PAIRED: Boot rebound to it (0x002EC000).\n'
        'Flash BOTH, app first, then Boot, with sector erase only (-FO7 equivalent); never flash the unsigned Keil HEX.\n'
        'After download the PC sits in the flash-algorithm SRAM loop: one SYSRESETREQ, then readback acceptance.\n'
        + ''.join(f'{n}  sha256={h}\n' for n, h in made), encoding='utf-8')
    return made


def cmd_check(a):
    res = build_acceptance()
    prev = latest_delivery()
    res['previous_delivery'] = str(prev.relative_to(ROOT)) if prev else None
    fz = prev and prev / 'frozen_inputs.json'
    res['changed_sources_vs_previous'] = [str(Path(p).relative_to(ROOT)) if p.startswith(str(ROOT)) else p
                                          for p in changed_sources(fz)] if fz and fz.exists() else 'NO_FROZEN_INPUTS'
    res['jlink_flash_supported'] = (res['component_version'], res['build']) == BENCH_VERSION
    say(json.dumps(res, indent=1, ensure_ascii=False))
    if not res['ready']: stop('build not accepted (errors/warnings, stale objects or HEX older than AXF): press F7 again')
    return res


def cmd_sign(a):
    res = cmd_check(a)
    out = RELEASES / f'gr_signed_{res["product_version"]}_b{res["build"]}_{datetime.now():%Y%m%d_%H%M}'
    keys = ROOT / 'tools/toolkit/test_keys'
    p = subprocess.run([str(SIGNER), 'sign', str(OBJECTS / 'YP001_GR5526.hex'), '--out', str(out),
                        '--private', str(keys / 'OTA_TEST_PRIVATE.key'), '--public', str(keys / 'OTA_TEST_PUBLIC.xml'),
                        '--layout', str(ROOT / 'tools/toolkit/contracts/layout_candidate.json'),
                        '--data', str(ROOT / 'tools/toolkit/contracts/data_contract_candidate.json'),
                        '--format', a.format if a.format in ('hex', 'both') else 'bin', '--expect-version', res['product_version']],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    say(p.stdout.strip())
    if p.returncode: stop('signing failed (see the report above)')
    made = [(f.name, sha(f)) for f in sorted(out.iterdir())]
    (out / 'build_acceptance.json').write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding='utf-8')
    say('Use the .bin with ReleaseCli pack-trial / the OTA packager. This is NOT a direct-flash image (no Boot pairing).')
    return made


def to_ihex(data, base):
    lines, hi = [], None
    for off in range(0, len(data), 16):
        addr = base + off
        if addr >> 16 != hi:
            hi = addr >> 16; rec = bytes([2, 0, 0, 4, hi >> 8, hi & 255]); lines.append(':' + rec.hex().upper() + '%02X' % (-sum(rec) & 255))
        chunk = data[off:off + 16]; rec = bytes([len(chunk), (addr >> 8) & 255, addr & 255, 0]) + chunk
        lines.append(':' + rec.hex().upper() + '%02X' % (-sum(rec) & 255))
    return '\n'.join(lines + [':00000001FF']) + '\n'


def cmd_prepare(a):
    res = cmd_check(a)
    if (res['component_version'], res['build']) != BENCH_VERSION:
        stop(f'J-Link pairing is verified only for the 1.0.2 build 3 bench baseline (Boot descriptor version 1000002); this build is '
             f'{res["component_version"]}/b{res["build"]}. Use `sign` and deliver it by OTA, or set the version back to 1.0.2 and F7 again.')
    prev = latest_delivery()
    if not prev or not (prev / 'frozen_inputs.json').exists(): stop('no previous delivery with frozen_inputs.json')
    stamp = datetime.now().strftime('%Y%m%d_%H%M'); audit = ROOT / 'logs' / f'gr_flash_{stamp}'; audit.mkdir(parents=True)
    say('previous delivery:', prev.relative_to(ROOT)); say('snapshot 1 (read-only) ...')
    s1 = snapshot(audit / 'pre_flash_1.bin')
    say(f'waiting {a.gap}s for snapshot 2 ...'); time.sleep(a.gap)
    s2 = snapshot(audit / 'pre_flash_2.bin')
    diff = [hex(0x200000 + i * 4096) for i in range(256) if s1[i * 4096:(i + 1) * 4096] != s2[i * 4096:(i + 1) * 4096]]
    if diff: stop('flash changed between snapshots (device busy/OTA running?): ' + ', '.join(diff[:8]))
    js = journal_state(s2); say('Boot journal:', js)
    if not js or js[1] != 'PREPARED' or js[2] != (0, 0, 0): stop(f'latest Boot journal is {js}; pairing only rebinds a clean PREPARED record')
    changed = [p for p in changed_sources(prev / 'frozen_inputs.json')]
    say('changed sources since previous delivery:'); [say('  ', Path(p).relative_to(ROOT) if p.startswith(str(ROOT)) else p) for p in changed]
    if not a.yes and input('Are these exactly the intended changes? [y/N] ').strip().lower() != 'y': stop('cancelled by user')
    out = RELEASES / f'gr_{res["product_version"]}_b{res["build"]}_{stamp}'
    cmd = [PY, str(SKILL / 'prepare_delivery.py'), '--previous', str(prev.relative_to(ROOT)), '--out', str(out.relative_to(ROOT)),
           '--audit', str(audit.relative_to(ROOT)), '--frozen', str((prev / 'frozen_inputs.json').relative_to(ROOT)),
           '--snapshot', str((audit / 'pre_flash_2.bin').relative_to(ROOT))]
    for p in changed: cmd += ['--allow', str(Path(p).relative_to(ROOT))]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, errors='replace')
    (audit / 'prepare.log').write_text(p.stdout + p.stderr, encoding='utf-8')
    if p.returncode: stop('pairing refused (see %s): %s' % ((audit / 'prepare.log').relative_to(ROOT), (p.stdout + p.stderr).strip()[-600:]))
    made = export(out, a.format, res['component_version'], res['build'])
    say('PREPARED', out.relative_to(ROOT)); [say(' ', n, h) for n, h in made]
    (out / 'tool_audit.txt').write_text(str(audit.relative_to(ROOT)))
    return out


def gr_cli(cmds, wait=3000):
    sys.path.insert(0, str(ROOT / 'tools/ota'))
    import serial
    text = []
    with serial.Serial('COM26', 115200, timeout=0.1) as s:
        time.sleep(0.3); s.read(65536)
        for c in cmds:
            s.write((c + '\r\n').encode()); end = time.time() + wait / 1000
            while time.time() < end: text.append(s.read(4096).decode('utf-8', 'replace'))
    return ''.join(text)


def cmd_flash(a):
    out = (ROOT / a.out).resolve()
    audit = ROOT / (out / 'tool_audit.txt').read_text().strip()
    m = json.loads((out / 'paired_downloads.json').read_text())
    say('About to WRITE Flash with', out.relative_to(ROOT), '(app then Boot). Close Keil debug/download sessions first.')
    if input('Type FLASH to continue: ').strip() != 'FLASH': stop('cancelled by user')
    now = snapshot(audit / 'pre_flash_3.bin')
    if now != (audit / 'pre_flash_2.bin').read_bytes(): stop('device flash changed since prepare; run prepare again')
    for proj, log in ((out / 'baseline/SIGNED_DOWNLOAD/DOWNLOAD_SIGNED_APP_ONLY.uvprojx', 'download_app.log'),
                      (out / 'boot/DOWNLOAD_PAIRED_BOOT_ONLY.uvprojx', 'download_boot.log')):
        say('download', proj.name, '...')
        subprocess.run([UV4, '-f', str(proj), '-j0', '-o', str(audit / log)], timeout=600)
        t = (audit / log).read_text(errors='replace') if (audit / log).exists() else ''
        if 'Verify OK' not in t: stop(f'{log}: no "Verify OK"; do NOT reset, inspect the log')
    say('one SYSRESETREQ ...')
    r = jlink(['mem32 0xE000EDF0,1', 'h', 'regs', 'w4 0xE000ED0C 0x05FA0004', 'sleep 2000', 'mem32 0xE000EDF0,1'], audit / 'jlink_reset.log')
    pc = re.search(r'PC = ([0-9A-F]{8})', r); say('PC before reset:', pc and pc.group(1))
    time.sleep(3)
    snapshot(audit / 'post_flash_1.bin')
    p = subprocess.run([PY, str(SKILL / 'check_readback.py'), '--out', str(out.relative_to(ROOT)), '--pre', str((audit / 'pre_flash_2.bin').relative_to(ROOT)),
                        '--post', str((audit / 'post_flash_1.bin').relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True, errors='replace')
    (audit / 'readback.json').write_text(p.stdout, encoding='utf-8')
    if p.returncode: stop('readback acceptance FAILED: ' + p.stdout[-800:])
    say('readback PASS')
    cli = gr_cli(['fw_version', 'business status'])
    (audit / 'post_cli.log').write_text(cli, encoding='utf-8')
    v = re.search(r'YP001_FW\|GR5526\|[^\r\n]*', cli); b = re.search(r'\[BUSINESS\][^\r\n]*', cli)
    say('GR:', v and v.group(0)); say('BUSINESS:', b and b.group(0))
    if not v: stop('no GR fw_version answer on COM26 after reset')
    if b and 'link=0' in b.group(0):
        say('NOTE: CAT1 is off after the GR reset. Follow the skill red-line order (cat1_power on, wait, one key) or start_cat1_once.py with authorization.')
    say('FLASH DONE', json.dumps({k: m.get(k) for k in ('app_sha256', 'boot_sha256', 'next_prepared_generation')}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    for n in ('sign', 'prepare', 'auto'):
        p = sub.add_parser(n); p.add_argument('--format', choices=('hex', 'bin', 'both'), default='both')
        p.add_argument('--gap', type=int, default=60, help='seconds between the two read-only snapshots'); p.add_argument('--yes', action='store_true')
    f = sub.add_parser('flash'); f.add_argument('out')
    a = ap.parse_args()
    if a.cmd == 'check': cmd_check(a)
    elif a.cmd == 'sign': cmd_sign(a)
    elif a.cmd == 'prepare': cmd_prepare(a)
    elif a.cmd == 'flash': cmd_flash(a)
    elif a.cmd == 'auto':
        out = cmd_prepare(a); a.out = str(out.relative_to(ROOT)); cmd_flash(a)


if __name__ == '__main__':
    main()
