"""SAM | 2026-10-26 +08:00 | Prepare bounded read-only J-Link commands from matching new symbols; never execute them or start an OTA."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
PAIR = ROOT / "firmware_releases/gr_adc_resync_20261026"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    manifest = PAIR / "paired_downloads.json"
    if not manifest.is_file():
        raise SystemExit("AWAIT_MATCHING_NEW_GR_AND_BOOT_ARTIFACTS")
    binding = json.loads(manifest.read_text())
    signed = PAIR / "baseline/baseline_signed.bin"
    assert hashlib.sha256(signed.read_bytes()).hexdigest() == binding["app_sha256"]
    assert signed.stat().st_size == binding["app_bytes"] <= 442368
    symbols = (PAIR / "baseline/symbols.txt").read_text()
    addresses = {}
    for name, size in (("g_yp001_adc_timing",32),("yp001_ota_quiet_denial",40),
                       ("g_cat_uart_first_fault",44),("g_cat_uart_recovery",36)):
        rows = [line for line in symbols.splitlines() if re.search(r"\b"+name+r"\s+0x",line) and "Data" in line]
        assert len(rows) == 1 and int(rows[0].split()[-1],16) == size, name
        address = int(re.search(r"\b"+name+r"\s+(0x[\da-fA-F]+)",rows[0]).group(1),16)
        assert 0x20000000 <= address < 0x20080000-size
        addresses[name] = address
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y%m%d_%H%M%S")
    out = (args.out or ROOT / ("logs/gr_adc_resync_20261026/readback_"+stamp)).resolve()
    assert not out.exists(), "PRESERVE_PRIOR_READBACK"
    out.mkdir(parents=True)
    reads = [("installed_app.bin",0x202000,binding["app_bytes"]),
             ("adc_first.bin",addresses["g_yp001_adc_timing"],32),
             ("adc_second.bin",addresses["g_yp001_adc_timing"],32),
             ("outer_denial.bin",addresses["yp001_ota_quiet_denial"],40),
             ("uart_first_fault.bin",addresses["g_cat_uart_first_fault"],44),
             ("uart_recovery.bin",addresses["g_cat_uart_recovery"],36)]
    commands = [f'savebin "{out / name}",0x{address:08X},0x{size:X}' for name,address,size in reads]
    (out / "read_evidence.jlink").write_text("\n".join(commands+["exit", ""]),encoding="ascii")
    plan = {"pair_manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "app_sha256":binding["app_sha256"],"app_bytes":binding["app_bytes"],
            "symbols_sha256":hashlib.sha256((PAIR / "baseline/symbols.txt").read_bytes()).hexdigest(),
            "addresses":{k:hex(v) for k,v in addresses.items()},"device_commands_executed":False,
            "precondition":"Confirm normal GR CLI and CAT1 rail/startup under the existing power redline before any UART test.",
            "no_reset_halt_or_write_commands":True,"ota_authorized":False}
    (out / "readback_plan.json").write_text(json.dumps(plan,indent=2),encoding="utf-8")
    print(json.dumps({"folder":str(out),"prepared_only":True,"device_commands_executed":False},indent=2))


if __name__ == "__main__":
    main()
