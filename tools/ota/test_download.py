"""SAM | 2026-10-12 19:40 +08:00 | Offline tests execute the real resumable Lua engine."""
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'logs/cat1_antenna_20261010/python_deps'))
from lupa import LuaRuntime


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("package.path = ... .. '/Air780EGH/?.lua;' .. package.path", ROOT.as_posix())
        self.lua.execute('''
        M = require('ota_download')
        files = {['/user.json']='preserve', ['/confirmed.bin']='old'}
        data = 'abcdefghijkl'
        job = {size=#data, sha256=string.rep('a',64), md5=string.rep('b',32),url='https://example.invalid/fw'}
        saved=nil; requests=0; failure=nil; hook=nil; verify_ok=true
        port={chunk_size=4,max_size=1024}
        port.size=function(p) return files[p] and #files[p] or 0 end
        port.truncate=function(p,n) files[p]=(files[p] or ''):sub(1,n); return true end
        port.write=function(p,n,s) files[p]=(files[p] or ''):sub(1,n)..s; return true end
        port.read=function(p,n,k) return files[p]:sub(n+1,n+k) end
        port.checkpoint=function(c) if failure=='commit' then return false end; saved=c; return true end
        port.http_get=function(url,h,limit)
          requests=requests+1; last_headers=h
          local a,b=h.Range:match('bytes=(%d+)%-(%d+)'); a=tonumber(a); b=tonumber(b)
          local r={status=206,headers={['Content-Range']='bytes '..a..'-'..b..'/'..#data,['Content-Length']=tostring(b-a+1),ETag='"v1"'},body=data:sub(a+1,b+1)}
          if hook then hook(r) end
          return r
        end
        port.verify_file=function(p,j) return {size=#files[p],md5=j.md5,sha256=j.sha256,signature_valid=verify_ok} end
        d=M.new(port)
        function unchanged() assert(files['/user.json']=='preserve' and files['/confirmed.bin']=='old') end
        ''')

    def run_lua(self, code):
        self.lua.execute(code)

    # SAM | 2026-10-26 +08:00 | Safe fixed transport causes survive the wrapper without changing a committed checkpoint or leaking raw exception text.
    def test_specific_stream_failures_preserve_checkpoint(self):
        self.run_lua('''
        assert(d:start(job));assert(d:step());assert(saved.offset==4)
        for upper,lower in pairs({HTTP_TIMEOUT='network_timeout',HTTP_IDLE_TIMEOUT='network_idle_timeout',HTTP_EOF='network_eof',HTTP_SOCKET='network_socket'}) do
          d=M.new(port);assert(d:start(job,saved));port.http_get=function()error(upper,0)end
          local ok,e=d:step();assert(not ok and e==lower,tostring(e));assert(saved.offset==4);unchanged()
        end
        ''')

    def test_resume_and_verify(self):
        self.run_lua('''assert(d:start(job)); assert(d:step()); assert(saved.offset==4)
        d=M.new(port); assert(d:start(job,saved)); assert(d:step()); assert(last_headers['If-Range']=='"v1"')
        assert(d:step()); assert(d:verify()); assert(d:status().state=='VERIFIED'); unchanged()''')

    def test_invalid_jobs_no_writes(self):
        self.run_lua('''for _,j in ipairs({{}, {size=1025,sha256=job.sha256,md5=job.md5,url=job.url},
          {size=12,sha256='../oops',md5=job.md5,url=job.url},
          {size=12,sha256=job.sha256,md5=job.md5,url='file:///user.json'}}) do assert(not d:start(j)) end
          assert(requests==0); unchanged()''')

    def test_reject_bad_responses_without_append(self):
        self.run_lua('''for _,change in ipairs({function(r) r.status=500 end,
          function(r) r.status=200 end, function(r) r.headers['Content-Range']='bytes 0-3/13' end,
          function(r) r.headers['Content-Length']='5' end, function(r) r.body=r.body..'x' end,
          function(r) r.headers.ETag='W/"v1"' end}) do
          d=M.new(port); assert(d:start(job)); hook=change; assert(not d:step()); assert(d:status().offset==0)
          assert(port.size(d:status().path)==0); unchanged() end''')

    def test_changed_etag_and_200_resume(self):
        self.run_lua('''assert(d:start(job)); assert(d:step()); hook=function(r) r.status=200 end
        local ok,e=d:step(); assert(not ok and e=='restart_required'); assert(d:status().offset==4)
        d=M.new(port); assert(d:start(job,saved)); hook=function(r) r.headers.ETag='"v2"' end
        assert(not d:step()); assert(d:status().offset==4); unchanged()''')

    def test_failed_checkpoint_recovers_only_durable_offset(self):
        self.run_lua('''assert(d:start(job)); assert(d:step()); failure='commit'; assert(not d:step())
        assert(d:status().offset==4 and saved.offset==4); failure=nil
        d=M.new(port); assert(d:start(job,saved)); assert(port.size(d:status().path)==4); unchanged()''')

    def test_pause_discards_late_response(self):
        self.run_lua('''assert(d:start(job)); hook=function(r) d:pause() end; assert(not d:step())
        assert(d:status().offset==0); assert(port.size(d:status().path)==0)
        local n=requests; assert(not d:step()); assert(requests==n); unchanged()''')

    def test_signature_and_hash_are_mandatory(self):
        self.run_lua('''assert(d:start(job)); assert(not d:verify()); for i=1,3 do assert(d:step()) end
        verify_ok=false; assert(not d:verify()); assert(d:status().state~='VERIFIED')
        port.verify_file=nil; assert(not d:verify()); unchanged()''')

    def test_verifier_rejects_each_corrupt_field(self):
        self.run_lua('''assert(d:start(job)); for i=1,3 do assert(d:step()) end
        for _,field in ipairs({'size','md5','sha256','signature_valid'}) do
          port.verify_file=function(p,j)
            local result={size=j.size,md5=j.md5,sha256=j.sha256,signature_valid=true}
            result[field]=nil; return result
          end
          assert(not d:verify()); assert(d:status().state~='VERIFIED')
        end; unchanged()''')

    def test_pause_during_write_and_verify(self):
        self.run_lua('''assert(d:start(job)); local write=port.write
        port.write=function(...) local result=write(...); d:pause(); return result end
        assert(not d:step()); assert(d:status().offset==0); assert(saved==nil)
        port.write=write; assert(d:start(job,d:status().checkpoint))
        for i=1,3 do assert(d:step()) end
        local verifier=port.verify_file
        port.verify_file=function(...) local result=verifier(...); d:pause(); return result end
        assert(not d:verify()); assert(d:status().state=='PAUSED'); unchanged()''')

    def test_port_exception_and_missing_capability_fail_closed(self):
        self.run_lua('''assert(not M.new():start(job)); assert(d:start(job))
        port.http_get=function() error('private URL must not leak') end
        local ok,reason=d:step(); assert(not ok and reason=='network_error')
        assert(d:status().offset==0); unchanged()''')

    def test_readback_failure_not_durable(self):
        self.run_lua('''assert(d:start(job)); port.read=function() return 'xxxx' end
        assert(not d:step()); assert(d:status().offset==0); assert(saved==nil); unchanged()''')

    def test_invalid_checkpoint_preserves_files(self):
        self.run_lua('''assert(d:start(job)); assert(d:step()); local p=d:status().path
        for _,c in ipairs({{offset=4,path='/user.json',sha256=job.sha256,size=12,etag='"v1"'},
          {offset=13,sha256=job.sha256,size=12,etag='"v1"'},
          {offset=4,sha256=job.sha256,size=12,etag='W/"v1"'}}) do
          assert(not M.new(port):start(job,c)); assert(files[p]=='abcd'); unchanged() end''')


if __name__ == '__main__':
    unittest.main(verbosity=2)
