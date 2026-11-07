"""SAM | 2026-10-23 +08:00 | Read actual temporary files through the Lua scanner; never touch device/user files."""
import hashlib
import pathlib
import uuid
import unittest
from test_cat_manager import ROOT, LuaRuntime


class BootIdentityTests(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(__file__).resolve().parents[2]/'logs'/'ota_boot_identity_tests'/uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.files = {'main.luac': b'a'*4998+b'\x00\xff', 'other.luac': b'b'*20,
                      '.airm2m_all_crc#.bin': b'x'*16}
        for name, data in self.files.items():
            (self.root/name).write_bytes(data)
        self.lua = LuaRuntime(encoding='latin-1', unpack_returned_tuples=True)
        self.lua.globals().source_root = ROOT.as_posix()
        self.lua.execute("package.path=source_root..'/Air780EGH/?.lua;'..package.path")
        g = self.lua.globals()
        g.py_begin = lambda: hashlib.sha256()
        g.py_update = lambda h, s: (h.update(s.encode('latin-1')), True)[1]
        g.py_finish = lambda h: h.hexdigest()
        g.test_root = self.root.as_posix()
        g.main_hash = hashlib.sha256(self.files['main.luac']).hexdigest()
        g.other_hash = hashlib.sha256(self.files['other.luac']).hexdigest()
        self.lua.execute('''
        B=require('ota_boot_identity');reads=0;busy=false
        expected={files={['main.luac']=main_hash,['other.luac']=other_hash},file_count=2,
          package_sha256=string.rep('a',64),manifest_sha256=string.rep('b',64),
          build_record_sha256=string.rep('c',64),version='001.005.000'}
        names={'main.luac','other.luac','.airm2m_all_crc#.bin'}
        local realio=io
        api={open=function(path,mode)
          assert(path:sub(1,7)=='/luadb/' and mode=='rb');reads=reads+1
          return realio.open(test_root..'/'..path:sub(8),mode)
        end,lsdir=function(path,n,offset)
          assert(path=='/luadb/' and n==16)
          local out={};for i=offset+1,math.min(#names,offset+n) do out[#out+1]={name=names[i],type=0} end
          return true,out
        end}
        hash={hash_begin=function()return py_begin()end,
          hash_update=function(h,s)assert(#s<=4096);return py_update(h,s)end,
          hash_finish=function(h)return py_finish(h)end}
        function make()return assert(B.new(expected,hash,api,function()return not busy end))end
        function finish(s)for i=1,100 do local ok,e=s:step();if not ok or e=='VERIFIED' then return ok,e end end;error('unbounded')end
        s=make()
        ''')

    def test_success_and_input_copy(self):
        self.lua.execute("expected.files['main.luac']=string.rep('0',64)")
        self.assertEqual(self.lua.eval('finish(s)'), (True, 'VERIFIED'))

    def test_changed_code_rejected(self):
        (self.root/'main.luac').write_bytes(b'a'*4999+b'x')
        self.assertEqual(self.lua.eval('finish(s)'), (False, 'BOOT_CODE_MISMATCH'))

    def test_extra_missing_duplicate_files(self):
        for expression in ("names[#names+1]='extra.luac'", "table.remove(names,2)",
                           "names[#names+1]='main.luac'"):
            self.lua.execute("names={'main.luac','other.luac','.airm2m_all_crc#.bin'};"+expression+";s=make()")
            self.assertEqual(self.lua.eval('finish(s)'), (False, 'BOOT_FILE_SET'))

    def test_pause_does_not_read(self):
        self.lua.execute('busy=true')
        self.assertEqual(self.lua.eval('s:step()'), (False, 'BUSINESS_PAUSED'))
        self.assertEqual(self.lua.eval('reads'), 0)
        self.lua.execute('busy=false')
        self.assertEqual(self.lua.eval('finish(s)'), (True, 'VERIFIED'))

    def test_invalid_paths_and_read_failure(self):
        self.lua.execute("expected.files['../x']=main_hash")
        self.assertEqual(self.lua.eval('B.new(expected,hash,api)'), (None, 'BOOT_IDENTITY_INVALID'))
        (self.root/'main.luac').unlink()
        self.assertEqual(self.lua.eval('finish(s)'), (False, 'BOOT_READ_FAILED'))

    def test_close_error_and_size_change_cannot_confirm(self):
        self.lua.execute("local open=api.open;api.open=function(...)local f=open(...);return {seek=function(_,...)return f:seek(...)end,read=function(_,...)return f:read(...)end,close=function()f:close();return nil end}end")
        self.assertEqual(self.lua.eval('finish(s)'), (False, 'BOOT_READ_FAILED'))

    def test_change_length_between_chunks_rejected(self):
        self.lua.execute("assert(s:step());assert(s:step())")
        (self.root/'main.luac').write_bytes(b'a'*5001)
        self.assertEqual(self.lua.eval('finish(s)'), (False, 'BOOT_READ_FAILED'))


if __name__ == '__main__':
    unittest.main()
