"""SAM | 2026-10-26 +08:00 | Reject torn/uncommitted diagnostics and distinguish total latency from critical-section latency."""
import struct
from decode_gr_adc_uart_evidence import timing, outer_denial, uart_fault


def main():
    sample = struct.pack("<8I", 2, 1, 0, 96_000_000, 57600, 600, 700, 1)
    result = timing(sample, sample)
    assert result["usable_duration"] and result["whole_call_upper_bound_within_budget"]
    torn = struct.pack("<8I", 3, 1, 0, 96_000_000, 57600, 600, 700, 1)
    assert not timing(torn, torn)["usable_duration"]
    assert not timing(sample, torn)["stable_read"]
    for words in ((2,1,0,0,57600,600,700,1),(2,1,0,96_000_000,0,0,700,1),
                  (2,1,1,96_000_000,57600,600,700,1),(2,1,0,96_000_000,57600,600,700,0)):
        data = struct.pack("<8I", *words)
        assert not timing(data, data)["usable_duration"]
    slow = struct.pack("<8I", 4, 2, 0, 96_000_000, 192000, 2000, 2000, 1)
    assert timing(slow,slow)["usable_duration"] and not timing(slow,slow)["whole_call_upper_bound_within_budget"]
    assert outer_denial(bytes(40)) == {"committed":False}
    denied = struct.pack("<10I",1,2,9,2,4,1,16,1,88,1000)
    assert outer_denial(denied)["reasons"] == ["peer"]
    assert uart_fault(bytes(44)) == {"committed":False}
    fault = struct.pack("<11I",0x55415254,1,2,0xffffffff,1000,16,16,0,0,0,100)
    assert uart_fault(fault)["driver_error"] == 2
    try:
        outer_denial(struct.pack("<10I",1,1,9,2,4,1,16,17,88,1000))
        raise AssertionError("INCONSISTENT_DENIAL_ACCEPTED")
    except ValueError:
        pass
    print("PASS decoder: stable ADC evidence only; zero snapshots remain uncommitted; exact peer reason; total delay never labeled a measured interrupt mask")


if __name__ == "__main__":
    main()
