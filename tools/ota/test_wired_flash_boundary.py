"""SAM | 2026-11-07 +08:00 | Assert guard placement and probe selection with all device/file writes modeled."""
import importlib.util
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('boundary_flasher', ROOT / 'tools/gr_release/GR_JLink_Flash/yp001_gr_jlink_flash.py')
flasher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(flasher)


class Boundary(unittest.TestCase):
    def test_guard_gets_actual_loaded_bytes_before_any_write_session(self):
        app = b'YP001_FW|GR5526|001.005.013|17|END' + b'\0' * 1000
        pre = bytearray(b'\xff' * 0x100000)
        offset = flasher.BOOT_ADDR - flasher.FLASH_BASE
        pre[offset:offset + flasher.DESC_OFF + 40] = bytes(flasher.DESC_OFF + 40)
        pre[offset + flasher.DESC_OFF - 108:offset + flasher.DESC_OFF - 96] = struct.pack('<3I', 1, 1, 1)
        pre[offset + flasher.DESC_OFF - 96:offset + flasher.DESC_OFF - 88] = flasher.LAYOUT_HASH
        checked = []
        def guard(actual_pre, actual_app, logdir):
            checked.append((actual_pre, actual_app))
            raise RuntimeError('GUARD_STOP')
        mutating = Mock(side_effect=AssertionError('write session reached before guard'))
        with patch.object(sys, 'argv', ['flasher', 'image.bin', '--yes', '--keep-name', '--probe-sn', '69407663']), \
             patch.object(Path, 'is_file', return_value=True), patch.object(Path, 'read_bytes', return_value=app), \
             patch.object(Path, 'mkdir'), patch.object(Path, 'write_bytes'), patch.object(flasher, 'install_device'), \
             patch.object(flasher, 'snapshot', return_value=bytes(pre)), patch.object(flasher, 'jlink', mutating), \
             patch.object(flasher, 'log'):
            with self.assertRaisesRegex(RuntimeError, 'GUARD_STOP'):
                flasher.main(preflight=guard)
        self.assertEqual(checked, [(bytes(pre), app)])
        mutating.assert_not_called()

    def test_every_jlink_session_uses_selected_serial(self):
        flasher.PROBE_SERIAL = 69407663
        result = SimpleNamespace(returncode=0, stdout='ok', stderr='')
        with patch.object(Path, 'write_text'), patch.object(flasher.subprocess, 'run', return_value=result) as run:
            code, _ = flasher.jlink('CORTEX-M4', ['exit'], Path('model.log'))
        self.assertEqual(code, 0)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('-SelectEmuBySN') + 1], '69407663')
        flasher.PROBE_SERIAL = None


if __name__ == '__main__':
    unittest.main()
