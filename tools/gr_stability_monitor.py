"""SAM | 2026-11-04 +08:00 | Correlate UART boots and scheduled J-Link resets.

Run: python tools/gr_stability_monitor.py --port COM30 --allow-resets
Create STOP in the output directory to end monitoring without another reset.
"""
import argparse
import datetime
import json
import pathlib
import queue
import re
import struct
import subprocess
import threading
import time
import zlib

import serial


def business_quiet(line):
    fields = dict(re.findall(r'\b(link|net|alarm|call)=(\d+)\b', line))
    if fields.get('alarm') != '0':
        return False
    if fields.get('call') in ('0', '4', '5'):
        return True
    # SAM | 2026-11-04 +08:00 | User-authorized GR bench resets may include an offline CAT1.
    return fields.get('call') == '6' and fields.get('link') == '0' and fields.get('net') == '0'


def write_status(path, status):
    # SAM | 2026-11-04 +08:00 | Readers can briefly hold Windows rename targets open.
    text = json.dumps(status, ensure_ascii=False, indent=2)
    temporary = path.with_suffix('.tmp')
    for attempt in range(3):
        try:
            temporary.write_text(text, encoding='utf8')
            temporary.replace(path)
            return True
        except PermissionError:
            time.sleep(0.1)
    try:
        path.write_text(text, encoding='utf8')
        return True
    except PermissionError:
        return False


class BootTracker:
    def __init__(self):
        self.boots = 0
        self.unexpected = 0
        self.planned = 0
        self.expected_until = 0
        self.in_boot = False
        self.last_boot = -1000

    def arm(self, now):
        self.expected_until = now + 45

    def line(self, line, now):
        banner = '=== YP001 GR5526 BOOT / UART0 ===' in line
        fallback = '[ULTRA PRE-RESET]' in line or 'entering QF_run' in line
        new_boot = banner or (fallback and not self.in_boot)
        if new_boot:
            self.boots += 1
            self.last_boot = now
            if self.expected_until and now <= self.expected_until:
                self.planned += 1
            else:
                self.unexpected += 1
            self.expected_until = 0
            self.in_boot = True
        if 'entering QF_run' in line:
            self.in_boot = False
        return new_boot


def journal_safe(data):
    """Validate both coordinator pages using the firmware's V1/V2 CRC layout."""
    if len(data) != 8192:
        return False
    records = []
    for offset in (0, 4096):
        page = data[offset:offset + 4096]
        if page == b'\xff' * 4096:
            continue
        magic, generation = struct.unpack_from('<II', page)
        offsets = {0x594F5431: (352, 356), 0x594F5432: (360, 364)}.get(magic, ())
        matching = [offset for offset in offsets
                    if struct.unpack_from('<I', page, offset)[0] == zlib.crc32(page[:offset])]
        if len(matching) != 1 or not generation:
            return False
        crc_offset = matching[0]
        crc, commit = struct.unpack_from('<II', page, crc_offset)
        if crc != zlib.crc32(page[:crc_offset]) or commit != 0:
            return False
        if page[crc_offset + 8:] != b'\xff' * (4096 - crc_offset - 8):
            return False
        phase = struct.unpack_from('<I', page, 12)[0]
        records.append((generation, phase, page[:crc_offset]))
    if not records:
        return True
    if len(records) == 2 and records[0][0] == records[1][0] and records[0] != records[1]:
        return False
    return max(records, key=lambda item: item[0])[1] in (0, 4)


