"""SAM | 2026-11-06 +08:00 | Synthetic evidence tests; never contact hardware."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib

SPEC = importlib.util.spec_from_file_location('gr_ota_probe', Path(__file__).with_name('gr_ota_probe.py'))
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def owner(generation=1, commit=0, version=2):
    raw = bytearray(b'\xff' * 4096)
    raw[:368] = bytes(368)
    struct.pack_into('<3I', raw, 0, 0x594F5432, generation, 5)
    raw[12] = 2
    raw[143:151] = b'GR5526\0\0'
    raw[151:157] = b'1.5.13'
    struct.pack_into('<4I', raw, 352, 0x80001000, 4096, 0, commit)
    struct.pack_into('<I', raw, 360, zlib.crc32(raw[:360]))
    if version == 1:
        struct.pack_into('<I', raw, 0, 0x594F5431)
        struct.pack_into('<2I', raw, 352, zlib.crc32(raw[:352]), commit)
        raw[360:368] = b'\xff' * 8
    return raw


def journal(generation=1, commit=0):
    words = [0] * 31
    words[:7] = [0x59504231, generation, probe.BOOT_LAYOUT_CRC, 1, 0, 0, 0]
    words[7] = words[17] = 4096
    words[27] = 1
    words[30] = commit
    raw = bytearray(struct.pack('<31I', *words))
    struct.pack_into('<I', raw, 116, zlib.crc32(raw[:116]))
    return raw + bytearray(b'\xff' * (4096 - 124))


class ProbeTests(unittest.TestCase):
    def decode(self, owners=None, journals=None, ram=None, **kwargs):
        return probe.decode_capture(owners or bytes(b'\xff' * 8192),
                                    journals or bytes(b'\xff' * 8192),
                                    ram if ram is not None else bytes(0x80000), **kwargs)

    def test_owner_offsets_crc_commit_and_latest(self):
        report = self.decode(owners=owner(3) + owner(4, commit=0xffffffff))
        self.assertEqual(report['owner'][0]['target'], 'GR5526')
        self.assertEqual(report['owner'][0]['version'], '1.5.13')
        self.assertEqual(report['owner'][0]['total'], 4096)
        self.assertEqual(report['owner'][0]['durable'], 4096)
        self.assertEqual(report['owner_latest']['generation'], 3)
        self.assertFalse(report['owner'][1]['valid'])
        bad = owner(5)
        bad[50] ^= 1
        report = self.decode(owners=owner(3) + bad)
        self.assertFalse(report['owner'][1]['crc_ok'])
        self.assertIsNone(report['owner_latest'])  # firmware fails closed on corrupt peer

    def test_owner_v1_and_equal_generation_conflict(self):
        report = self.decode(owners=owner(version=1) + bytearray(b'\xff' * 4096))
        self.assertTrue(report['owner_latest']['valid'])
        self.assertIsNone(report['owner_latest']['total'])
        other = owner()
        other[151] = ord('2')
        struct.pack_into('<I', other, 360, zlib.crc32(other[:360]))
        self.assertIsNone(self.decode(owners=owner() + other)['owner_latest'])

    def test_journal_latest_ignores_bad_crc_and_uncommitted(self):
        bad = journal(99)
        bad[50] ^= 1
        report = self.decode(journals=journal(2) + bad)
        self.assertEqual(report['journal_latest']['generation'], 2)
        self.assertFalse(report['journal'][1]['crc_ok'])
        self.assertEqual(self.decode(journals=journal(2) + journal(99, 0xffffffff))['journal_latest']['generation'], 2)
        self.assertIsNone(self.decode(journals=journal(2) + journal(2))['journal_latest'])

    def test_journal_bad_layout_and_non_head_magic_are_not_selected(self):
        bad = journal(99)
        struct.pack_into('<I', bad, 8, 0)
        struct.pack_into('<I', bad, 116, zlib.crc32(bad[:116]))
        blank = bytearray(b'\xff' * 4096)
        blank[124:248] = journal(100)[:124]
        report = self.decode(journals=bad + blank)
        self.assertIsNone(report['journal_latest'])
        self.assertTrue(report['journal'][0]['crc_ok'])
        self.assertFalse(report['journal'][0]['layout_crc_ok'])

    def test_scan_prevalidation_zero_versions_and_ambiguity(self):
        ram = bytearray(0x80000)
        for index, stage in enumerate(range(10, 17)):
            words = [1, 2, stage, 5, 2, 0xffffffff, 0] + [0] * 9
            struct.pack_into('<16I', ram, index * 64, *words)
        report = self.decode(ram=ram, epoch=5)
        self.assertEqual([c['stage'] for c in report['install_error_candidates']], list(range(10, 17)))
        self.assertIsNone(report['install_error'])
        self.assertIn('unverified', report['install_error_status'])
        self.assertEqual(len(self.decode(ram=ram[:64] + bytes(0x80000 - 64))['install_error_candidates']), 1)
        self.assertIsNone(self.decode(ram=ram[:64] + bytes(0x80000 - 64))['install_error'])

    def test_exact_zero_marker_retains_raw_words_and_provenance(self):
        ram = bytearray(0x80000)
        struct.pack_into('<16I', ram, 0x7ffc0, *([0, 3, 12] + [0] * 13))
        report = self.decode(ram=ram, install_error_address=0x2007ffc0, firmware_provenance='synthetic b16 map')
        self.assertEqual(report['install_error']['record_status'], 'absent_marker')
        self.assertEqual(report['install_error']['raw16'][:3], [0, 3, 12])
        self.assertEqual(report['firmware_provenance'], 'synthetic b16 map')

    def test_exact_address_and_capture_lengths_rejected(self):
        for address in (0x1ffffffc, 0x20000001, 0x2007ffc4, 0x20080000):
            with self.assertRaises(ValueError):
                self.decode(install_error_address=address)
        with self.assertRaises(ValueError):
            probe.decode_capture(bytes(8191), bytes(8192), bytes(0x80000))

    def test_last_sram_record_scanned_and_epoch_filter_applied(self):
        ram = bytearray(0x80000)
        struct.pack_into('<16I', ram, 0x7ffc0, *([1, 1, 10, 5, 2, 0xffffffff, 0] + [0] * 9))
        self.assertEqual(self.decode(ram=ram, epoch=5)['install_error_candidates'][0]['addr'], '0x2007ffc0')
        self.assertEqual(self.decode(ram=ram, epoch=6)['install_error_candidates'], [])

    def test_offline_cli_never_invokes_jlink_and_preserves_evidence(self):
        raw = {'owner.bin': owner() * 2, 'journal.bin': bytes(b'\xff' * 8192), 'sram.bin': bytes(0x80000)}
        with patch.object(Path, 'read_bytes', lambda p: raw[p.name]), patch.object(Path, 'open', side_effect=AssertionError('write')), \
                patch.object(probe, 'dump', side_effect=AssertionError('hardware')), contextlib.redirect_stdout(io.StringIO()) as out:
            probe.main(['--offline-dir', 'synthetic-input', '--install-error-address', '0x20000000', '--firmware-provenance', 'synthetic'])
        self.assertEqual(json.loads(out.getvalue())['install_error']['record_status'], 'absent_marker')

    def test_live_output_directory_never_overwrites_existing(self):
        with patch.object(Path, 'mkdir', side_effect=FileExistsError('exists')), \
                patch.object(probe, 'dump', side_effect=AssertionError('hardware')), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                probe.main(['--output-dir', 'synthetic-existing'])

    def test_live_capture_retains_directory_and_does_not_use_temporary_context(self):
        raw = {'owner.bin': owner() * 2, 'journal.bin': journal() * 2, 'sram.bin': bytes(0x80000)}
        with patch.object(Path, 'mkdir') as mkdir, patch.object(Path, 'read_bytes', lambda p: raw[p.name]), \
                patch.object(probe, 'dump', return_value='00000000') as dump, \
                patch.object(probe.tempfile, 'TemporaryDirectory', side_effect=AssertionError('would delete evidence')), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            probe.main(['--output-dir', 'synthetic-new'])
        mkdir.assert_called_once_with(parents=True, exist_ok=False)
        dump.assert_called_once_with(Path('synthetic-new'))
        self.assertEqual(json.loads(out.getvalue())['capture_mode'], 'live')

    def test_existing_json_report_rejected_before_hardware(self):
        with patch.object(Path, 'exists', return_value=True), patch.object(probe, 'dump', side_effect=AssertionError('hardware')), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                probe.main(['--json', 'synthetic-existing.json'])


if __name__ == '__main__':
    unittest.main()
