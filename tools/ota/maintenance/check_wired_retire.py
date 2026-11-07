"""SAM | 2026-11-07 +08:00 | Validate a narrowly scoped wired retirement plan offline; never accesses devices or writes Flash."""
import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gr_ota_probe import decode_capture


# SAM | 2026-11-07 +08:00 | Only the current logger run's still-connected port response proves liveness; reopening alone supplies no beacon.
def live_cat_beacon(text):
    beacons, disconnected = {}, set()
    for index, line in enumerate(text.splitlines()):
        if re.search(r'\bPC\s+VUART LOG start\b', line):
            beacons.clear()
            disconnected.clear()
            continue
        event = re.search(r'\bPC\s+(COM\d+)\s+(lost|opened)\b', line)
        if event:
            port, state = event.groups()
            beacons.pop(port, None)
            if state == 'lost':
                disconnected.add(port)
            else:
                disconnected.discard(port)
            continue
        beacon = re.search(r'\b(COM\d+)\s+\[OTA\] B ', line)
        if beacon and beacon[1] not in disconnected:
            beacons[beacon[1]] = (index, line)
    return max(beacons.values())[1] if beacons else None


# SAM | 2026-11-07 +08:00 | Share exact task checks between offline review and the flasher's actual pre-erase snapshot.
def _validate_owner_boot(raw, journal, profile, sram=None):
    report = decode_capture(raw, journal, bytes(0x80000) if sram is None else sram)
    owner, boot = report['owner_latest'], report['journal_latest']
    if not owner or not boot:
        raise ValueError('owner/Boot CRC, commit or selection invalid')
    if (owner['generation'] != profile['owner_generation'] or owner['epoch'] != profile['epoch'] or
            owner['phase'] != 'PREPARED' or owner['target'] != 'GR5526' or
            owner['version'] != profile['target_version'] or owner['source'] != profile['source_version'] or
            owner['total'] != profile['old_image_bytes'] or owner['durable'] != owner['total']):
        raise ValueError('owner is not the approved fully staged PREPARED task')
    offset = int(owner['addr'], 16) - 0x2f9000
    read = lambda start, size: raw[offset + start:offset + start + size].split(b'\0')[0].decode('ascii')
    if read(13, 65) != profile['job_id'] or read(78, 65) != profile['hash']:
        raise ValueError('owner job/hash changed')
    if boot['state'] != 'CONFIRMED' or boot['generation'] != profile['boot_generation']:
        raise ValueError('Boot is not the approved CONFIRMED baseline; no retirement allowed')
    return owner, boot


def _validate_logs(profile, gr_log, cat_log):
    gr = Path(gr_log).read_text(encoding='utf-8', errors='replace')
    version = re.findall(r'YP001_FW\|GR5526\|([\d.]+)\|(\d+)\|END', gr)
    status = re.findall(r'\[BUSINESS\]([^\r\n]+)', gr)
    if not version or not status:
        raise ValueError('GR CLI did not prove normal application operation')
    v, build = version[-1]
    if '.'.join(str(int(n)) for n in v.split('.')) != profile['source_version'] or int(build) != profile['source_build']:
        raise ValueError('running GR differs from approved source identity')
    fields = dict(re.findall(r'(\w+)=([^\s]+)', status[-1]))
    if any(fields.get(k) != v for k, v in {'link': '1', 'net': '4', 'alarm': '0', 'call': '0'}.items()):
        raise ValueError('business state is not online/idle; do not reset or program')
    cat = Path(cat_log).read_text(encoding='utf-8', errors='replace')
    beacon = live_cat_beacon(cat)
    if not beacon or not re.search(r'\[OTA\] B RECOVERY_HOLD .* SPENT activation_validation_failed N IDLE IDLE ', beacon):
        raise ValueError('CAT1 did not prove the exact failed task and idle native installer')


def _validate_image(image, profile):
    if hashlib.sha256(image).hexdigest() != profile['new_image_sha256']:
        raise ValueError('signed image differs from approved hash')


