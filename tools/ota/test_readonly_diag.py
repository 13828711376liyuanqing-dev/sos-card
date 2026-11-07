"""SAM | 2026-10-24 +08:00 | A diagnostic ZIP reader has no GR grant, durable proof, FS writes or native installation authority."""
import unittest
import hashlib
import test_zip_bundle as fixture
import test_http_range as http_fixture


class ReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.BundleTests()
        self.f.setUp()
        self.lua = self.f.lua
        self.lua.globals().py_begin = lambda kind: hashlib.sha256() if kind == b'SHA256' else hashlib.md5()

    def open_diag(self):
        self.lua.execute(b'''
        local function denied()error('production callback reached')end
        p.owns=denied;p.owns_bundle=denied;p.completed=denied
        p.save_archive_proof=denied;p.archive_verified=denied;p.free_bytes=denied
        r,err=M.open_diagnostic(p,input);assert(r,err)
        ''')

    def test_no_authority_and_full_component_hashes(self):
        self.open_diag()
        self.lua.execute(b'''
        assert(r:summary().diagnostic_only and not r:summary().device_installable)
        local cp,e=r:component_port('GR5526',1,{});assert(not cp and e=='DIAGNOSTIC_ONLY')
        local ok,e=r:diagnostic_step();assert(not ok and e=='ARCHIVE_MD5_UNVERIFIED')
        assert(scan())
        local result
        for i=1,600 do
          local ok,info=r:diagnostic_step();assert(ok,tostring(info))
          if info.stage=='COMPLETE' then result=info;break end
        end
        assert(result and result.gr_verified and result.cat_verified and result.install_enabled==false)
        ''')
        self.assertIsNone(self.f.proof)

    def test_pause_stops_without_network(self):
        self.open_diag()
        self.assertIs(self.lua.eval(b'scan()'), True)
        self.f.allowed = False
        before = len(self.f.reads)
        self.assertEqual(self.lua.eval(b'r:diagnostic_step()'), (False, b'BUSINESS_PAUSED'))
        self.assertEqual(len(self.f.reads), before)
        self.f.allowed = True
        self.assertIs(self.lua.eval(b'(function() local ok=r:diagnostic_step();return ok end)()'), True)

    def test_component_change_after_preflight_rejected(self):
        self.open_diag()
        self.assertIs(self.lua.eval(b'scan()'), True)
        c = self.lua.eval(b"r:component('GR5526')")
        at = c[b'offset']
        data = bytearray(self.f.data)
        data[at] ^= 1
        self.f.data = bytes(data)
        self.lua.execute(b'''
        local rejected=false
        for i=1,600 do local ok,e=r:diagnostic_step()
          if not ok then assert(e=='COMPONENT_DIGEST');rejected=true;break end
        end
        assert(rejected)
        local ok,e=r:diagnostic_step();assert(not ok and e=='DIAGNOSTIC_REJECTED')
        ''')

    def test_production_reader_cannot_call_diagnostic_api(self):
        self.f.opened()
        self.assertEqual(self.lua.eval(b'r:diagnostic_step()'), (False, b'DIAGNOSTIC_ONLY'))
        self.assertFalse(self.lua.eval(b'r:summary().diagnostic_only'))

    def test_diagnostic_transport_does_not_certify_production_gate(self):
        f = http_fixture.HttpRangeTests()
        f.setUp()
        f.lua.execute('''
        deps.native_rx_limit_verified=false
        local r,e=M.new(deps);assert(not r and e=='HTTP_NATIVE_CONTRACT')
        p=assert(M.new_diagnostic(deps));assert(deps.native_rx_limit_verified==false)
        local r,e=get();assert(r and r.body=='DATA',tostring(e))
        local r,e=M.new(deps);assert(not r and e=='HTTP_NATIVE_CONTRACT')
        ''')


if __name__ == '__main__':
    unittest.main()
