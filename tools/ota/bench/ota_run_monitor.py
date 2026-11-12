"""SAM | 2026-11-10 | One command for the whole OTA watch: starts the CAT1 keep-power script, the CAT1 beacon log and the GR owner watcher, and prints
ONLY the stage changes and problems (one line each), so it can be used directly as a Monitor command. Ends by itself when the owner reaches COMPLETE
for CAT1 (and stops the three helpers), or after --max-min.

  python ota_run_monitor.py --round logs/ota_1.5.30_to_1.5.31_xxx [--max-min 45] [--no-keep] [--no-push-warn-sec 120]

Prints: stage changes (time, stage, state, native-install state, ...), owner changes, [OTA_RX] ACCEPTED/REJECTED, errors; and a warning when no push
has reached the device (no [OTA_RX]) after --no-push-warn-sec seconds, then every 5 minutes.  Own helpers only are stopped; nothing else is touched.
The GR port must be free. After DONE run: python ota_check.py post --target <version>
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

if not sys.stdout.isatty():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
OTA = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent
PROBLEM = re.compile(r'OTA_RX|SNAPSHOT|ERROR|error|traceback|REFUSED|REJECT|DATA_')


class Tail:
    def __init__(self, path):
        self.path, self.pos = Path(path), 0

    def lines(self):
        if not self.path.exists():
            return []
        with open(self.path, 'rb') as f:
            f.seek(self.pos)
            data = f.read()
            self.pos = f.tell()
        return data.decode('utf-8', 'replace').splitlines()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--round', required=True)
    ap.add_argument('--max-min', type=float, default=45)
    ap.add_argument('--no-keep', action='store_true')
    ap.add_argument('--no-push-warn-sec', type=float, default=120)
    a = ap.parse_args()
    rd = Path(a.round)
    rd.mkdir(parents=True, exist_ok=True)
    beacon, owner = rd / 'run_vuart.txt', rd / 'run_owner_gr.txt'
    env = dict(os.environ, PYTHONIOENCODING='utf-8', YP_RAW_LOG=str(rd / 'keep.log'))
    cmds = []
    if not a.no_keep:
        cmds.append(([sys.executable, str(BENCH / 'keep_cat1.py'), str(int(a.max_min + 15))], rd / 'keep_out.log'))
    cmds.append(([sys.executable, str(OTA / 'cat1_vuart_log.py'), '--log', str(beacon), '--min', str(int(a.max_min + 15))], rd / 'vuart_out.log'))
    cmds.append(([sys.executable, str(OTA / 'gr_owner_watch.py'), '--target', 'CAT1', '--max-min', str(int(a.max_min))], owner))
    procs = []
    for c, out in cmds:
        procs.append(subprocess.Popen(c, stdout=open(out, 'w', encoding='utf-8'), stderr=subprocess.STDOUT, env=env))
    print('监控已启动：', rd, '（保电' + ('关' if a.no_keep else '开') + '），最长', a.max_min, '分钟', flush=True)
    tb, to = Tail(beacon), Tail(owner)
    last, got_rx, t0, next_warn, done_at = None, False, time.time(), a.no_push_warn_sec, None
    try:
        while time.time() - t0 < a.max_min * 60:
            time.sleep(1)
            for line in tb.lines():
                if '[OTA] B ' in line:
                    p = line.split()
                    if len(p) >= 14:
                        ph = 'WAIT' if p[4] in ('PREPARING', 'PAUSED') else p[4]
                        key = (ph, p[6], p[10], p[12])
                        if key != last:
                            print(p[0], p[4], p[6], 'N=' + p[10], p[11], 'S=' + p[-1] if len(p) > 14 else '', flush=True)
                            last = key
                    continue
                if PROBLEM.search(line):
                    if 'OTA_RX' in line:
                        got_rx = True
                    print('!!', line[:160], flush=True)
            for line in to.lines():
                if 'owner gen' in line:
                    print('OWNER', line[:150], flush=True)
                if line.startswith('END owner COMPLETE') and done_at is None:
                    done_at = time.time()
                    print('DONE owner COMPLETE for CAT1：OTA 走完了。接下来：python tools/ota/bench/ota_check.py post --target <版本>', flush=True)
            if done_at and time.time() - done_at > 20:
                break
            if not got_rx and time.time() - t0 > next_warn:
                print(f'!! {int(time.time() - t0)} 秒了设备还没有收到推送（没有 [OTA_RX]）：查后台推送状态、IMEI、目标版本；已经 ACCEPTED 的不要重推', flush=True)
                next_warn += 300
        else:
            print('END 超时，没有看到 owner COMPLETE：去看 run_vuart.txt 最后几行', flush=True)
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        print('监控已停止，保电和日志进程已结束', flush=True)


if __name__ == '__main__':
    main()
