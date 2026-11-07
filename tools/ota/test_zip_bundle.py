"""SAM | 2026-10-22 +08:00 | Exercise actual Lua ZIP reader against signed STORE archives, without device writes."""
import base64
import hashlib
import json
import os
import io
import pathlib
import sys
import unittest
import zipfile
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes


class BundleTests(unittest.TestCase):
    def setUp(self):
        # SAM | 2026-10-23 20:25 +08:00 | Exercise the current operator-generated native package; legacy oversized fixtures must not define the firmware's layout.
        fixture = json.loads((ROOT / 'tools/ota/bundle_fixture.json').read_text(encoding='utf-8'))
        archive = pathlib.Path(os.environ.get('YP_OTA_TEST_ARCHIVE', str(ROOT / fixture['archive'])))
        self.data = archive.read_bytes()
        if 'YP_OTA_TEST_ARCHIVE' not in os.environ:
            self.assertEqual(hashlib.sha256(self.data).hexdigest(), fixture['sha256'])
        with zipfile.ZipFile(io.BytesIO(self.data)) as z:
            manifest = json.loads(z.read('bundle.json'))
        self.assertEqual(manifest['gr_slot_bytes'], 442368)
        self.lua = LuaRuntime(encoding=None, unpack_returned_tuples=True)
        self.lua.execute(b"package.path=.....'/Air780EGH/?.lua;'..package.path", ROOT.as_posix().encode())
        public = (ROOT / 'tools/toolkit/test_keys/OTA_TEST_PUBLIC.xml').read_bytes()
        key = ET.fromstring(public)
        num = lambda n: int.from_bytes(base64.b64decode(key.findtext(n)), 'big')
        self.key = rsa.RSAPublicNumbers(num('Exponent'), num('Modulus')).public_key()
        self.proof = None
        self.owner = b'GR5526'
        self.done = False
        self.allowed = True
        self.etag = b'"fixture-v1"'
        self.mode = None
        self.reads = []
        g = self.lua.globals()
        g.fixture_source = manifest['source_version'].encode()
        g.fixture_target = manifest['target_version'].encode()
        g.py_http = self.http
        g.py_decode = lambda s: self.table(json.loads(s))
        g.py_sha = lambda s: hashlib.sha256(s).hexdigest().encode()
        g.py_verify = self.verify
        g.py_begin = lambda _: hashlib.md5()
        g.py_update = lambda h, s: (h.update(s), True)[1]
        g.py_finish = lambda h: h.hexdigest().encode()
        g.py_proof = lambda *args: args == self.proof
        g.py_save = self.save
        g.py_allowed = lambda: self.allowed
        g.py_owner = lambda target, *_: target == self.owner
        g.py_completed = lambda target, *_: self.done if target == b'GR5526' else False
        g.keyid = hashlib.sha256(public).hexdigest().encode()
        g.md5 = hashlib.md5(self.data).hexdigest().encode()
        self.lua.execute(b'''
        M=require('ota_bundle')
        p={trusted_key_id=keyid,
          http_get=function(...) return py_http(...) end,
          decode=function(s) return py_decode(s) end,
          sha256=function(s) return py_sha(s) end,
          verify_manifest=function(...) return py_verify(...) end,
          can_read=function() return py_allowed() end,
          current_version=function() return fixture_source end,
          owns_bundle=function() return true end,
          owns=function(...) return py_owner(...) end,
          completed=function(...) return py_completed(...) end,
          free_bytes=function() return 495616 end,
          hash_begin=function(...) return py_begin(...) end,
          hash_update=function(...) return py_update(...) end,
          hash_finish=function(...) return py_finish(...) end,
          archive_verified=function(...) return py_proof(...) end,
          save_archive_proof=function(...) return py_save(...) end}
        input={url='https://example.invalid/update.zip',md5=md5}
        function open() r,err=M.open(p,input);return r~=nil,err end
        function scan() for i=1,600 do local ok,e=r:preflight_step();if not ok then return false,e end;if e=='VERIFIED' then return true end end;error('unbounded') end
        ''')

    def table(self, value):
        if isinstance(value, dict):
            return self.lua.table_from({k.encode(): self.table(v) for k, v in value.items()})
        if isinstance(value, list):
            return self.lua.table_from([self.table(v) for v in value])
        return value.encode() if isinstance(value, str) else value

    def verify(self, manifest, signature):
        try:
            sig = json.loads(signature)
            self.key.verify(base64.b64decode(sig['signature_base64']),
                            b'YP001_BUNDLE_LOCAL_TEST_RSA_V1\0' + manifest,
                            padding.PKCS1v15(), hashes.SHA256())
            return True
        except Exception:
            return False

    def save(self, *args):
        self.proof = args
        return True

    def http(self, url, headers, limit):
        a, b = map(int, headers[b'Range'][6:].split(b'-'))
        assert b-a+1 == limit and limit <= 16384
        self.reads.append((a, b))
        response = {b'status': 206, b'body': self.data[a:b+1], b'headers': self.lua.table_from({
            b'Content-Range': f'bytes {a}-{b}/{len(self.data)}'.encode(),
            b'Content-Length': str(limit).encode(), b'ETag': self.etag})}
        if self.mode == '200':
            response[b'status'] = 200
        return self.lua.table_from(response)

    def opened(self):
        self.assertEqual(self.lua.eval(b'open()'), (True, None))

    # SAM | 2026-10-23 +08:00 | Authenticated record must expose a bounded immutable identity, never a version-only boot claim.
    def test_authenticated_code_identity_is_copied(self):
        self.opened()
        self.lua.execute(b"""
        local a=r:cat_identity();assert(a.files['main.luac'] and a.file_count>0)
        local expected=a.files['main.luac'];a.files['main.luac']='changed'
        local b=r:cat_identity();assert(b.files['main.luac']==expected)
        assert(b.manifest_sha256==r:summary().manifest_sha256)
        assert(b.package_sha256==r:component('CAT1').sha256)
        """)

    def test_invalid_compiled_map_rejected(self):
        for change in (b"b.compiled_sha256=nil", b"b.file_count=0",
                       b"b.compiled_sha256['../main.luac']=string.rep('0',64)",
                       b"b.compiled_sha256['main.luac']='bad'"):
            with self.subTest(change=change):
                self.lua.execute(b"""
                p.decode=function(s)
                  local b=py_decode(s)
                  if b.schema=='YP001_CAT1_SCRIPT_SOTA_V1' then
                """+change+b" end;return b end")
                self.assertEqual(self.lua.eval(b'open()'), (False, b'BUILD_CODE_IDENTITY'))

    # SAM | 2026-10-23 +08:00 | Native timeout must remain retryable through the production ZIP/runtime path.
    def test_native_timeout_is_retryable_and_pause_does_not_spend_budget(self):
        self.runtime_setup()
        self.lua.execute(b'''
        local clock=1000;base.now=function()return clock end
        p.http_get=function()return nil,'HTTP_TIMEOUT' end
        function recover()
          runtime=make_runtime()
          assert(runtime:on_gr_line('OTA_GR='..codec.encode({op='STATUS',job=job.id,hash=job.hash,
            target=job.target,version=job.version,epoch=7,phase='DOWNLOADING'})))
        end
        recover();local ok,why=runtime:tick();assert(not ok and why=='NETWORK_ERROR',tostring(why))
        assert(runtime:status().retries[job.hash].permanent==false)
        recover();ok,why=runtime:tick();assert(not ok and why=='RETRY_BACKOFF')
        clock=1031;runtime:tick();assert(runtime:status().retries[job.hash].count==2)
        p.http_get=function()return nil,'BUSINESS_PAUSED' end
        clock=1092;recover();runtime:tick();assert(runtime:status().retries[job.hash].count==2)
        assert(runtime:status().download==nil and files['/user.cfg']=='preserved')
        ''')

    def test_store_and_real_signature(self):
        import io
        with zipfile.ZipFile(io.BytesIO(self.data)) as z:
            self.assertEqual(len(z.infolist()), 6)
            self.assertTrue(all(e.compress_type == 0 for e in z.infolist()))
        self.opened()
        self.assertIs(self.lua.eval(b'scan()'), True)
        self.assertIsNotNone(self.proof)
        self.assertLessEqual(max(b-a+1 for a, b in self.reads), 16384)

    # SAM | 2026-10-23 +08:00 | The component downloader must retain pause/entity distinctions after the wrapper throws.
    def test_component_pause_and_entity_failure_classification(self):
        self.runtime_setup()
        self.lua.execute(b'''
        for i=1,500 do runtime:tick();if runtime:status().download then break end end
        assert(runtime:status().download.offset==4096)
        ''')
        self.allowed = False
        self.lua.execute(b"local ok,e=runtime:tick();assert(not ok and e=='paused',tostring(e));assert(next(runtime:status().retries)==nil)")
        self.allowed = True
        self.etag = b'"different-object"'
        self.lua.execute(b"local ok,e=runtime:tick();assert(not ok and e=='entity_changed',tostring(e));assert(runtime:status().retries[job.hash].permanent)")

    def test_legacy_oversized_signed_gr_is_rejected_before_component_download(self):
        # SAM | 2026-10-23 20:25 +08:00 | A formerly accepted signed package cannot cross the now-fixed preserved-data boundary.
        self.data = (ROOT / 'logs/ota_integrated_progress_20261023/signed_bundle/YP001_1.0.0---1.0.2_LOCAL_TEST_c1cb05278675.ypota.zip').read_bytes()
        self.assertEqual(self.lua.eval(b'open()'), (False, b'ZIP_MEMBER'))
        self.assertIsNone(self.proof)

    def test_md5_mismatch_blocks_components(self):
        self.lua.execute(b"input.md5=string.rep('0',32)")
        self.opened()
        self.assertEqual(self.lua.eval(b'scan()'), (False, b'ARCHIVE_MD5_MISMATCH'))
        self.assertIsNone(self.proof)
        self.assertEqual(self.lua.eval(b"r:component_port('GR5526',1,{})"), (None, b'ARCHIVE_MD5_UNVERIFIED'))

    def test_serial_gate_and_exact_component_bytes(self):
        self.opened()
        self.assertIs(self.lua.eval(b'scan()'), True)
        self.assertEqual(self.lua.eval(b"r:component_port('CAT1',1,{})"), (None, b'GR_OWNERSHIP_REQUIRED'))
        self.lua.execute(b"cp=assert(r:component_port('GR5526',1,{}));c=r:component('GR5526')")
        c = self.lua.globals().c
        body = self.lua.eval(b"cp.http_get(input.url,{Range='bytes=0-4095'},4096).body")
        self.assertEqual(body, self.data[c[b'offset']:c[b'offset']+4096])
        self.owner, self.done = b'CAT1', True
        self.assertIsNotNone(self.lua.eval(b"r:component_port('CAT1',1,{})"))

    def test_pause_and_entity_change(self):
        self.opened()
        self.allowed = False
        self.assertEqual(self.lua.eval(b'r:preflight_step()'), (False, b'BUSINESS_PAUSED'))
        self.allowed = True
        self.etag = b'"changed"'
        self.assertEqual(self.lua.eval(b'r:preflight_step()'), (False, b'BUNDLE_ENTITY_CHANGED'))

    def test_reject_200_and_weak_entity(self):
        self.mode = '200'
        self.assertEqual(self.lua.eval(b'open()'), (False, b'HTTP_RANGE_REQUIRED'))
        self.mode = None
        self.etag = b'W/"weak"'
        self.assertEqual(self.lua.eval(b'open()'), (False, b'HTTP_ETAG'))

    def test_proof_reuse_and_reset(self):
        self.opened()
        self.assertEqual(self.lua.eval(b'r:preflight_step()'), (True, b'VERIFYING'))
        self.opened()
        self.assertEqual(self.lua.eval(b'r:preflight_status().offset'), 0)
        self.assertIs(self.lua.eval(b'scan()'), True)
        self.opened()
        n = len(self.reads)
        self.assertEqual(self.lua.eval(b'r:preflight_step()'), (True, b'VERIFIED'))
        self.assertEqual(len(self.reads), n)

    def test_invalid_signature_and_pinned_key(self):
        self.lua.execute(b'p.verify_manifest=function() return false end')
        self.assertEqual(self.lua.eval(b'open()'), (False, b'SIGNATURE_INVALID'))
        self.lua.execute(b"p.trusted_key_id=string.rep('0',64)")
        self.assertEqual(self.lua.eval(b'open()'), (False, b'SIGNATURE_KEY'))

    def test_reject_old_deflate_archive(self):
        old = next((ROOT / 'OTA_Packager/output').glob('*bf3449debd69*.ypota.zip'))
        self.data = old.read_bytes()
        self.assertEqual(self.lua.eval(b'open()'), (False, b'ZIP_STORE_REQUIRED'))

    def test_space_unknown_and_revoked_verification(self):
        self.opened()
        self.assertIs(self.lua.eval(b'scan()'), True)
        self.lua.execute(b'p.free_bytes=function() return 100 end')
        self.assertEqual(self.lua.eval(b"r:component_port('GR5526',1,{})"), (None, b'COMPONENT_SPACE'))
        self.lua.execute(b'''p.free_bytes=function() return 495616 end
          base={verify_file=function() p.owns=function() return false end;return {signature_valid=true} end}
          cp=assert(r:component_port('GR5526',1,base))
          assert(cp.verify_file()==false)''')

    def test_corrupt_directory_rejected(self):
        self.data = self.data[:-22] + bytes(22)
        self.assertEqual(self.lua.eval(b'open()'), (False, b'ZIP_EOCD'))

    # SAM | 2026-10-23 +08:00 | Drive the actual runtime/manager/store/download chain with an authenticated ZIP, not a fake downloader.
    def runtime_setup(self, mismatch=False):
        from lupa.lua53 import lua_type
        def native(value):
            if lua_type(value) == 'table':
                keys = list(value.keys())
                if keys and all(isinstance(k, int) for k in keys):
                    return [native(value[k]) for k in sorted(keys)]
                return {k.decode(): native(v) for k, v in value.items()}
            return value.decode() if isinstance(value, bytes) else value
        self.lua.globals().py_encode = lambda v: json.dumps(native(v), separators=(',', ':')).encode()
        self.opened()
        self.lua.execute(b'''
        codec={encode=function(t)return py_encode(t)end,decode=function(s)return py_decode(s)end}
        manifest=r:summary().manifest_sha256;c=r:component('GR5526');files={['/user.cfg']='preserved'};journal={};stages=0
        store=require('ota_store').new({read=function(p)return journal[p],journal[p] and nil or 'missing'end,
          write=function(p,s)journal[p]=s;return true end},codec)
        job={id=string.rep('b',64),hash=c.sha256,md5=c.md5,size=c.size,target='GR5526',
          version=fixture_target,source=fixture_source,url=input.url,bundle={md5=input.md5,manifest_sha256=manifest}}
        base={resolve=function()return job end,validate=function()return true end,compare=function()return 1 end,
          idle=function()return true end,now=function()return 1000 end,send_gr=function()return true end,
          stage_gr=function(j,path,epoch)assert(epoch==7 and #files[path]==j.size);stages=stages+1;return true end,
          candidate_ready=function()return true end}
        dp={chunk_size=4096,max_size=524288,size=function(p)return #(files[p] or '')end,
          truncate=function(p,n)files[p]=(files[p] or ''):sub(1,n);return true end,
          write=function(p,n,s)files[p]=(files[p] or ''):sub(1,n)..s;return true end,
          read=function(p,n,k)return files[p]:sub(n+1,n+k)end,
          verify_file=function(p,j)return {size=#files[p],sha256=py_sha(files[p]),md5=py_md5(files[p]),signature_valid=true}end,
          http_get=function()error('ZIP must never enter the raw component downloader')end}
        function make_runtime()return require('ota_runtime').new({codec=codec,store=store,port=base,download_port=dp,bundle_port=p})end
        command={MsgType='otaMsg',CurrentVersion=fixture_source,TargetVersion=fixture_target,Address=input.url,Md5=input.md5,Time=1}
        ''')
        self.lua.globals().py_md5 = lambda s: hashlib.md5(s).hexdigest().encode()
        if mismatch:
            self.lua.execute(b"job.hash=string.rep('a',64)")
        self.lua.execute(b'''
        runtime=make_runtime();assert(runtime:accept(command))
        assert(runtime:on_gr_line('OTA_GR='..codec.encode({op='GRANT',job=job.id,hash=job.hash,
          target=job.target,version=job.version,epoch=7,phase='DOWNLOADING'})))
        ''')

    def test_runtime_bundle_resume_stops_test_archive_before_gr_staging(self):
        self.runtime_setup()
        self.lua.execute(b'''
        for i=1,8 do assert(not runtime:tick());assert(runtime:status().download==nil)end
        runtime=make_runtime()
        -- SAM | 2026-10-23 +08:00 | Reboot must obtain matching peer status before any resumed range request.
        assert(not runtime:tick())
        assert(runtime:on_gr_line('OTA_GR='..codec.encode({op='STATUS',job=job.id,hash=job.hash,
          target=job.target,version=job.version,epoch=7,phase='DOWNLOADING'})))
        for i=1,500 do
          runtime:tick()
          if runtime:status().download and runtime:status().download.offset>0 then break end
        end
        assert(runtime:status().download.offset==4096,'ZIP preflight never reached component download')
        -- Actual FS free space shrinks with the existing candidate; resume must count only the remaining bytes.
        p.free_bytes=function()return 495616-runtime:status().download.offset end
        runtime=make_runtime()
        assert(not runtime:tick())
        assert(runtime:on_gr_line('OTA_GR='..codec.encode({op='STATUS',job=job.id,hash=job.hash,
          target=job.target,version=job.version,epoch=7,phase='DOWNLOADING'})))
        for i=1,200 do runtime:tick();if runtime:status().reason=='BUNDLE_NOT_INSTALLABLE' then break end end
        assert(runtime:status().reason=='BUNDLE_NOT_INSTALLABLE' and stages==0)
        assert(runtime:status().download.offset==job.size)
        assert(files['/user.cfg']=='preserved')
        ''')

    # SAM | 2026-10-23 +08:00 | Production defaults must use the real manager journal, not fixture ownership or in-memory proof callbacks.
    def test_runtime_default_ownership_and_archive_proof(self):
        self.runtime_setup()
        self.lua.execute(b'''
        p.owns=nil;p.owns_bundle=nil;p.archive_verified=nil;p.save_archive_proof=nil
        runtime=make_runtime();assert(not runtime:tick())
        assert(runtime:on_gr_line('OTA_GR='..codec.encode({op='STATUS',job=job.id,hash=job.hash,
          target=job.target,version=job.version,epoch=7,phase='DOWNLOADING'})))
        for i=1,500 do
          runtime:tick()
          if runtime:status().download and runtime:status().download.offset>0 then break end
        end
        local s=runtime:status();assert(s.download and s.download.offset==4096)
        assert(s.release.archive_proof.md5==input.md5)
        assert(s.release.archive_proof.manifest==job.bundle.manifest_sha256)
        runtime=make_runtime();assert(not runtime:tick())
        assert(runtime:status().download.offset==4096 and stages==0)
        assert(runtime:on_gr_line('OTA_GR='..codec.encode({op='STATUS',job=job.id,hash=job.hash,
          target=job.target,version=job.version,epoch=7,phase='DOWNLOADING'})))
        runtime:tick();assert(runtime:status().download.offset==8192)
        assert(files['/user.cfg']=='preserved')
        ''')

    def test_runtime_rejects_component_mapping_mismatch(self):
        self.runtime_setup(mismatch=True)
        self.lua.execute(b'''
        local ok,e=runtime:tick();assert(not ok and e=='BUNDLE_JOB_MISMATCH',tostring(e))
        assert(runtime:status().download==nil and stages==0)
        assert(files['/user.cfg']=='preserved')
        ''')

    def test_luatos_crypto_contract_and_real_pinned_rsa(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import utils
        g=self.lua.globals()
        g.native_begin=lambda kind: hashlib.new(kind.decode().lower())
        g.native_update=lambda h,data: h.update(data)  # LuatOS returns nil, not true.
        g.native_finish=lambda h: h.hexdigest().upper().encode()
        def verify_native(pem,mode,digest,sig):
            try:
                serialization.load_pem_public_key(pem).verify(sig,digest,padding.PKCS1v15(),utils.Prehashed(hashes.SHA256()))
                return mode==6
            except Exception:
                return False
        g.native_verify=verify_native
        self.lua.execute(b'''
        native={hash_init=function(...)return native_begin(...)end,
          hash_update=function(...)return native_update(...)end,
          hash_finish=function(...)return native_finish(...)end}
        rsa={MD_SHA256=6,verify=function(...)return native_verify(...)end}
        crypto_port=assert(require('ota_crypto').new(native,rsa,{decode=p.decode},require('ota_trust')))
        for k,v in pairs(crypto_port)do p[k]=v end
        local h=p.hash_begin('MD5');assert(p.hash_update(h,'abc'))
        assert(p.hash_finish(h)=='900150983cd24fb0d6963f7d28e17f72')
        assert(not p.hash_update(h,'again') and p.hash_finish(h)==nil)
        ''')
        self.opened()
        self.assertIs(self.lua.eval(b'scan()'), True)
        self.lua.execute(b'''
        local trust=require('ota_trust');local old=trust.key_id;trust.key_id=string.rep('0',64)
        local bad,e=require('ota_crypto').new(native,rsa,{decode=p.decode},trust)
        assert(not bad and e=='CRYPTO_KEY_FINGERPRINT');trust.key_id=old
        assert(not crypto_port.verify_manifest('{}','{}'))
        ''')

    # SAM | 2026-10-22 +08:00 | Exercise real HTTP sockets separately from injected response tests; still no device installation.
    def test_real_http_whole_zip_and_both_component_hashes(self):
        import threading
        import urllib.request
        from sim_backend.package_http import PackageServer
        server = PackageServer(self.data)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/packages/{server.digest}'
        seen = []

        def network(request_url, headers, limit):
            hdr = {k.decode(): v.decode() for k, v in headers.items()}
            request = urllib.request.Request(request_url.decode(), headers=hdr)
            with urllib.request.urlopen(request, timeout=3) as response:
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise ValueError('receive limit exceeded')
                seen.append(len(body))
                return self.lua.table_from({b'status': response.status, b'body': body,
                    b'headers': self.lua.table_from({k.encode(): v.encode() for k, v in response.headers.items()}),
                    b'final_url': response.url.encode()})
        self.lua.globals().py_http = network
        self.lua.globals().input[b'url'] = url.encode()
        try:
            self.opened()
            self.assertIs(self.lua.eval(b'scan()'), True)
            for target in (b'GR5526', b'CAT1'):
                self.owner = target
                self.lua.globals().target = target
                self.lua.execute(b'cp=assert(r:component_port(target,1,{}));c=r:component(target)')
                component = self.lua.globals().c
                sha, md5 = hashlib.sha256(), hashlib.md5()
                # Hash streaming buffers; never accumulate the whole ZIP or a component in this test.
                for offset in range(0, component[b'size'], 4096):
                    count = min(4096, component[b'size'] - offset)
                    self.lua.globals().requested_range = f'bytes={offset}-{offset+count-1}'.encode()
                    self.lua.globals().requested_count = count
                    body = self.lua.eval(b'cp.http_get(input.url,{Range=requested_range},requested_count).body')
                    sha.update(body)
                    md5.update(body)
                self.assertEqual(sha.hexdigest().encode(), component[b'sha256'])
                self.assertEqual(md5.hexdigest().encode(), component[b'md5'])
                # Host confirmation only; deliberately not a claim that GR installed on hardware.
                self.done = True
            self.assertGreater(len(seen), 300)
            self.assertLessEqual(max(seen), 16384)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == '__main__':
    unittest.main()
