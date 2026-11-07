"""SAM | 2026-10-24 +08:00 | Full-stream ZIP preflight keeps metadata only; component reads restart network and retain normal signatures/ownership."""
import hashlib
import unittest
import test_zip_bundle as fixture


class SequentialTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.BundleTests();self.f.setUp();self.lua=self.f.lua
        self.lua.globals().py_begin=lambda kind:hashlib.sha256() if kind==b'SHA256' else hashlib.md5()
        self.opens=self.closes=0
        self.fail=False
        self.change=False
        def open_stream(url):
            self.assertEqual(url.decode(),'http://example.invalid/stream.zip')
            self.opens+=1
            data=self.f.data
            if self.change and self.opens>1:
                with __import__('zipfile').ZipFile(__import__('io').BytesIO(data)) as z:
                    info=z.getinfo('GR5526/payload.bin')
                    at=info.header_offset+30+len(info.filename)
                changed=bytearray(data);changed[at]^=1;data=bytes(changed)
            position=0
            def read(n):
                nonlocal position
                self.assertLessEqual(n,16384)
                if self.fail and position>=100:return None,b'NETWORK_ERROR'
                value=data[position:position+min(n,113)]
                position+=len(value);return value
            def close():
                self.closes+=1;return True
            return self.lua.table_from({b'read':read,b'close':close,b'status':200})
        self.lua.globals().py_stream=open_stream
        self.lua.execute(b'''
        input.url='http://example.invalid/stream.zip'
        p.open_stream=function(url)return py_stream(url)end
        S=require('ota_seq_zip')
        ''')

    def diag(self):
        self.lua.execute(b'''
        local function denied()error('production side effect')end
        p.owns=denied;p.owns_bundle=denied;p.completed=denied
        p.save_archive_proof=denied;p.archive_verified=denied;p.free_bytes=denied
        r,err=S.open_diagnostic(p,input);assert(r,err)
        ''')

    def test_metadata_only_then_serial_components_no_whole_zip_file(self):
        self.diag()
        self.assertEqual(self.opens,1)
        self.lua.execute(b'''
        local s=r:summary()
        assert(s.transport_mode=='SEQUENTIAL_200' and s.network_restart_from_zero and s.metadata_bytes<=35000)
        assert(not s.device_installable and scan())
        local done
        for n=1,600 do local ok,v=r:diagnostic_step();assert(ok,tostring(v));if v.stage=='COMPLETE' then done=true;break end end
        assert(done);r:close()
        ''')
        self.assertEqual(self.opens,3)  # preflight, GR, then CAT: not one new GET per block
        self.assertEqual(self.opens,self.closes)
        self.assertIsNone(self.f.proof)

    def test_disconnect_restarts_new_preflight_without_false_resume(self):
        self.fail=True
        self.lua.execute(b'local r,e=S.open_diagnostic(p,input);assert(not r and e)')
        self.assertEqual(self.opens,self.closes)
        self.fail=False
        self.diag()
        self.assertEqual(self.opens,2)

    def test_changed_component_on_second_get_is_rejected(self):
        self.change=True;self.diag()
        self.lua.execute(b'''
        assert(scan());local rejected=false
        for n=1,600 do local ok,e=r:diagnostic_step();if not ok then assert(e=='COMPONENT_DIGEST');rejected=true;break end end
        assert(rejected);r:close()
        ''')
        self.assertEqual(self.opens,self.closes)

    def test_pause_during_component_closes_stream(self):
        self.diag()
        self.lua.execute(b"assert(scan());local ok=r:diagnostic_step();assert(ok)")
        self.lua.execute(b"p.can_read=function()return false end;local ok,e=r:diagnostic_step();assert(not ok and e=='BUSINESS_PAUSED');r:close()")
        self.assertEqual(self.opens,self.closes)

    # SAM | 2026-10-24 +08:00 | Shared preflight finalization must still persist and read back production proof.
    def test_production_preflight_saves_and_reads_back_snapshot_proof(self):
        self.lua.execute(b"r,err=S.open(p,input);assert(r,err);local ok,e=r:preflight_step();assert(ok and e=='VERIFIED')")
        self.assertIsNotNone(self.f.proof)
        self.assertEqual(self.opens, 1)
        self.assertEqual(self.opens, self.closes)

    def test_production_preflight_rejects_failed_proof_save(self):
        self.lua.execute(b"p.save_archive_proof=function()return false end;r,err=S.open(p,input);assert(r,err);local ok,e=r:preflight_step();assert(not ok and e=='ARCHIVE_PROOF_SAVE')")
        self.assertIsNone(self.f.proof)

    def test_production_preflight_rejects_missing_proof_readback(self):
        self.lua.execute(b"p.archive_verified=function()return false end;r,err=S.open(p,input);assert(r,err);local ok,e=r:preflight_step();assert(not ok and e=='ARCHIVE_PROOF_READBACK')")
        self.assertIsNotNone(self.f.proof)

    def test_production_reader_still_requires_real_ownership(self):
        self.lua.execute(b'''
        r,err=S.open(p,input);assert(r,err)
        p.owns_bundle=function()return false end
        local ok,e=r:preflight_step();assert(not ok and e=='GR_BUNDLE_OWNERSHIP_REQUIRED')
        ''')


if __name__=='__main__':
    unittest.main()
