"""SAM | 2026-11-07 +08:00 | Guard the actual flasher snapshots and loaded image; default is local preview, physical writes need --execute-confirmed."""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

from check_wired_retire import validate_flash_snapshot

ROOT = Path(__file__).resolve().parents[3]
FLASHER = ROOT / 'tools/gr_release/GR_JLink_Flash/yp001_gr_jlink_flash.py'


def run_readonly(arguments):
    result = subprocess.run([sys.executable] + [str(x) for x in arguments], cwd=ROOT,
                            capture_output=True, text=True, errors='replace', timeout=55)
    if result.returncode:
        raise RuntimeError('read-only preflight failed: ' + result.stdout + result.stderr)


def make_guard(flasher, profile, evidence):
    def before_write(pre, app, logdir):
        cat_log, gr_log = evidence / 'cat_at_write.txt', evidence / 'gr_at_write.txt'
        if any(p.exists() for p in (cat_log, gr_log, evidence / 'write_boundary_guard.json')):
            raise ValueError('refusing reused preflight evidence; choose a new attempt directory')
        run_readonly(['tools/ota/cat1_vuart_log.py', '--ports', 'COM21,COM23', '--min', '0.3', '--log', cat_log])
        run_readonly(['tools/ota/gr_cli.py', '--port', 'COM30', '--wait-ms', '1600', '--log', gr_log,
                      'fw_version', 'business status'])
        # Re-read AFTER refreshing online state. Both the flasher's pairing snapshot and this latest
        # snapshot must satisfy the same exact source/Boot/userdata/owner contract before any erase.
        latest = flasher.snapshot(logdir / 'guard_pre.bin', logdir, 'guard_pre_snapshot')
        first = validate_flash_snapshot(pre, app, profile, gr_log, cat_log, time.time())
        final = validate_flash_snapshot(latest, app, profile, gr_log, cat_log, time.time())
        with (evidence / 'write_boundary_guard.json').open('x', encoding='utf-8') as f:
            json.dump({'original_snapshot': first, 'latest_snapshot': final,
                       'jlink_serial': profile['jlink_serial']}, f, indent=2)
        print('WRITE_BOUNDARY_GUARD: PASS (same approved source, Boot, owner and user-area fingerprint)', flush=True)
    return before_write


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--profile', required=True, type=Path)
    ap.add_argument('--image', required=True, type=Path)
    ap.add_argument('--evidence', required=True, type=Path)
    ap.add_argument('--execute-confirmed', action='store_true')
    args = ap.parse_args()
    profile = json.loads(args.profile.read_text(encoding='utf-8'))
    if not args.execute_confirmed:
        print('PREVIEW ONLY: no device access, no erase/write/reset')
        return
    if profile['jlink_serial'] != 69407663:
        raise ValueError('this recovery is bound to J-Link 69407663')
    args.evidence.mkdir(parents=True, exist_ok=True)
    # Claim the attempt exactly once. The serial logger appends, so old evidence must never
    # acquire fresh mtimes and masquerade as a new successful connection.
    with (args.evidence / 'attempt.json').open('x', encoding='utf-8') as f:
        json.dump({'created': time.time(), 'jlink_serial': profile['jlink_serial'],
                   'image_sha256': profile['new_image_sha256']}, f)
    spec = importlib.util.spec_from_file_location('scoped_gr_flasher', FLASHER)
    flasher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flasher)
    previous = sys.argv
    sys.argv = [str(FLASHER), str(args.image.resolve()), '--yes', '--keep-name', '--port', 'COM30',
                '--probe-sn', str(profile['jlink_serial']), '--device-dir', str(FLASHER.parent / '_maintenance_device')]
    try:
        flasher.main(preflight=make_guard(flasher, profile, args.evidence))
    finally:
        sys.argv = previous


if __name__ == '__main__':
    main()
