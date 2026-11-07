"""SAM | 2026-10-24 +08:00 | Reject unsupported lab claims without accessing devices."""
import copy
import hashlib
from pathlib import Path
import unittest
import uuid

from check_lab_preparation import CASES, check


class PreparationTests(unittest.TestCase):
    def setUp(self):
        # SAM | 2026-10-24 +08:00 | Keep disposable test inputs in the workspace; Windows system TEMP has restricted ACLs here.
        parent = Path(__file__).resolve().parents[2] / 'logs/ota_lab_preparation_20261024/test_work'
        self.root = parent / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.addCleanup(self.clean)
        (self.root / 'source.lua').write_bytes(b'local x=1')
        self.source = {
            'schema': 1, 'device_actions': False, 'ota_passed': False,
            'kv_empty': None,
            'sources': [{'path': 'source.lua', 'sha256': hashlib.sha256(b'local x=1').hexdigest()}],
        }
        self.plan = {
            'schema': 1, 'execution_mode': 'preparation_only',
            'spare_board_available': False, 'production_activation_enabled': False,
            'scenarios': [{'id': name, 'status': 'NOT_RUN', 'before_evidence': None,
                           'after_evidence': None} for name in CASES],
        }

    def clean(self):
        # Only remove the one known fixture and its now-empty directory.
        (self.root / 'source.lua').unlink(missing_ok=True)
        self.root.rmdir()

    def test_valid_preparation_never_accepts_device_ota(self):
        r = check(self.root, self.source, self.plan)
        self.assertTrue(r['local_preparation_ok'])
        self.assertFalse(r['device_ota_accepted'])
        self.assertIn('NO_SPARE_BOARD', r['device_blockers'])
        self.assertIn('DEVICE_TESTS_NOT_RUN', r['device_blockers'])

    def test_false_pass_claim_rejected(self):
        self.plan['scenarios'][1]['status'] = 'PASS'
        r = check(self.root, self.source, self.plan)
        self.assertFalse(r['local_preparation_ok'])
        self.assertIn('DEVICE_CLAIM_NOT_VALIDATED', r['errors'])

    def test_source_drift_detected(self):
        (self.root / 'source.lua').write_bytes(b'local x=2')
        r = check(self.root, self.source, self.plan)
        self.assertFalse(r['local_preparation_ok'])
        self.assertIn('SOURCE_CHANGED:source.lua', r['errors'])

    def test_incomplete_or_duplicate_cases_rejected(self):
        for cases in [self.plan['scenarios'][:-1], self.plan['scenarios'] + self.plan['scenarios'][:1]]:
            plan = copy.deepcopy(self.plan)
            plan['scenarios'] = cases
            self.assertIn('CASE_SET_INVALID', check(self.root, self.source, plan)['errors'])

    def test_paths_cannot_escape_workspace(self):
        for path in ['../outside', str(self.root / 'source.lua'), 'C:/outside', '..\\outside']:
            self.source['sources'][0]['path'] = path
            self.assertIn('SOURCE_PATH_INVALID', check(self.root, self.source, self.plan)['errors'])

    def test_missing_source_or_malformed_input_does_not_pass(self):
        (self.root / 'source.lua').unlink()
        self.assertFalse(check(self.root, self.source, self.plan)['local_preparation_ok'])
        for source, plan in [(None, self.plan), (self.source, []), ({}, self.plan)]:
            self.assertFalse(check(self.root, source, plan)['local_preparation_ok'])

    def test_no_empty_kv_assumption_or_activation_override(self):
        self.source['kv_empty'] = True
        self.plan['production_activation_enabled'] = True
        r = check(self.root, self.source, self.plan)
        self.assertIn('PREPARATION_SCOPE_INVALID', r['errors'])

    def test_supplied_evidence_is_not_silently_accepted(self):
        self.plan['scenarios'][0]['before_evidence'] = {'data_ok': True}
        self.assertIn('DEVICE_CLAIM_NOT_VALIDATED', check(self.root, self.source, self.plan)['errors'])

    def test_added_lua_file_invalidates_frozen_source_set(self):
        directory = self.root / 'Air780EGH'
        directory.mkdir()
        extra = directory / 'added.lua'
        try:
            self.source['root_lua_count'] = 0
            self.assertTrue(check(self.root, self.source, self.plan)['local_preparation_ok'])
            extra.write_bytes(b'return {}')
            self.assertIn('ROOT_LUA_SET_CHANGED', check(self.root, self.source, self.plan)['errors'])
        finally:
            extra.unlink(missing_ok=True)
            directory.rmdir()


if __name__ == '__main__':
    unittest.main()
