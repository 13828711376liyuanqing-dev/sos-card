"""SAM | 2026-11-13 00:17 +08:00 | Check GUI capture sessions against deterministic meter data."""
import csv
from pathlib import Path
import queue
import threading
import unittest
import uuid

import c2_meter_gui


class DisplayFilterTests(unittest.TestCase):
    def test_exponential_smoothing_reduces_jitter_and_converges(self):
        display = c2_meter_gui.DisplayFilter(1.0)
        self.assertEqual(display.update({"current_ma": 4.0}, 0), {"current_ma": 4.0})
        value = display.update({"current_ma": 50.0}, 0.1)["current_ma"]
        self.assertGreater(value, 4.0)
        self.assertLess(value, 10.0)
        self.assertAlmostEqual(display.update({"current_ma": 4.0}, 20)["current_ma"], 4.0, places=5)

    def test_disabled_filter_follows_input(self):
        display = c2_meter_gui.DisplayFilter(0)
        display.update({"current_ma": 4.0}, 0)
        self.assertEqual(display.update({"current_ma": 50.0}, 0.1)["current_ma"], 50.0)


class SessionTests(unittest.TestCase):
    def setUp(self):
        folder = Path(__file__).resolve().parents[2] / "logs" / "c2_meter_tests"
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / (uuid.uuid4().hex + ".csv")

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_capture_logs_all_samples_and_releases_meter_on_stop(self):
        stop = threading.Event()
        events = queue.SimpleQueue()

        class Meter:
            closed = False

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.closed = True

            def read(self):
                stop.set()
                return [dict(timestamp_utc="2026-11-13T00:00:00+00:00", sample_index=i,
                             voltage_v=5.1, current_a=0.004, current_ma=4.0, power_w=0.0204)
                        for i in range(4)]

        meter = Meter()
        c2_meter_gui.capture(stop, events, self.path, lambda: meter)
        with self.path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 4)
        self.assertEqual(float(rows[0]["current_ma"]), 4.0)
        self.assertTrue(meter.closed)
        messages = []
        while not events.empty():
            messages.append(events.get())
        self.assertEqual(messages[-1][0], "done")
        self.assertEqual(messages[-1][1]["samples"], 4)
        self.assertIsNone(messages[-1][1]["error"])

    def test_connection_error_reaches_interface_and_keeps_existing_file(self):
        def fail():
            raise OSError("C2 unavailable")

        self.path.write_text("existing", encoding="utf-8")
        events = queue.SimpleQueue()
        c2_meter_gui.capture(threading.Event(), events, self.path, fail)
        self.assertEqual(self.path.read_text(encoding="utf-8"), "existing")
        done = events.get()
        self.assertEqual(done[0], "done")
        self.assertIn("C2 unavailable", done[1]["error"])


if __name__ == "__main__":
    unittest.main()
