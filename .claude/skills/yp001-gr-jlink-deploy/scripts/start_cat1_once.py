# SAM | 2026-10-28 18:55 +08:00 | One user-authorized CAT1 PWRKEY pulse via J-Link (from logs/r6_query_readonly_20261027/start_cat1_once.py) because the GR OTA gate denies `cat1_power key` while the owner is INSTALL_PENDING. Masked PWRKEY output only; no Flash/owner/OTA changes.
# Usage: python -I start_cat1_once.py <round_log_dir>   (refuses to run twice for the same directory)
from pathlib import Path
import ctypes, struct, time, json, sys

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
j = ctypes.CDLL(r'C:\Program Files\SEGGER\JLink\JLink_x64.dll'); j.JLINKARM_Open.restype = ctypes.c_char_p
assert not (out / 'cat1_start.json').exists(), 'DO_NOT_REPEAT_START'
opened = False; pulsed = False; result = {}


def read32(a):
    b = ctypes.create_string_buffer(b'\xcd' * 4, 4); rc = j.JLINKARM_ReadMem(a, 4, b); assert rc in (0, 4); assert b.raw != b'\xcd' * 4
    return struct.unpack('<I', b.raw)[0]


def write32(a, v):
    b = ctypes.create_string_buffer(struct.pack('<I', v), 4); rc = j.JLINKARM_WriteMem(a, 4, b); assert rc in (0, 4)


try:
    err = j.JLINKARM_Open(); opened = True; assert not err, err
    b = ctypes.create_string_buffer(256); assert j.JLINKARM_ExecCommand(b'Device = Cortex-M4', b, 256) == 0
    assert j.JLINKARM_TIF_Select(1) == 0; j.JLINKARM_SetSpeed(4000); assert j.JLINKARM_Connect() == 0
    assert not j.JLINKARM_IsHalted(), 'GR_MUST_BE_RUNNING'
    ctl = read32(0x4000a1ec); mux = read32(0x4000ee50); over = read32(0x4000a1f4); rail = read32(0x40010004); oe = read32(0x40010010)
    result = {'before': {'aon_ctrl1': hex(ctl), 'mux': hex(mux), 'override': hex(over), 'rail_output': hex(rail), 'rail_enable': hex(oe)}}
    # Rail GPIO6 must already be on (send `cat1_power on` first); PWRKEY is AON_GPIO0 via Q4 inverter, MUX7, released output.
    assert rail & 64 and oe & 64, 'RAIL_NOT_ENABLED'; assert mux & 15 == 7 and not over & 0x10000, 'PWRKEY_NOT_GPIO7'
    assert not ctl & 1 and not ctl & 0x100, 'PWRKEY_NOT_RELEASED_OUTPUT'
    baseline = ctl & 0xffff
    # Record once before asserting; exceptions after assertion always release and are not auto-retried.
    (out / 'cat1_start.json').write_text(json.dumps(dict(result, status='RESERVED'), indent=2)); pulsed = True
    write32(0x4000a1ec, baseline | 0x100); time.sleep(1.6)
    write32(0x4000a1ec, read32(0x4000a1ec) & 0xfeff); pulsed = False
    result.update(status='PULSE_COMPLETED', after_ctrl1=hex(read32(0x4000a1ec)), flash_written=False, ota_started=False)
    (out / 'cat1_start.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))
finally:
    if pulsed:
        try: write32(0x4000a1ec, read32(0x4000a1ec) & 0xfeff)
        except Exception: pass
    if opened: j.JLINKARM_Close()
