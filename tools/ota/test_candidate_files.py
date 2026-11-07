"""SAM | 2026-10-23 +08:00 | Verify device file adapter on real temporary files and bounded stream hashing."""
# SAM | 2026-10-24 +08:00 | Exercise the renamed USB-compatible module against the same persistent paths.
import hashlib
import base64
from pathlib import Path
import contextlib
import uuid
import unittest
import test_zip_bundle


class FileTests(unittest.TestCase):
    # SAM | 2026-10-24 +08:00 | Compare with Python's independent codec; never shorten identity by dropping hash bits.
    def test_short_path_keeps_all_hash_bits_and_rejects_user_paths(self):
        f=test_zip_bundle.BundleTests();f.setUp()
        module=f.lua.eval(b"require('ota_candidates')")
        hashes=[bytes(32),bytes([255])*32]+[hashlib.sha256(str(i).encode()).digest() for i in range(32)]
        for digest in hashes:
            path=module[b'path'](digest.hex().encode())
            expected=b'/o'+base64.b32encode(digest).lower().rstrip(b'=')+b'.p'
            self.assertEqual(path,expected)
            self.assertLessEqual(len(path)-1,63)
            self.assertTrue(module[b'allowed'](path))
        self.assertIsNone(module[b'path'](b'bad'))
        for path in [b'/user.cfg',b'/ota_candidate_'+b'a'*64+b'.part',b'/o'+b'a'*51+b'b.p']:
            self.assertFalse(module[b'allowed'](path))

    # SAM | 2026-10-24 +08:00 | Reproduce V2052's 63-byte LittleFS name ceiling at the real downloader/file boundary.
    def test_download_respects_native_filename_limit(self):
        f=test_zip_bundle.BundleTests();f.setUp();f.opened()
        self.assertIs(f.lua.eval(b'scan()'),True)
        folder=test_zip_bundle.ROOT/'logs/candidate_file_tests'/uuid.uuid4().hex
        folder.mkdir(parents=True)
        f.lua.globals().root=folder.as_posix().encode()
        f.lua.globals().exists=lambda p: (folder/p.decode().lstrip('/')).is_file()
        f.lua.globals().begin=lambda kind: hashlib.new(kind.decode().lower())
        f.lua.execute(b'''
          local native=io
          api={exists=function(p)return exists(p)end,open=function(p,m)
            if #p:match('[^/]+$')>63 then return nil end
            return native.open(root..p,m)
          end}
          hashes={hash_begin=function(k)return begin(k)end,hash_update=p.hash_update,hash_finish=p.hash_finish}
          local disk=require('ota_candidates').new(hashes,api)
          disk.checkpoint=function()return true end
          local cp=assert(r:component_port('GR5526',1,disk))
          local d=require('ota_download').new(cp)
          assert(d:start(r:component('GR5526')))
          local ok,why=d:step();assert(ok,why)
          assert(d:status().offset>0)
        ''')

    # SAM | 2026-10-23 19:56 +08:00 | Cleanup must be idempotent and cannot address any user file.
    def test_completed_candidate_cleanup_is_scoped_and_read_back(self):
        f=test_zip_bundle.BundleTests();f.setUp()
        folder=test_zip_bundle.ROOT/'logs/candidate_file_tests'/uuid.uuid4().hex
        folder.mkdir(parents=True)
        f.lua.globals().root=folder.as_posix().encode()
        f.lua.globals().exists=lambda p:(folder/p.decode().lstrip('/')).is_file()
        f.lua.execute(b'''
          local native=io;local removed=0
          api={exists=function(p)return exists(p)end,open=function(p,m)return native.open(root..p,m)end,
            remove=function(p)removed=removed+1;return os.remove(root..p)end}
          files=require('ota_candidates').new({},api)
          path=require('ota_candidates').path(string.rep('a',64))
          local user=assert(native.open(root..'/user.cfg','wb'));user:write('keep');user:close()
          assert(not files.remove('/user.cfg') and removed==0)
          assert(files.write(path,0,'candidate'))
          assert(files.remove(path) and not api.exists(path))
          assert(files.remove(path) and removed==1)
          assert(api.exists('/user.cfg'))
          assert(files.write(path,0,'candidate'))
          api.remove=function()return true end
          assert(not files.remove(path),'successful return is not proof of deletion')
        ''')
    def test_signed_component_download_resume_real_files(self):
        f=test_zip_bundle.BundleTests();f.setUp();f.opened()
        self.assertIs(f.lua.eval(b'scan()'),True)
        folder=test_zip_bundle.ROOT/'logs/candidate_file_tests'/uuid.uuid4().hex
        folder.mkdir(parents=True)
        f.lua.globals().root=folder.as_posix().encode()
        f.lua.globals().exists=lambda p: (folder/p.decode().lstrip('/')).is_file()
        f.lua.globals().begin=lambda kind: hashlib.new(kind.decode().lower())
        f.lua.execute(b'''
          api={exists=function(p)return exists(p)end,open=function(p,m)return io.open(root..p,m)end}
          hashes={hash_begin=function(k)return begin(k)end,hash_update=p.hash_update,hash_finish=p.hash_finish}
          c=r:component('GR5526');checkpoint=nil
          function create()
            local disk=require('ota_candidates').new(hashes,api)
            disk.checkpoint=function(v)checkpoint=v;return true end
            local cp=assert(r:component_port('GR5526',1,disk))
            local d=require('ota_download').new(cp)
            assert(d:start(c,checkpoint));return d,disk
          end
          d,disk=create();assert(d:step())
          -- Simulate data written before a lost durable checkpoint, then reset RAM.
          assert(disk.write(d:status().path,4096,'uncommitted'))
          d,disk=create();assert(d:status().offset==4096)
          while d:status().state=='DOWNLOADING' do assert(d:step()) end
          assert(d:verify());assert(d:status().state=='VERIFIED')
        ''')
        component=f.lua.globals().c
        path=folder/('o'+base64.b32encode(bytes.fromhex(component[b'sha256'].decode())).decode().lower().rstrip('=')+'.p')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest().encode(),component[b'sha256'])

    def test_real_file_recovery_and_path_protection(self):
        f=test_zip_bundle.BundleTests();f.setUp()
        folder=test_zip_bundle.ROOT/'logs/candidate_file_tests'/uuid.uuid4().hex
        folder.mkdir(parents=True)
        with contextlib.nullcontext(folder) as folder:
            f.lua.globals().root=Path(folder).as_posix().encode()
            f.lua.globals().exists=lambda p: (Path(folder)/p.decode().lstrip('/')).is_file()
            f.lua.globals().begin=lambda kind: hashlib.new(kind.decode().lower())
            f.lua.execute(b'''
              local native=io
              api={exists=function(p)return exists(p)end,open=function(p,m)return native.open(root..p,m)end}
              hashes={hash_begin=function(k)return begin(k)end,hash_update=p.hash_update,hash_finish=p.hash_finish}
              files=require('ota_candidates').new(hashes,api)
              path=require('ota_candidates').path(string.rep('a',64))
              assert(files.size(path)==0)
              assert(files.write(path,0,'abcdef'))
              assert(files.size(path)==6)
              assert(files.truncate(path,3))
              assert(files.size(path)==3 and files.read(path,0,3)=='abc')
              assert(files.verify_file(path,{size=3})==nil,'physical tail hidden from verifier')
              assert(files.write(path,3,'XYZ123'))
              assert(files.read(path,0,9)=='abcXYZ123')
              assert(not files.write('/user.cfg',0,'bad'))
              assert(not files.truncate('/user.cfg',0))
              assert(not files.write(path,20,'hole'))
              -- SAM | 2026-11-04 +08:00 | Per-call limit is io_limit (16 KiB OTA speed-up chunks), stored in 4 KiB file calls.
              assert(not files.write(path,9,string.rep('x',16385)))
              result=files.verify_file(path,{size=9})
              assert(result and result.size==9 and result.signature_valid==false)
              local big={};for i=1,16384 do big[i]=string.char(i%251) end;big=table.concat(big)
              assert(files.write(path,9,big) and files.size(path)==9+16384)
              assert(files.read(path,9,16384)==big and files.read(path,0,9)=='abcXYZ123')
              assert(files.read(path,0,16385)==nil)
            ''')
            result=f.lua.globals().result
            self.assertEqual(result[b'sha256'],hashlib.sha256(b'abcXYZ123').hexdigest().encode())
            self.assertEqual(result[b'md5'],hashlib.md5(b'abcXYZ123').hexdigest().encode())

    def test_signed_binding_rejects_hash_only_tampering(self):
        f=test_zip_bundle.BundleTests();f.setUp();f.opened()
        self.assertIs(f.lua.eval(b'scan()'),True)
        f.lua.execute(b'''
          c=r:component('GR5526')
          local wrong=false
          cp=assert(r:component_port('GR5526',1,{verify_file=function()
            return {size=c.size,md5=c.md5,sha256=wrong and string.rep('0',64) or c.sha256,
              content_hash_only=true,signature_valid=false}
          end}))
          assert(cp.verify_file().signature_valid==true)
          wrong=true;assert(cp.verify_file().signature_valid==false)
        ''')


if __name__=='__main__':unittest.main()
