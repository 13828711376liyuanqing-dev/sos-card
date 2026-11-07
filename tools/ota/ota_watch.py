"""SAM | 2026-10-29 11:55 +08:00 | Token-saving local OTA watcher (user request): polls COM26 itself and prints only events, so the
assistant reads one short summary instead of re-reading logs. Read-only: sends only `cat_at FOTA_STATUS` and `fw_version`.
Events: phase/reason/step change, progress crossing each 25 %, GR version change, CAT1 no answer, stall, finish.
Exit codes: 0 finished (CAT1 back to IDLE after a task), 2 stopped (RECOVERY_HOLD / limit / error reason), 3 stalled,
4 CAT1 or GR silent too long, 5 overall timeout. Full raw lines go to --log; the last state goes to --state (JSON).
Usage: python ota_watch.py --log logs/x.log [--state logs/x.json] [--poll-sec 30] [--stall-min 8] [--silent-min 6] [--max-min 90]"""
import argparse
import json
import re
import time
from datetime import datetime
import serial

STOP_REASONS = re.compile(r'FAILED_HASH_LIMIT|TRIAL_SPENT_STOP|RECOVERY|DENIED|MISMATCH|INVALID|SCOPE')
NOISE = re.compile(r'^\[BAT\]|^\[CHG\]|EPD|^\s*>?\s*$')


def now():
    return datetime.now().strftime('%H:%M:%S')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', required=True)
    ap.add_argument('--state')
    ap.add_argument('--port', default='COM26')
    ap.add_argument('--poll-sec', type=float, default=30)
    ap.add_argument('--gr-sec', type=float, default=120)
    ap.add_argument('--stall-min', type=float, default=8)
    ap.add_argument('--silent-min', type=float, default=6)
    ap.add_argument('--max-min', type=float, default=90)
    a = ap.parse_args()
    st = dict(phase=None, reason=None, step=None, progress=None, total=None, gr=None, seen_task=False,
              last_answer=time.time(), last_progress=time.time(), events=[])

    def event(text):
        line = f'{now()} {text}'
        st['events'].append(line); print(line, flush=True)
        if a.state:
            json.dump({k: v for k, v in st.items()}, open(a.state, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    def finish(code, text):
        event(f'END code={code} {text} | phase={st["phase"]} reason={st["reason"]} step={st["step"]} '
              f'progress={st["progress"]}/{st["total"]} gr={st["gr"]}')
        raise SystemExit(code)

    with serial.Serial(a.port, 115200, timeout=0.1) as s, open(a.log, 'a', encoding='utf-8', buffering=1) as w:
        time.sleep(0.3); s.read(65536)
        start = time.time(); next_poll = 0; next_gr = 0; buf = ''; pending = {}
        event('WATCH start')
        while True:
            t = time.time()
            if t - start > a.max_min * 60: finish(5, 'timeout')
            if t >= next_poll:
                s.write(b'cat_at FOTA_STATUS\r\n'); next_poll = t + a.poll_sec; pending = {}
            if t >= next_gr:
                s.write(b'fw_version\r\n'); next_gr = t + a.gr_sec
            buf += s.read(4096).decode('utf-8', 'replace')
            while '\n' in buf:
                line, buf = buf.split('\n', 1); line = line.rstrip('\r')
                if NOISE.search(line): continue
                w.write(f'{datetime.now().strftime("%H:%M:%S.%f")[:-3]} {line}\n')
                m = re.search(r'YP001_FW\|GR5526\|([\d.]+)\|(\d+)\|', line)
                if m:
                    gr = f'{m.group(1)}/b{m.group(2)}'
                    if gr != st['gr']:
                        event(f'GR version {st["gr"]} -> {gr}'); st['gr'] = gr
                m = re.search(r'\[FOTA_STATUS\]\s+(\S+)$', line)
                if not m: continue
                v = m.group(1); st['last_answer'] = time.time()
                if '=' not in v: pending['phase'] = v
                elif v.startswith('OTA_REASON='): pending['reason'] = v[11:]
                elif v.startswith('OTA_STEP='): pending['step'] = v[9:]
                elif v.startswith('OTA_PROGRESS='):
                    p = re.match(r'OTA_PROGRESS=(\S+):(\d+)/(\d+)', v)
                    if p: pending['progress'] = (p.group(1), int(p.group(2)), int(p.group(3)))
                # Apply what has arrived for this poll.
                for k in ('phase', 'reason', 'step'):
                    if k in pending and pending[k] != st[k]:
                        if k != 'reason' or not (pending[k] == 'DOWNLOAD_PENDING' and st[k] == 'DOWNLOAD_PENDING'):
                            event(f'{k} {st[k]} -> {pending[k]}')
                        st[k] = pending.pop(k)
                if 'progress' in pending:
                    tgt, done, total = pending.pop('progress')
                    old = st['progress'] or 0
                    if done != old:
                        st['last_progress'] = time.time()
                        if total and (done * 4 // total) != (old * 4 // total) or tgt != (st.get('target')):
                            event(f'progress {tgt} {done}/{total} ({done * 100 // max(total, 1)}%)')
                    st['progress'], st['total'], st['target'] = done, total, tgt
                if st['phase'] and st['phase'] != 'IDLE': st['seen_task'] = True
                if st['phase'] == 'IDLE' and st['seen_task']: finish(0, 'task finished, CAT1 IDLE')
                if st['phase'] == 'RECOVERY_HOLD': finish(2, 'RECOVERY_HOLD')
                if st['reason'] and STOP_REASONS.search(st['reason']): finish(2, 'stop reason')
            t = time.time()
            if t - st['last_answer'] > a.silent_min * 60: finish(4, 'no FOTA_STATUS answer (GR rebooting or CAT1 off?)')
            if st['phase'] in ('PREPARING', 'PAUSED') and st['step'] == 'DOWNLOAD_PENDING' and t - st['last_progress'] > a.stall_min * 60:
                finish(3, 'download progress stalled')


if __name__ == '__main__':
    main()
