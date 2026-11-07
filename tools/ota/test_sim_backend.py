"""SAM | 2026-10-21 +08:00 | Verify local runner limits and honest failure reporting."""
import importlib.util
from pathlib import Path
import uuid
import unittest
import threading
import http.client
import json
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('backend', Path(__file__).parent/'sim_backend/server.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)

class Tests(unittest.TestCase):
    # SAM | 2026-10-21 +08:00 | Inject evidence failures without touching production sources.
    def test_source_drift_rejects_success(self):
        folder = backend.ROOT/'logs/ota_sim_backend_tests'/uuid.uuid4().hex
        def fake(command, **kwargs):
            return backend.subprocess.CompletedProcess(command, 0, 'PASS')
        with patch.object(backend, 'source_hashes', side_effect=[{'a': 'old'}, {'a': 'new'}]):
            report = backend.run_suites(['layout'], folder, execute=fake)
        self.assertFalse(report['passed'])
        self.assertFalse(report['source_unchanged'])

    def test_timeout_retains_output_and_continues(self):
        folder = backend.ROOT/'logs/ota_sim_backend_tests'/uuid.uuid4().hex
        calls = []
        def fake(command, **kwargs):
            calls.append(command)
            if len(calls) == 1:
                raise backend.subprocess.TimeoutExpired(command, 180, output=b'last checkpoint 117')
            return backend.subprocess.CompletedProcess(command, 0, 'PASS next suite')
        report = backend.run_suites(['cat_manager', 'layout'], folder, execute=fake)
        self.assertEqual(len(calls), 2)
        self.assertFalse(report['passed'])
        self.assertTrue(report['results'][1]['passed'])
        self.assertIn('last checkpoint 117', report['results'][0]['log'])

    def test_evidence_includes_test_harness(self):
        hashes = backend.source_hashes()
        for name in ('tools/ota/sim_backend/server.py', 'tools/ota/test_gr_flash.py',
                     'tools/ota/test_gr_flash.c', 'tools/ota/test_cat_manager.py'):
            self.assertIn(name, hashes)

    def test_unknown_suite(self):
        with self.assertRaises(ValueError):
            backend.selected_suites(['../main.lua'])

    def test_failure_does_not_become_success(self):
        with self.subTest():
            folder = backend.ROOT/'logs/ota_sim_backend_tests'/uuid.uuid4().hex
            def fake(command, **kwargs):
                return backend.subprocess.CompletedProcess(command, 2, 'failure evidence')
            report = backend.run_suites(['cat_manager'], Path(folder), execute=fake)
            self.assertFalse(report['passed'])
            self.assertFalse(report['device_verified'])
            self.assertEqual(report['results'][0]['exit_code'], 2)

    def test_timeout_is_failure(self):
        with self.subTest():
            folder = backend.ROOT/'logs/ota_sim_backend_tests'/uuid.uuid4().hex
            def fake(command, **kwargs):
                raise backend.subprocess.TimeoutExpired(command, 1)
            report = backend.run_suites(['cat_manager'], Path(folder), execute=fake)
            self.assertFalse(report['passed'])

    def test_empty_is_not_pass(self):
        with self.assertRaises(ValueError):
            backend.selected_suites([])

# SAM | 2026-10-21 +08:00 | Exercise real HTTP dispatch on an isolated ephemeral port; never touch the user's running console.
class HttpTests(unittest.TestCase):
    def setUp(self):
        backend.STATE.update(running=False, report=None, error=None)
        self.server = backend.ThreadingHTTPServer(('127.0.0.1', 0), backend.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, body, token=True, host=None):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-OTA-Token'] = backend.TOKEN
        if host:
            headers['Host'] = host
        try:
            c.request('POST', '/api/run', body=body, headers=headers)
            r = c.getresponse()
            return r.status, r.read()
        finally:
            c.close()

    def test_auth_and_input(self):
        self.assertEqual(self.request(b'{}', token=False)[0], 403)
        self.assertEqual(self.request(b'{}', host='untrusted.invalid')[0], 403)
        for body in (b'{}', b'[]', b'null', b'{', b'{"suites":[]}', b'{"suites":["unknown"]}'):
            self.assertEqual(self.request(body)[0], 400)
        self.assertFalse(backend.STATE['running'])

    def test_duplicate_run_is_409(self):
        entered, release = threading.Event(), threading.Event()
        def blocked(names):
            entered.set()
            release.wait(3)
            with backend.LOCK:
                backend.STATE['running'] = False
        try:
            with patch.object(backend, 'worker', blocked):
                body = json.dumps({'suites': ['layout']}).encode()
                self.assertEqual(self.request(body)[0], 202)
                self.assertTrue(entered.wait(1))
                self.assertEqual(self.request(body)[0], 409)
        finally:
            release.set()

    def test_worker_exception_clears_busy(self):
        backend.STATE['running'] = True
        with patch.object(backend, 'run_suites', side_effect=RuntimeError('injected failure')):
            backend.worker(['layout'])
        self.assertFalse(backend.STATE['running'])
        self.assertIsNone(backend.STATE['report'])
        self.assertEqual(backend.STATE['error'], 'injected failure')

if __name__ == '__main__':
    unittest.main()