def validate(folder, profile, image, gr_log, cat_log):
    folder = Path(folder)
    owner, boot = _validate_owner_boot((folder / 'owner.bin').read_bytes(), (folder / 'journal.bin').read_bytes(),
                                       profile, (folder / 'sram.bin').read_bytes())
    _validate_logs(profile, gr_log, cat_log)
    _validate_image(Path(image).read_bytes(), profile)
    return {'ready_for_operator_confirmation': True, 'device_actions': False,
            'owner_generation': owner['generation'], 'epoch': owner['epoch'],
            'boot_generation': boot['generation'], 'signed_sha256': profile['new_image_sha256'],
            'limitations': ['non-atomic capture; execute immediately only on the same attached board',
                            'this report grants no erase/write authority; operator confirmation is separate']}


# SAM | 2026-11-07 +08:00 | Fresh CLI evidence and hashes must bind the actual 1 MiB pre.bin/app bytes before the first erase, not an earlier capture.
def _require_fresh_log(path, now):
    mtime = Path(path).stat().st_mtime
    if not math.isfinite(now) or not math.isfinite(mtime) or not 0 <= now - mtime <= 60:
        raise ValueError('CLI log is stale or future-dated; fresh GR/CAT evidence within 60 seconds required')


def validate_flash_snapshot(pre: bytes, app: bytes, profile: dict, gr_log, cat_log, now: float):
    if len(pre) != 0x100000:
        raise ValueError('pre-erase Flash snapshot must contain exactly 1 MiB')
    _validate_image(app, profile)
    old_bytes = profile['old_running_bytes']
    if old_bytes != 377064 or hashlib.sha256(pre[0x2000:0x2000 + old_bytes]).hexdigest() != profile['old_running_sha256']:
        raise ValueError('actual running signed A differs from the approved old image')
    if hashlib.sha256(pre[0xec000:0xf6000]).hexdigest() != profile['old_boot_sha256']:
        raise ValueError('actual Boot differs from the approved baseline')
    protected = pre[0x6e000:0x80000] + pre[0xfb000:0x100000]
    if hashlib.sha256(protected).hexdigest() != profile['protected_sha256']:
        raise ValueError('protected Flash differs from the approved baseline')
    owner, boot = _validate_owner_boot(pre[0xf9000:0xfb000], pre[0xf7000:0xf9000], profile)
    for path in (gr_log, cat_log):
        _require_fresh_log(path, now)
    _validate_logs(profile, gr_log, cat_log)
    return {'flash_snapshot_validated': True, 'owner_generation': owner['generation'], 'epoch': owner['epoch'],
            'boot_generation': boot['generation'], 'signed_sha256': profile['new_image_sha256'],
            'limitations': ['requires caller to invoke on actual pre.bin/app immediately before first erase on the pinned device',
                            'zero SRAM supplied only for owner/Boot decoding; no RAM or image authentication claim',
                            'log mtime bounds evidence freshness; liveness can change after the captured response']}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('capture', 'profile', 'image', 'gr-log', 'cat-log'):
        ap.add_argument('--' + name, type=Path)
    ap.add_argument('--cat-online-log', type=Path, help='standalone ordered live CAT beacon check, including after flashing')
    args = ap.parse_args(argv)
    try:
        if args.cat_online_log:
            if any((args.capture, args.profile, args.image, args.gr_log, args.cat_log)):
                ap.error('--cat-online-log is a standalone mode')
            _require_fresh_log(args.cat_online_log, time.time())
            beacon = live_cat_beacon(args.cat_online_log.read_text(encoding='utf-8', errors='replace'))
            if beacon is None:
                raise ValueError('CAT1 has no live beacon after its last port disconnect/reconnect')
            result = {'cat_online': True, 'device_actions': False, 'limitations': ['beacon liveness only; firmware identity and installation success unverified']}
        else:
            if not all((args.capture, args.profile, args.image, args.gr_log, args.cat_log)):
                ap.error('review mode requires --capture --profile --image --gr-log --cat-log')
            result = validate(args.capture, json.loads(args.profile.read_text(encoding='utf-8')),
                              args.image, args.gr_log, args.cat_log)
    except (OSError, ValueError, KeyError, UnicodeError) as exc:
        ap.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
