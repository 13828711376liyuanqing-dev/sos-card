"""SAM | 2026-11-07 09:31 +08:00 | Negative release-gate tests protect exact reviewed inputs."""
import copy
import json
from pathlib import Path
import shutil
import uuid
import unittest
from unittest.mock import patch
import release_gate as gate


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent / ('gate_fixture_' + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.maps = []
        for component, dest in [('gr', 'ble_app_uart_c'), ('cat1', 'Air780EGH'), ('sdk', 'SDK')]:
            base = f'firmware_releases/baselines/baseline/source/{component}'
            for d in (base, dest):
                (self.root / d).mkdir(parents=True)
                (self.root / d / 'input.txt').write_text('original')
            self.maps.append(dict(component=component, baseline=base, candidate=dest))
        (self.root / 'ble_app_uart_c/input.txt').write_text('candidate')
        self.hex = self.root / 'ble_app_uart_c/app.hex'
        self.hex.write_text('HEX')
        self.ev = self.root / 'logs/version_control_20261107/evidence.txt'
        self.ev.parent.mkdir(parents=True)
        self.ev.write_text('real review evidence fixture')
        before, after = gate.snapshot(self.root, self.maps)
        evidence = [dict(path=self.ev.relative_to(self.root).as_posix(), sha256=gate.file_hash(self.ev))]
        approval = dict(source_sha256=gate.digest(after), reviewer='test reviewer', reason='fixture only', evidence=evidence)
        self.frozen = self.root / 'firmware_releases/baselines/baseline/manifest.json'
        self.frozen_data = dict(schema='YP001_LOCAL_BASELINE_V1', release_id='baseline',
            source_alignment=copy.deepcopy(approval) | {'status': 'verified_build_inputs'},
            files=[dict(path='source/' + key, sha256=value) for key, value in before.items()])
        self.frozen.write_text(json.dumps(self.frozen_data))
        self.manifest = dict(baseline_manifest=dict(path=self.frozen.relative_to(self.root).as_posix(),
                             sha256=gate.file_hash(self.frozen)), schema_version=1, scan_policy=gate.SCAN_POLICY, baseline_id='baseline', candidate_id='candidate',
                             mappings=self.maps, baseline_files=before, candidate_files=after,
                             baseline_sha256=gate.digest(before), candidate_sha256=gate.digest(after),
                             changes=[dict(path=p, before_sha256=before.get(p), after_sha256=after.get(p),
                                           reviewer='test reviewer', reason='fixture change', evidence=evidence)
                                      for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)],
                             build_evidence=dict(approval, gr_hex_sha256=gate.file_hash(self.hex)), attestation=approval)

    def validate(self, manifest=None, findings=()):
        return gate.validate(self.root, manifest or self.manifest, self.root / 'Air780EGH',
                             self.root / self.maps[1]['baseline'], self.hex, findings)

    def test_exact_review_passes(self):
        self.assertEqual(self.validate()['candidate_sha256'], self.manifest['candidate_sha256'])

    def test_changed_gr_byte_invalidates(self):
        (self.root / 'ble_app_uart_c/input.txt').write_text('later')
        with self.assertRaises(gate.GateError): self.validate()

    def test_changed_sdk_byte_invalidates(self):
        (self.root / 'SDK/input.txt').write_text('later')
        with self.assertRaises(gate.GateError): self.validate()

    def test_evidence_byte_invalidates(self):
        self.ev.write_text('later')
        with self.assertRaises(gate.GateError): self.validate()

    def test_missing_change_is_rejected(self):
        self.manifest['changes'].pop()
        with self.assertRaises(gate.GateError): self.validate()

    def test_missing_review_subject_is_rejected(self):
        self.manifest['changes'][0]['reviewer'] = ' '
        with self.assertRaises(gate.GateError): self.validate()

    def test_hard_block_cannot_be_reviewed(self):
        for rule in ('R2 新建目录', 'R3 重启', 'R4 串口', 'R6 命令名', 'R7 require', 'R10 语法'):
            with self.subTest(rule=rule), self.assertRaises(gate.GateError):
                self.validate(findings=[('BLOCK', rule, 'input.txt', 'danger')])

    def test_r1_requires_exact_review(self):
        self.validate(findings=[('BLOCK', 'R1 OTA文件', 'input.txt', 'changed')])

    def test_absolute_and_escape_schema_paths_rejected(self):
        for bad in ('../SDK', '/SDK', 'C:/SDK', 'SDK/../SDK', 'SDK\\x'):
            m = copy.deepcopy(self.manifest)
            m['mappings'][2]['candidate'] = bad
            with self.subTest(path=bad), self.assertRaises(gate.GateError): self.validate(m)

    def test_missing_component_rejected(self):
        self.manifest['mappings'].pop()
        with self.assertRaises(gate.GateError): self.validate()

    def test_source_bound_build_and_attestation(self):
        for field in ('build_evidence', 'attestation'):
            m = copy.deepcopy(self.manifest)
            m[field]['source_sha256'] = '0' * 64
            with self.subTest(field=field), self.assertRaises(gate.GateError): self.validate(m)

    def test_hex_byte_invalidates(self):
        self.hex.write_text('later')
        with self.assertRaises(gate.GateError): self.validate()

    def test_symlink_rejected(self):
        link = self.root / 'SDK/link.txt'
        try: link.symlink_to(self.ev)
        except OSError: self.skipTest('host cannot create symlink')
        with self.assertRaises(gate.GateError): self.validate()

    def test_release_identity_reuse_rejected(self):
        out = self.root / 'firmware_releases/old'
        out.mkdir(parents=True)
        (out / 'run.json').write_text(json.dumps(dict(to_version='1.5.14', to_build=18)))
        with self.assertRaises(gate.GateError):
            gate.check_identity(out.parent, '1.5.14', 18, {'candidate_sha256': 'a'})

    def test_release_id_never_overwritten(self):
        out = self.root / 'existing'
        out.mkdir()
        with self.assertRaises(gate.GateError): gate.reserve_output(out)

    def test_flags_do_not_fabricate_review(self):
        import oneclick
        args = oneclick.build_parser().parse_args(['check', '--yes-attest', '--reviewed-ota-change', '--no-device'])
        state_file = self.root / 'fixture_state.json'
        state_file.write_text('{}')
        before = state_file.read_bytes()
        with patch.object(oneclick, 'STATE_FILE', state_file):
            with self.assertRaisesRegex(oneclick.Fail, '--review-manifest'):
                oneclick.run_all(args, check_only=True)
        self.assertEqual(state_file.read_bytes(), before)

    def test_empty_evidence_and_unbound_hex_rejected(self):
        for mutate in ('empty', 'hash'):
            m = copy.deepcopy(self.manifest)
            if mutate == 'empty': m['attestation']['evidence'] = []
            else: m['build_evidence']['gr_hex_sha256'] = '0' * 64
            with self.subTest(mutate=mutate), self.assertRaises(gate.GateError): self.validate(m)

    def test_inexact_review_hash_rejected(self):
        self.manifest['changes'][0]['after_sha256'] = '0' * 64
        with self.assertRaises(gate.GateError): self.validate()

    def test_artifact_identity_cannot_change(self):
        out = self.root / 'firmware_releases/old'
        out.mkdir(parents=True)
        identity = {'candidate_sha256': 'a'}
        (out / 'run.json').write_text(json.dumps(dict(to_version='1.5.14', to_build=18,
            input_identity=identity, artifact_identity={'package_sha256': 'old'})))
        gate.check_identity(out.parent, '1.5.14', 18, identity)
        with self.assertRaises(gate.GateError):
            gate.check_identity(out.parent, '1.5.14', 18, identity, {'package_sha256': 'new'})

    def test_frozen_baseline_reserves_version(self):
        out = self.root / 'firmware_releases/baselines/frozen'
        out.mkdir(parents=True)
        (out / 'manifest.json').write_text(json.dumps(dict(firmware=dict(gr_version='1.5.14', gr_build=18,
            cat_version='1.5.14', cat_build=18))))
        with self.assertRaises(gate.GateError):
            gate.check_identity(self.root / 'firmware_releases', '1.5.14', 18, {'candidate_sha256': 'a'})

    def test_done_requires_separate_device_evidence(self):
        import oneclick
        args = oneclick.build_parser().parse_args(['done', '--yes-attest'])
        state_file = self.root / 'fixture_state.json'
        state_file.write_text('{}')
        before = state_file.read_bytes()
        with patch.object(oneclick, 'STATE_FILE', state_file):
            with self.assertRaisesRegex(oneclick.Fail, 'device-evidence'):
                oneclick.cmd_done(args)
        self.assertEqual(state_file.read_bytes(), before)

    def test_link_detection_is_fail_closed_without_symlink_privilege(self):
        link = self.root / 'SDK/link.txt'
        link.write_text('fixture')
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda path: path == link or original(path)):
            with self.assertRaises(gate.GateError): self.validate()

    def test_missing_baseline_and_extra_review_rejected(self):
        m = copy.deepcopy(self.manifest)
        m['mappings'][0]['baseline'] = 'firmware_releases/missing'
        with self.assertRaises(gate.GateError): self.validate(m)
        m = copy.deepcopy(self.manifest)
        m['changes'].append(copy.deepcopy(m['changes'][0]))
        with self.assertRaises(gate.GateError): self.validate(m)

    def test_changed_cat1_byte_invalidates(self):
        (self.root / 'Air780EGH/input.txt').write_text('later')
        with self.assertRaises(gate.GateError): self.validate()

    def test_empty_evidence_file_rejected_even_with_matching_hash(self):
        self.ev.write_text('')
        record = dict(reviewer='test', reason='fixture', evidence=[dict(
            path=self.ev.relative_to(self.root).as_posix(), sha256=gate.file_hash(self.ev))])
        with self.assertRaises(gate.GateError): gate.evidence(self.root, record)

    def test_identical_release_content_can_be_compared(self):
        out = self.root / 'firmware_releases/old'
        out.mkdir(parents=True)
        identity, artifacts = {'candidate_sha256': 'a'}, {'package_sha256': 'same'}
        (out / 'run.json').write_text(json.dumps(dict(to_version='1.5.15', to_build=19,
            input_identity=identity, artifact_identity=artifacts)))
        gate.check_identity(out.parent, '1.5.15', 19, identity, artifacts)

    def test_windows_alias_and_private_evidence_paths_rejected(self):
        for name in ('SDK./file', 'SDK /file', '.GIT/config', '.aws./credentials',
                     'OTA_keys /secret', 'firmware_releases/Test_Keys/x', 'SDK/x.KEY'):
            with self.subTest(name=name), self.assertRaises(gate.GateError):
                gate.safe_path(self.root, name)

    def test_exclusions_are_case_insensitive_and_bound_to_digest(self):
        excluded = self.root / 'ble_app_uart_c/oBjEcTs'
        excluded.mkdir()
        (excluded / 'cache.txt').write_text('not an input')
        private = self.root / 'SDK/TeSt_KeYs'
        private.mkdir()
        (private / 'private.txt').write_text('private')
        self.validate()

    def test_malformed_manifest_rejected(self):
        with self.assertRaises(gate.GateError): self.validate(['not-an-object'])

    def device_fixture(self):
        identity = {'candidate_sha256': 'source', 'gr_hex_sha256': 'hex'}
        artifacts = {'package_sha256': 'package', 'gr_signed_sha256': 'signed'}
        lr = dict(to_version='1.5.15', to_build=19, md5='a' * 32,
                  input_identity=identity, artifact_identity=artifacts)
        proof = dict(schema_version=1, purpose='device_ota_acceptance', to_version='1.5.15',
                     to_build=19, package_md5='a' * 32, input_identity=identity, artifact_identity=artifacts,
                     reviewer='device fixture reviewer', reason='fixture only',
                     evidence=[dict(path=self.ev.relative_to(self.root).as_posix(), sha256=gate.file_hash(self.ev))],
                     observations=dict(gr=dict(version='1.5.15', build=19),
                         cat1=dict(version='1.5.15', build=19, native_phase='IDLE', outbox=0),
                         owner=dict(phase='COMPLETE', result='success', actual_version='1.5.15', target='CAT1'),
                         boot=dict(state='CONFIRMED')))
        return lr, proof

    def test_exact_device_evidence_accepts(self):
        lr, proof = self.device_fixture()
        gate.validate_device(self.root, proof, lr)

    def test_wrong_device_task_version_package_and_identity_reject(self):
        lr, proof = self.device_fixture()
        for field, value in [('to_version', '1.5.14'), ('to_build', 18), ('package_md5', 'b' * 32),
                             ('input_identity', {}), ('artifact_identity', {})]:
            wrong = copy.deepcopy(proof)
            wrong[field] = value
            with self.subTest(field=field), self.assertRaises(gate.GateError):
                gate.validate_device(self.root, wrong, lr)

    def test_wrong_device_observations_reject(self):
        lr, proof = self.device_fixture()
        for component, field, value in [('gr', 'version', '1.5.14'), ('cat1', 'build', 18),
            ('cat1', 'native_phase', 'INSTALLING'), ('cat1', 'outbox', 1),
            ('owner', 'phase', 'INSTALL_PENDING'), ('owner', 'result', 'fail'),
            ('owner', 'actual_version', '1.5.14'), ('owner', 'target', 'GR'), ('boot', 'state', 'TRIAL')]:
            wrong = copy.deepcopy(proof)
            wrong['observations'][component][field] = value
            with self.subTest(component=component, field=field), self.assertRaises(gate.GateError):
                gate.validate_device(self.root, wrong, lr)

    def test_unbound_historical_run_cannot_be_promoted(self):
        lr, proof = self.device_fixture()
        del lr['input_identity']
        with self.assertRaises(gate.GateError): gate.validate_device(self.root, proof, lr)

    def test_baseline_metadata_tamper_rejected(self):
        self.frozen_data['release_id'] = 'unreviewed'
        self.frozen.write_text(json.dumps(self.frozen_data))
        with self.assertRaises(gate.GateError): self.validate()

    def test_pending_source_alignment_cannot_publish(self):
        self.frozen_data['source_alignment']['status'] = 'pending'
        self.frozen.write_text(json.dumps(self.frozen_data))
        self.manifest['baseline_manifest']['sha256'] = gate.file_hash(self.frozen)
        with self.assertRaises(gate.GateError): self.validate()

    def test_baseline_inventory_cannot_alias_or_omit(self):
        self.frozen_data['files'].pop()
        self.frozen.write_text(json.dumps(self.frozen_data))
        self.manifest['baseline_manifest']['sha256'] = gate.file_hash(self.frozen)
        with self.assertRaises(gate.GateError): self.validate()

    def test_baseline_mapping_must_be_inside_frozen_root(self):
        src = self.root / self.maps[0]['baseline']
        dst = self.root / 'logs/version_control_20261107/alias_gr'
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        self.manifest['mappings'][0]['baseline'] = dst.relative_to(self.root).as_posix()
        with self.assertRaises(gate.GateError): self.validate()

    def test_cleanup_flags_rejected_before_device_or_tools(self):
        import oneclick
        for flag in ('--clean-ota-log', '--auto-prune'):
            args = oneclick.build_parser().parse_args(['check', flag])
            with patch.object(oneclick, 'dev_read') as device:
                with self.assertRaisesRegex(oneclick.Fail, '恢复方案'):
                    oneclick.run_all(args, check_only=True)
                device.assert_not_called()

    def test_invalid_review_never_calls_device(self):
        import oneclick
        (self.root / 'review.json').write_text('[]')
        args = oneclick.build_parser().parse_args(['check', '--review-manifest', 'review.json'])
        with patch.object(oneclick, 'PROJECT', self.root), patch.object(oneclick, 'dev_read') as device:
            with self.assertRaises(oneclick.Fail): oneclick.run_all(args, check_only=True)
            device.assert_not_called()

    def test_device_read_sends_only_queries(self):
        import oneclick
        from types import SimpleNamespace
        writes = []
        class SerialFixture:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def write(self, data): writes.append(data)
            def read(self, size):
                if not writes: return b''
                return (b'YP001_FW|GR5526|1.5.14|18|END' if writes[-1].startswith(b'fw_version')
                        else b'OTA_FS total=100 used=20 block=4096')
        fake = SimpleNamespace(Serial=lambda *args, **kwargs: SerialFixture())
        with patch.dict('sys.modules', serial=fake), patch.object(oneclick.time, 'sleep'):
            info, why = oneclick.dev_read('FIXTURE')
        self.assertEqual(info['version'], '1.5.14')
        self.assertEqual(writes, [b'fw_version\r\n', b'cat_at OTA_FS\r\n'])

    def test_done_rejects_mutated_source_or_deliverable(self):
        out = self.root / 'firmware_releases/run'
        target = out / 'work/target_source'
        target.mkdir(parents=True)
        (target / 'main.lua').write_text('fixture')
        for name in gate.DELIVERY_DIRS:
            folder = out / name
            folder.mkdir()
            (folder / 'artifact.txt').write_text('fixture')
        files = gate.tree_files(target, 'cat1')
        lr = dict(out=str(out), target_source=str(target), target_source_files=files,
                  target_source_sha256=gate.digest(files), artifact_files=gate.delivery_files(out))
        gate.verify_run_files(self.root, lr)
        (target / 'main.lua').write_text('changed')
        with self.assertRaises(gate.GateError): gate.verify_run_files(self.root, lr)
        (target / 'main.lua').write_text('fixture')
        (out / gate.DELIVERY_DIRS[0] / 'artifact.txt').write_text('changed')
        with self.assertRaises(gate.GateError): gate.verify_run_files(self.root, lr)

    def test_custom_output_root_cannot_hide_canonical_identity(self):
        out = self.root / 'firmware_releases/old'
        out.mkdir(parents=True, exist_ok=True)
        (out / 'run.json').write_text(json.dumps(dict(to_version='1.5.14', to_build=18)))
        with self.assertRaises(gate.GateError):
            gate.check_known_identity(self.root, self.root / 'custom_output', '1.5.14', 18, {'candidate_sha256': 'new'})

    def test_done_records_fixture_evidence_without_promoting_mutable_source(self):
        import oneclick
        lr, proof = self.device_fixture()
        lr.update(package='fixture.zip', target_source='fixture-source', sizes={})
        state_file = self.root / 'fixture_state.json'
        state_file.write_text(json.dumps(dict(last_run=lr, baseline_dir='immutable-baseline',
                                              attest=dict(confirmed_by_user=False))))
        (self.root / 'device.json').write_text(json.dumps(proof))
        args = oneclick.build_parser().parse_args(['done', '--device-evidence', 'device.json',
            '--device-reviewer', proof['reviewer'], '--device-reason', proof['reason']])
        with patch.object(oneclick, 'PROJECT', self.root), patch.object(oneclick, 'STATE_FILE', state_file), \
             patch.object(gate, 'verify_run_files') as verify, patch('builtins.print'):
            oneclick.cmd_done(args)
            verify.assert_called_once()
        saved = json.loads(state_file.read_text())
        self.assertEqual(saved['baseline_dir'], 'immutable-baseline')
        self.assertFalse(saved['attest']['confirmed_by_user'])
        self.assertEqual(saved['last_success']['promotion'], 'pending_immutable_baseline')

    def test_pending_baseline_rejects_before_source_hashing(self):
        self.frozen_data['source_alignment']['status'] = 'pending'
        self.frozen.write_text(json.dumps(self.frozen_data))
        self.manifest['baseline_manifest']['sha256'] = gate.file_hash(self.frozen)
        with patch.object(gate, 'snapshot', side_effect=AssertionError('must not scan pending baseline')), \
             patch.object(gate, 'tree_files', side_effect=AssertionError('must not hash pending source')):
            with self.assertRaisesRegex(gate.GateError, 'pending/unproven'):
                self.validate()


if __name__ == '__main__': unittest.main()
