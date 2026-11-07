"""SAM | 2026-11-07 +08:00 | Scope guards are tested without serial, J-Link, or filesystem mutations; CRC parsing has its own suite."""
import copy
import hashlib
import io
import contextlib
import sys
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'maintenance'))
import check_wired_retire as guard


class Guards(unittest.TestCase):
    def setUp(self):
        self.profile = dict(job_id='a' * 64, hash='b' * 64, epoch=6, owner_generation=302,
                            boot_generation=658, source_version='1.5.12', source_build=16,
                            target_version='1.5.13', old_image_bytes=380136,
                            new_image_sha256=hashlib.sha256(b'signed-fixture').hexdigest())
        self.raw = bytearray(8192)
        self.raw[13:78] = b'a' * 64 + b'\0'
        self.raw[78:143] = b'b' * 64 + b'\0'
        self.report = dict(owner_latest=dict(addr='0x2f9000', generation=302, epoch=6,
                            phase='PREPARED', target='GR5526', version='1.5.13',
                            source='1.5.12', total=380136, durable=380136),
                           journal_latest=dict(generation=658, state='CONFIRMED'))
        self.gr = '[FW_VERSION] YP001_FW|GR5526|001.005.012|16|END\n[BUSINESS] link=1 net=4 alarm=0 call=0\n'
        self.cat = '00:00:01 COM21 [OTA] B RECOVERY_HOLD nil/0 SPENT activation_validation_failed N IDLE IDLE nil nil\n'

    def run_guard(self):
        def read_bytes(path):
            return bytes(self.raw) if path.name == 'owner.bin' else b'signed-fixture' if path.name == 'image.bin' else b''
        def read_text(path, **kwargs):
            return self.gr if path.name == 'gr.txt' else self.cat
        with patch.object(Path, 'read_bytes', read_bytes), patch.object(Path, 'read_text', read_text), \
                patch.object(guard, 'decode_capture', return_value=self.report):
            return guard.validate(Path('capture'), self.profile, 'image.bin', 'gr.txt', 'cat.txt')

    def test_exact_failed_task_is_reviewable_without_write_authority(self):
        result = self.run_guard()
        self.assertTrue(result['ready_for_operator_confirmation'])
        self.assertFalse(result['device_actions'])

    def test_all_other_owners_or_progress_refuse(self):
        original = copy.deepcopy(self.report)
        for key, value in dict(generation=303, epoch=7, phase='INSTALL_PENDING', target='CAT1',
                               version='1.5.14', source='1.5.11', total=380137, durable=0).items():
            with self.subTest(key=key):
                self.report = copy.deepcopy(original)
                self.report['owner_latest'][key] = value
                with self.assertRaises(ValueError): self.run_guard()

    def test_hash_and_job_scope_refuse(self):
        for pos in (13, 78):
            with self.subTest(pos=pos):
                self.raw[pos] ^= 1
                with self.assertRaises(ValueError): self.run_guard()
                self.raw[pos] ^= 1

    def test_active_or_changed_boot_refuse(self):
        for state in ('PREPARED', 'INSTALL', 'TRIAL', 'ROLLBACK'):
            self.report['journal_latest']['state'] = state
            with self.assertRaises(ValueError): self.run_guard()
        self.report['journal_latest'] = dict(state='CONFIRMED', generation=659)
        with self.assertRaises(ValueError): self.run_guard()

    def test_invalid_crc_selection_refuses(self):
        for key in ('owner_latest', 'journal_latest'):
            original = self.report[key]
            self.report[key] = None
            with self.assertRaises(ValueError): self.run_guard()
            self.report[key] = original

    def test_wrong_application_or_missing_cli_refuses(self):
        for text in ('', self.gr.replace('001.005.012', '001.005.013'), self.gr.replace('|16|', '|17|')):
            original = self.gr; self.gr = text
            with self.assertRaises(ValueError): self.run_guard()
            self.gr = original

    def test_busy_or_offline_business_refuses(self):
        for before, after in [('alarm=0', 'alarm=1'), ('call=0', 'call=2'), ('link=1', 'link=0'), ('net=4', 'net=1')]:
            original = self.gr; self.gr = original.replace(before, after)
            with self.assertRaises(ValueError): self.run_guard()
            self.gr = original

    def test_no_live_cat_or_native_installer_active_refuses(self):
        original = self.cat
        for text in ('', original.replace('N IDLE IDLE', 'N INSTALLING WRITING'), original.replace('SPENT', 'RUNNING')):
            self.cat = text
            with self.assertRaises(ValueError): self.run_guard()

    def test_changed_image_refuses(self):
        self.profile['new_image_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.run_guard()

    # SAM | 2026-11-07 +08:00 | Bind liveness to ordered port events and bind approval to the flasher's actual pre-erase bytes.
    def test_beacon_before_same_port_loss_refuses(self):
        self.cat += '00:00:02 PC COM21 lost (CAT1 reboot?)\n'
        with self.assertRaises(ValueError): self.run_guard()
        self.cat += '00:00:03 PC COM21 opened\n'
        with self.assertRaises(ValueError): self.run_guard()

    def test_beacon_after_reconnect_accepts(self):
        old = self.cat
        self.cat += '00:00:02 PC COM21 lost (CAT1 reboot?)\n00:00:03 PC COM21 opened\n' + old
        self.assertTrue(self.run_guard()['ready_for_operator_confirmation'])

    def test_unrelated_unused_port_loss_does_not_invalidate_live_port(self):
        self.cat += '00:00:02 PC COM23 lost (CAT1 reboot?)\n'
        self.assertEqual(guard.live_cat_beacon(self.cat), self.cat.splitlines()[0])

    # SAM | 2026-11-07 +08:00 | Appended logger runs cannot inherit a previous run's module response or connection state.
    def test_new_empty_logger_run_discards_previous_beacon(self):
        self.cat += '00:00:02 PC VUART LOG end\n00:00:03 PC VUART LOG start ports=COM21,COM23\n00:00:04 PC VUART LOG end\n'
        self.assertIsNone(guard.live_cat_beacon(self.cat))
        with self.assertRaises(ValueError): self.run_guard()

    def test_new_logger_run_accepts_only_new_beacon(self):
        old = self.cat
        self.cat += '00:00:02 PC COM21 lost (CAT1 reboot?)\n00:00:03 PC VUART LOG end\n00:00:04 PC VUART LOG start ports=COM21,COM23\n00:00:05 PC COM21 opened\n'
        self.assertIsNone(guard.live_cat_beacon(self.cat))
        self.cat += old
        self.assertEqual(guard.live_cat_beacon(self.cat), old.rstrip())
        self.assertTrue(self.run_guard()['ready_for_operator_confirmation'])

    def test_standalone_postflash_liveness_mode(self):
        with patch.object(Path, 'read_text', return_value='00:00:01 COM21 [OTA] B IDLE nil/0 AVAILABLE none N IDLE IDLE nil nil\n'), \
                patch.object(Path, 'stat', return_value=SimpleNamespace(st_mtime=995)), patch.object(guard.time, 'time', return_value=1000), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            guard.main(['--cat-online-log', 'cat.txt'])
        self.assertIn('cat_online', out.getvalue())

    def prepare_snapshot(self):
        self.pre = bytearray(b'\xff' * 0x100000)
        self.pre[0x2000:0x2000 + 377064] = b'A' * 377064
        self.pre[0xec000:0xf6000] = b'B' * 0xa000
        self.pre[0xf9000:0xfb000] = self.raw
        self.profile.update(old_running_bytes=377064, old_running_sha256=hashlib.sha256(b'A' * 377064).hexdigest(),
                            old_boot_sha256=hashlib.sha256(b'B' * 0xa000).hexdigest(),
                            protected_sha256=hashlib.sha256(self.pre[0x6e000:0x80000] + self.pre[0xfb000:0x100000]).hexdigest())

    def run_snapshot(self, now=1000, mtime=995):
        def decode(owner, journal, sram):
            self.assertEqual(owner, self.pre[0xf9000:0xfb000])
            self.assertEqual(journal, self.pre[0xf7000:0xf9000])
            self.assertEqual(sram, bytes(0x80000))
            return self.report
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('must use actual pre/app bytes')), \
                patch.object(Path, 'stat', return_value=SimpleNamespace(st_mtime=mtime)), \
                patch.object(Path, 'read_text', lambda p, **kwargs: self.gr if p.name == 'gr.txt' else self.cat), \
                patch.object(guard, 'decode_capture', side_effect=decode):
            return guard.validate_flash_snapshot(bytes(self.pre), b'signed-fixture', self.profile, 'gr.txt', 'cat.txt', now)

    def test_snapshot_validates_actual_flash_bytes_without_saved_capture(self):
        self.prepare_snapshot()
        self.assertTrue(self.run_snapshot()['flash_snapshot_validated'])

    def test_snapshot_mutated_a_boot_protected_or_app_refuses(self):
        self.prepare_snapshot()
        for offset in (0x2000, 0xec000, 0x6e000, 0xfb000):
            with self.subTest(offset=offset):
                self.pre[offset] ^= 1
                with self.assertRaises(ValueError): self.run_snapshot()
                self.pre[offset] ^= 1
        self.profile['new_image_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.run_snapshot()

    def test_snapshot_changed_owner_boot_and_stale_or_future_logs_refuse(self):
        self.prepare_snapshot()
        for key, value in [('owner_latest', None), ('journal_latest', None)]:
            previous = self.report[key]
            self.report[key] = value
            with self.assertRaises(ValueError): self.run_snapshot()
            self.report[key] = previous
        for mtime in (939.99, 1000.01):
            with self.subTest(mtime=mtime):
                with self.assertRaises(ValueError): self.run_snapshot(mtime=mtime)
        self.assertTrue(self.run_snapshot(mtime=940)['flash_snapshot_validated'])

    def test_snapshot_requires_complete_one_megabyte(self):
        self.prepare_snapshot()
        self.pre = self.pre[:-1]
        with self.assertRaises(ValueError): self.run_snapshot()


if __name__ == '__main__':
    unittest.main()