class Monitor:
    def __init__(self, args):
        self.args = args
        stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        self.directory = pathlib.Path(args.output) / stamp
        self.directory.mkdir(parents=True, exist_ok=False)
        self.events = (self.directory / 'events.jsonl').open('w', encoding='utf8', buffering=1)
        self.lines = queue.Queue()
        self.stop = threading.Event()
        self.tracker = BootTracker()
        self.started = time.monotonic()
        self.phase = 'baseline'
        self.block = ''
        self.serial_error = ''
        self.last_version = -1000
        self.last_business = -1000
        self.business_idle = False
        self.last_rx = -1000
        self.version = ''
        self.jlink_ok = 0
        self.jlink_failed = 0
        self.reset_attempts = 0
        self.completed_windows = 0
        self.counts = {'adc_invalid': 0, 'epd_timeout': 0, 'charger_fault': 0}
        self.reference_version = ''
        if args.baseline_evidence:
            evidence = json.loads(pathlib.Path(args.baseline_evidence).read_text(encoding='utf8'))
            if evidence['elapsed_s'] < 1800 or evidence['unexpected_boots'] or evidence['reset_attempts']:
                raise ValueError('baseline evidence must contain 30 minutes without any resets')
            self.reference_version = evidence['version']

    def note(self, kind, **values):
        event = {'time': datetime.datetime.now().astimezone().isoformat(),
                 'elapsed_s': round(time.monotonic() - self.started, 3), 'kind': kind, **values}
        self.events.write(json.dumps(event, ensure_ascii=False) + '\n')
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def receive(self):
        pending = b''
        try:
            with (self.directory / 'uart.raw').open('wb') as raw:
                while not self.stop.is_set():
                    chunk = self.port.read(8192)
                    if not chunk:
                        continue
                    raw.write(chunk)
                    raw.flush()
                    pending += chunk
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        self.lines.put((time.monotonic(), line.decode('utf8', 'replace').rstrip('\r')))
                    if len(pending) > 65536:
                        raise RuntimeError('UART line exceeded 64 KiB')
        except Exception as error:
            self.lines.put((time.monotonic(), 'HOST_SERIAL_ERROR ' + str(error)))
        finally:
            if pending:
                self.lines.put((time.monotonic(), pending.decode('utf8', 'replace')))

    def drain(self):
        with (self.directory / 'uart_timestamped.log').open('a', encoding='utf8') as log:
            while True:
                try:
                    at, line = self.lines.get_nowait()
                except queue.Empty:
                    break
                elapsed = at - self.started
                log.write(f'{elapsed:012.3f} {line}\n')
                self.last_rx = at
                if line.startswith('HOST_SERIAL_ERROR'):
                    self.serial_error = line
                    self.block = line
                if self.tracker.line(line, at):
                    self.note('boot', planned=self.tracker.planned,
                              unexpected=self.tracker.unexpected, marker=line)
                    if self.tracker.unexpected:
                        self.block = 'unexpected_boot'
                if '[FW_VERSION] YP001_FW|' in line:
                    self.last_version = at
                    self.version = line.strip()
                    if self.reference_version and self.version != self.reference_version:
                        self.block = 'firmware_changed_since_baseline'
                if '[BUSINESS] link=' in line:
                    self.last_business = at
                    self.business_idle = business_quiet(line)
                if any(word in line for word in ('INSTALL_PENDING', 'PREPARED', '[OTA_HOLD] 1', 'owner=OTA')):
                    self.block = 'ota_activity_observed'
                self.counts['adc_invalid'] += '[BAT] sample invalid=' in line
                self.counts['epd_timeout'] += 'EPD BUSY timeout' in line
                self.counts['charger_fault'] += 'AUTO BLOCKED:' in line

    def query(self):
        self.note('uart_query', commands=['fw_version', 'business status'])
        self.port.write(b'fw_version\r\n')
        time.sleep(0.15)
        self.port.write(b'business status\r\n')

    def jlink(self, commands, label):
        argv = [self.args.jlink, '-NoGui', '1', '-ExitOnError', '1', '-device',
                'Cortex-M4', '-if', 'SWD', '-speed', '100']
        log = self.directory / f'{time.monotonic_ns()}_{label}.log'
        try:
            result = subprocess.run(argv, input='connect\n' + commands + '\nexit\n',
                                    text=True, capture_output=True, timeout=20)
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            output = 'HOST_JLINK_TIMEOUT'
        log.write_text(output, encoding='utf8')
        ok = 'E000ED00 = 410FC241' in output.upper()
        if ok:
            self.jlink_ok += 1
        else:
            self.jlink_failed += 1
        self.note('jlink', ok=ok, label=label, log=log.name)
        return ok, output

    def save_status(self, result='running'):
        status = {'result': result, 'phase': self.phase,
                  'elapsed_s': round(time.monotonic() - self.started, 1),
                  'unexpected_boots': self.tracker.unexpected, 'planned_boots': self.tracker.planned,
                  'reset_attempts': self.reset_attempts, 'completed_windows': self.completed_windows,
                  'jlink_ok': self.jlink_ok, 'jlink_failed': self.jlink_failed,
                  'block': self.block, 'version': self.version, 'fault_counts': self.counts,
                  'last_rx_age_s': round(time.monotonic() - self.last_rx, 1)}
        if not write_status(self.directory / 'status.json', status):
            self.note('status_write_deferred', status=status)
        return status

    def reset(self):
        self.query()
        time.sleep(2)
        self.drain()
        now = time.monotonic()
        if self.block or now - self.last_version > 10 or now - self.last_business > 10 or not self.business_idle:
            self.block = self.block or 'no_fresh_idle_CLI_response'
            return False
        journal = (self.directory / f'ota_gate_{self.reset_attempts + 1}.bin').resolve()
        # SAM | 2026-11-04 +08:00 | J-Link interprets unprefixed lengths as hex.
        ok, _ = self.jlink(f'mem32 0xE000ED00 1\nsavebin "{journal}", 0x002F9000, 0x2000', 'reset_gate')
        self.drain()
        if not ok or not journal.exists() or not journal_safe(journal.read_bytes()):
            self.block = self.block or 'ota_journal_unknown_or_active'
            return False
        if self.block:
            return False
        self.reset_attempts += 1
        self.tracker.arm(time.monotonic())
        self.note('planned_reset_requested', number=self.reset_attempts)
        ok, output = self.jlink('mem32 0xE000ED00 1\nr\ng', 'planned_reset')
        self.drain()
        if not ok or 'Reset device via AIRCR.SYSRESETREQ' not in output:
            self.block = 'reset_command_unconfirmed'
            return False
        return True

    def run(self):
        self.port = serial.Serial(port=None, baudrate=115200, timeout=0.2,
                                  write_timeout=2, rtscts=False, dsrdtr=False)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = self.args.port
        self.port.open()
        receiver = threading.Thread(target=self.receive)
        receiver.start()
        self.started = time.monotonic()
        self.note('monitor_started', directory=str(self.directory.resolve()), port=self.args.port)
        if self.args.baseline_evidence:
            self.note('baseline_evidence_reused', path=self.args.baseline_evidence)
        next_poll = self.started
        baseline_end = self.started + self.args.baseline_minutes * 60
        end = baseline_end + 6 * self.args.interval_minutes * 60
        next_reset = baseline_end
        last_reset = None
        result = 'incomplete'
        try:
            while time.monotonic() < end:
                now = time.monotonic()
                self.drain()
                if (self.directory / 'STOP').exists():
                    self.block = 'operator_stop'
                    break
                if self.serial_error:
                    break
                if now >= next_poll:
                    self.query()
                    self.jlink('mem32 0xE000ED00 1\nmem32 0xE000EDF0 1\nmem32 0xE000ED28 2', 'poll')
                    self.drain()
                    next_poll = time.monotonic() + 60
                if now - self.last_version > 150 and now - self.started > 150:
                    self.block = self.block or 'CLI_heartbeat_missing'
                if self.tracker.expected_until and now > self.tracker.expected_until:
                    self.block = self.block or 'planned_boot_not_observed'
                if now >= baseline_end:
                    self.phase = 'reset_cycles' if not self.block else 'observation_after_failure'
                    if self.args.allow_resets and not self.block and now >= next_reset:
                        if last_reset is not None:
                            self.completed_windows += 1
                        if self.reset():
                            last_reset = time.monotonic()
                            next_reset = last_reset + self.args.interval_minutes * 60
                            end = next_reset + (6 - self.reset_attempts) * self.args.interval_minutes * 60
                        else:
                            self.note('automatic_resets_stopped', reason=self.block)
                self.save_status()
                time.sleep(0.2)
            if last_reset and time.monotonic() - last_reset >= self.args.interval_minutes * 60:
                self.completed_windows += 1
            self.drain()
            result = 'failed_or_incomplete' if self.block else 'completed'
        except Exception as error:
            self.block = f'{type(error).__name__}: {error}'
            result = 'failed_or_incomplete'
            self.note('host_error', error=self.block)
        finally:
            self.stop.set()
            receiver.join(timeout=3)
            self.port.close()
            self.drain()
            self.note('monitor_finished', **self.save_status(result))
            self.events.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM30')
    parser.add_argument('--jlink', default='C:/Program Files/SEGGER/JLink/JLink.exe')
    parser.add_argument('--output', default='logs/gr_stability')
    parser.add_argument('--allow-resets', action='store_true')
    parser.add_argument('--baseline-minutes', type=float, default=30)
    parser.add_argument('--interval-minutes', type=float, default=5)
    parser.add_argument('--baseline-evidence', help='Reuse a completed 30-minute baseline status.json')
    args = parser.parse_args()
    if args.baseline_minutes <= 0 or args.interval_minutes <= 0:
        parser.error('monitor durations must be positive')
    if args.baseline_evidence:
        args.baseline_minutes = 0
    Monitor(args).run()


if __name__ == '__main__':
    main()
