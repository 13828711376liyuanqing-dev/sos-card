"""SAM | 2026-11-13 +08:00 | Verify captured USB sample decoding and framing."""
import unittest
from unittest.mock import patch
import ctypes as ct

import c2_meter


FRAME = bytes.fromhex(
    "ee043937d00737d00737d00737d007120e00790d00790d00790d00"
    "1b001b001d001d0028002800260026004e004e004e004b000b0b0b0b0b0b0b0b0151ff00"
)


class DecoderTests(unittest.TestCase):
    def test_captured_voltage_current_units(self):
        samples = c2_meter.decode_frame(FRAME)
        self.assertEqual(len(samples), 4)
        self.assertAlmostEqual(samples[0]["voltage_v"], 5.12055)
        self.assertAlmostEqual(samples[0]["current_ma"], 36.02)
        self.assertAlmostEqual(samples[1]["current_a"], 0.03449)
        self.assertAlmostEqual(samples[0]["power_w"], 5.12055 * 0.03602)

    def test_reject_truncated_or_wrong_frame(self):
        for frame in (FRAME[:-1], b"\x00" + FRAME[1:], FRAME[:-2] + b"\x00\x00"):
            with self.assertRaises(ValueError):
                c2_meter.decode_frame(frame)

    def test_stream_fragmentation_and_resynchronization(self):
        decoder = c2_meter.FrameDecoder()
        self.assertEqual(decoder.feed(b"noise" + FRAME[:25]), [])
        self.assertEqual(decoder.feed(FRAME[25:] + FRAME), [FRAME, FRAME])

    def test_resync_after_bad_terminator(self):
        decoder = c2_meter.FrameDecoder()
        self.assertEqual(decoder.feed(FRAME[:-2] + b"xx" + FRAME), [FRAME])


class TransportTests(unittest.TestCase):
    def test_timeout_validation(self):
        for timeout in (0, -1, 2**32):
            with self.assertRaises(ValueError):
                c2_meter.C2Meter(timeout_ms=timeout)

    def test_failed_read_raises_instead_of_returning_old_samples(self):
        class FailedUsb:
            def WinUsb_ReadPipe(self, *args):
                ct.set_last_error(121)
                return False

        meter = c2_meter.C2Meter()
        meter.usb = FailedUsb()
        with self.assertRaises(OSError) as result:
            meter.read()
        self.assertEqual(result.exception.winerror, 121)

    def test_open_is_exclusive_and_cleanup_runs_when_policy_fails(self):
        class FakeKernel:
            closed = []

            def CreateFileW(self, *args):
                self.share = args[2]
                return 123

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return True

        class FakeUsb:
            freed = []

            def WinUsb_Initialize(self, file, interface):
                interface._obj.value = 456
                return True

            def WinUsb_SetPipePolicy(self, *args):
                ct.set_last_error(87)
                return False

            def WinUsb_Free(self, interface):
                self.freed.append(interface.value)
                return True

        kernel, usb = FakeKernel(), FakeUsb()
        with patch.object(c2_meter, "windows_apis", return_value=(None, kernel, usb)), \
                patch.object(c2_meter, "list_devices", return_value=["C2"]):
            with self.assertRaises(OSError):
                with c2_meter.C2Meter():
                    self.fail("Failed initialization must not enter the context")
        self.assertEqual(kernel.share, 0)
        self.assertEqual(kernel.closed, [123])
        self.assertEqual(usb.freed, [456])


if __name__ == "__main__":
    unittest.main()
