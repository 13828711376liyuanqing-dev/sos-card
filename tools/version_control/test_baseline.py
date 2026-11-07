"""SAM | 2026-11-07 09:20 +08:00 | Exercise non-overwrite and tamper detection with synthetic files only."""
import json
import os
from pathlib import Path
import stat
import uuid
import unittest
from unittest.mock import patch

import baseline


class BaselineTests(unittest.TestCase):
    def setUp(self):
        # Retain synthetic evidence; Windows sandbox temporary-directory ACLs are not writable here.
        self.root = Path(__file__).resolve().parents[2] / 'logs/version_control_20261107/tests' / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        (self.root / 'source').mkdir()
        (self.root / 'source/main.c').write_text('original', encoding='utf-8')
        self.spec = {'release_id': 'test', 'verification': {'host': 'pending'}, 'rollback_plan': 'source-only; no user data',
                     'inputs': [{'path': 'source', 'destination': 'source'}]}

    def test_copy_and_duplicate_output(self):
        out = self.root / 'frozen'
        baseline.freeze(self.root, self.spec, out)
        self.assertEqual(baseline.verify(out, baseline.sha(out / 'manifest.json'))['files'][0]['sha256'], baseline.sha(self.root / 'source/main.c'))
        with self.assertRaises(ValueError):
            baseline.freeze(self.root, self.spec, out)

    def test_missing_input_creates_nothing(self):
        self.spec['inputs'][0]['path'] = 'missing'
        with self.assertRaises(ValueError):
            baseline.freeze(self.root, self.spec, self.root / 'frozen')
        self.assertFalse((self.root / 'frozen').exists())

    def test_detects_tamper_and_extra_file(self):
        out = self.root / 'frozen'
        baseline.freeze(self.root, self.spec, out)
        (out / 'source/main.c').write_text('changed!', encoding='utf-8')
        with self.assertRaises(ValueError):
            baseline.verify(out, baseline.sha(out / 'manifest.json'))
        (out / 'source/main.c').write_text('original', encoding='utf-8')
        (out / 'extra').touch()
        with self.assertRaises(ValueError):
            baseline.verify(out, baseline.sha(out / 'manifest.json'))

    def test_paths_keys_and_duplicate_targets(self):
        for path in ('../source', '/source', 'D:/source', 'source/../source', '.git/config', '.AWS/credentials', 'ota_KEYS/private.txt', '.aws./credentials', 'OTA_keys /private.bin'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                baseline.safe_path(self.root, path)
        self.spec['inputs'].append(self.spec['inputs'][0].copy())
        with self.assertRaises(ValueError):
            baseline.freeze(self.root, self.spec, self.root / 'frozen')

    def test_metadata_tamper_requires_original_anchor(self):
        out = self.root / 'frozen'
        baseline.freeze(self.root, self.spec, out)
        anchor = baseline.sha(out / 'manifest.json')
        m = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        m['verification']['host'] = 'passed'
        (out / 'manifest.json').write_text(json.dumps(m), encoding='utf-8')
        with self.assertRaises(ValueError):
            baseline.verify(out, anchor)

    def test_mixed_case_private_directory_is_omitted(self):
        (self.root / 'source/ota_KEYS').mkdir()
        (self.root / 'source/ota_KEYS/private.bin').write_bytes(b'synthetic')
        m = baseline.freeze(self.root, self.spec, self.root / 'frozen')
        self.assertEqual(len(m['files']), 1)

    def test_empty_and_overlap_refused(self):
        self.spec['inputs'] = []
        with self.assertRaises(ValueError):
            baseline.freeze(self.root, self.spec, self.root / 'frozen')
        self.spec['inputs'] = [{'path': 'source', 'destination': 'source'}]
        # Do not allow a snapshot to recursively contain itself.
        with self.assertRaises(ValueError):
            baseline.freeze(self.root, self.spec, self.root / 'source/frozen')

    def test_private_keys_and_cache_are_not_delivered(self):
        (self.root / 'source/sign.key').write_text('synthetic', encoding='utf-8')
        (self.root / 'source/Objects').mkdir()
        (self.root / 'source/Objects/cache.d').touch()
        out = self.root / 'frozen'
        m = baseline.freeze(self.root, self.spec, out)
        self.assertEqual(len(m['files']), 1)
        self.assertEqual(m['omitted_private_files'], ['source/sign.key'])

    # SAM | 2026-11-07 09:44 +08:00 | Exercise drift with restored metadata and real Windows reparse points, not just success-path copies.
    def test_same_size_restored_mtime_drift_retains_incomplete_output(self):
        original = baseline.copy_one
        def change_after_copy(root, output, pair):
            result = original(root, output, pair)
            source = pair[0]
            before = source.stat()
            source.write_bytes(b'modified')
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            return result
        out = self.root / 'frozen'
        with patch.object(baseline, 'copy_one', change_after_copy), self.assertRaisesRegex(ValueError, 'drift'):
            baseline.freeze(self.root, self.spec, out)
        self.assertTrue((out / 'source/main.c').exists())
        self.assertFalse((out / 'manifest.json').exists())

    def test_file_set_changed_during_copy(self):
        original = baseline.copy_one
        def add_after_copy(root, output, pair):
            result = original(root, output, pair)
            (root / 'source/late.c').write_text('late', encoding='utf-8')
            return result
        with patch.object(baseline, 'copy_one', add_after_copy), self.assertRaisesRegex(ValueError, 'file set changed'):
            baseline.freeze(self.root, self.spec, self.root / 'frozen')

    def test_source_modified_during_stream_with_restored_mtime(self):
        constructor = baseline.hashlib.sha256
        source = self.root / 'source/main.c'
        before = source.stat()
        changed = False
        class MutatingDigest:
            def __init__(self):
                self.digest = constructor()
            def update(self, chunk):
                nonlocal changed
                self.digest.update(chunk)
                if not changed:
                    changed = True
                    source.write_bytes(b'modified')
                    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            def hexdigest(self):
                return self.digest.hexdigest()
        with patch.object(baseline.hashlib, 'sha256', MutatingDigest), self.assertRaisesRegex(ValueError, 'drift|changed'):
            baseline.freeze(self.root, self.spec, self.root / 'frozen')
        self.assertTrue(changed)

    def test_nested_target_collision_creates_nothing(self):
        self.spec['inputs'] = [{'path': 'source/main.c', 'destination': 'a'},
                               {'path': 'source/main.c', 'destination': 'a/main.c'}]
        with self.assertRaisesRegex(ValueError, 'collision'):
            baseline.freeze(self.root, self.spec, self.root / 'frozen')
        self.assertFalse((self.root / 'frozen').exists())

    def test_real_directory_link_even_in_excluded_directory_is_refused(self):
        linked = self.root / 'source/Objects'
        if os.name == 'nt':
            import _winapi
            _winapi.CreateJunction(str(self.root / 'source'), str(linked))
        else:
            linked.symlink_to(self.root / 'source', target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Link|junction'):
            baseline.freeze(self.root, self.spec, self.root / 'frozen')

    def test_reparse_attribute_and_link_mode_are_refused(self):
        from types import SimpleNamespace
        for mode, attributes in ((stat.S_IFREG, 0x400), (stat.S_IFLNK, 0)):
            with self.assertRaises(ValueError):
                baseline.checked(SimpleNamespace(st_mode=mode, st_file_attributes=attributes), self.root)

    def test_linked_manifest_refused_before_read(self):
        out = self.root / 'frozen'
        baseline.freeze(self.root, self.spec, out)
        original = baseline.safe_path
        def refuse_manifest(root, value):
            if value == 'manifest.json':
                raise ValueError('Link/junction refused')
            return original(root, value)
        with patch.object(baseline, 'safe_path', refuse_manifest), patch.object(baseline, 'sha', side_effect=AssertionError('must not read linked manifest')):
            with self.assertRaisesRegex(ValueError, 'Link'):
                baseline.verify(out, 'anchor')

    def test_verify_rechecks_file_set_after_hash(self):
        out = self.root / 'frozen'
        baseline.freeze(self.root, self.spec, out)
        anchor = baseline.sha(out / 'manifest.json')
        original = baseline.sha
        def add_during_hash(path):
            result = original(path)
            if path.name == 'main.c':
                (out / 'late_extra').write_bytes(b'late')
            return result
        with patch.object(baseline, 'sha', add_during_hash), self.assertRaisesRegex(ValueError, 'changed during verification'):
            baseline.verify(out, anchor)

    def test_verify_rechecks_reparse_points_after_hash(self):
        out = self.root / 'frozen'
        baseline.freeze(self.root, self.spec, out)
        anchor = baseline.sha(out / 'manifest.json')
        original = baseline.sha
        def link_during_hash(path):
            result = original(path)
            if path.name == 'main.c':
                linked = out / 'late_link'
                if os.name == 'nt':
                    import _winapi
                    _winapi.CreateJunction(str(self.root / 'source'), str(linked))
                else:
                    linked.symlink_to(self.root / 'source', target_is_directory=True)
            return result
        with patch.object(baseline, 'sha', link_during_hash), self.assertRaisesRegex(ValueError, 'Link|junction'):
            baseline.verify(out, anchor)


if __name__ == '__main__':
    unittest.main()
