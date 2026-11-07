"""SAM | 2026-10-26 +08:00 | Decode RAM evidence without executing firmware or authorizing an OTA."""
from pathlib import Path
import argparse
import hashlib
import json
import struct

UART_HALF_FIFO_US = 64 * 10 / 460800 * 1_000_000


def timing(first, second):
    if len(first) != 32 or len(second) != 32:
        raise ValueError("ADC_TIMING_SIZE")
    keys = ("sequence", "count", "status", "clock_hz", "cycles", "last_us", "max_us", "valid")
    result = dict(zip(keys, struct.unpack("<8I", second)))
    stable = first == second and result["sequence"] > 0 and result["sequence"] % 2 == 0
    derived = result["cycles"] * 1_000_000 // result["clock_hz"] if result["clock_hz"] else None
    valid = (stable and result["count"] > 0 and result["valid"] == 1 and result["status"] == 0
             and result["cycles"] > 0 and derived == result["last_us"]
             and result["max_us"] >= result["last_us"])
    result.update(stable_read=stable, usable_duration=valid, uart_half_fifo_budget_us=UART_HALF_FIFO_US)
    result["whole_call_upper_bound_within_budget"] = valid and result["max_us"] < UART_HALF_FIFO_US
    result["scope"] = "Total conversion call; an over-budget total does not by itself prove an over-budget PRIMASK interval."
    return result


def outer_denial(data):
    if len(data) != 40:
        raise ValueError("OUTER_DENIAL_SIZE")
    keys = ("sequence", "count", "token", "kind", "epoch", "owner_phase", "mask", "gate_bits", "battery", "observed_ms")
    values = dict(zip(keys, struct.unpack("<10I", data)))
    if values["sequence"] == 0:
        return {"committed":False}
    if values["sequence"] != 1 or not values["count"]:
        raise ValueError("OUTER_DENIAL_COMMIT")
    bits = values["gate_bits"]
    expected = (0 if bits & 1 else 1) | (bits & 14) | (0 if bits & 16 else 16)
    if values["mask"] != expected or not expected:
        raise ValueError("OUTER_DENIAL_INCONSISTENT")
    reasons = [name for bit, name in enumerate(("unknown", "alarm", "call", "activity", "peer")) if expected & (1 << bit)]
    return dict(values, committed=True, reasons=reasons)


def uart_fault(data):
    if len(data) != 44:
        raise ValueError("UART_FIRST_FAULT_SIZE")
    words = struct.unpack("<11I", data)
    if words[0] == 0:
        return {"committed":False}
    if words[0] != 0x55415254:
        raise ValueError("UART_FIRST_FAULT_MAGIC")
    keys = ("magic", "source", "driver_error", "rearm_result", "observed_ms", "rx_before", "rx_after", "read_index", "write_index", "dropped", "rx_bytes")
    return dict(zip(keys, words), committed=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    path = args.folder
    identity_verified = False
    if (path / "readback_plan.json").is_file():
        plan = json.loads((path / "readback_plan.json").read_text())
        installed = (path / "installed_app.bin").read_bytes()
        if len(installed) != plan["app_bytes"] or hashlib.sha256(installed).hexdigest() != plan["app_sha256"]:
            raise ValueError("DEVICE_IMAGE_DOES_NOT_MATCH_NEW_SYMBOLS")
        identity_verified = True
    result = {"adc":timing((path / "adc_first.bin").read_bytes(), (path / "adc_second.bin").read_bytes()),
              "outer_denial":outer_denial((path / "outer_denial.bin").read_bytes()),
              "uart_first_fault":uart_fault((path / "uart_first_fault.bin").read_bytes()),
              "device_image_matches_new_symbols":identity_verified,
              "ota_authorized_by_decoder":False}
    (path / "decoded_evidence.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
