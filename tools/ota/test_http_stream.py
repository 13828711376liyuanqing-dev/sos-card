"""SAM | 2026-10-24 +08:00 | Decode 200/chunked incrementally without a whole-body allocation or Range disguise."""
import unittest
import test_http_range as fixture


class StreamTests(unittest.TestCase):
    def run_lua(self, script):
        f=fixture.HttpRangeTests();f.setUp();f.lua.execute(script)

    # SAM | 2026-10-26 +08:00 | A healthy sequential component outlives 180s because journaling/pacing consumes wall time; real stalls and an overall bound must still terminate.
    def test_progressing_stream_crosses_old_absolute_deadline(self):
        self.run_lua(r'''
        response='HTTP/1.1 200 OK\r\nContent-Length: 40960\r\n\r\n'..string.rep('x',40960)
        fragment=512;local s=assert(p.open_stream('http://example.invalid/x'))
        for i=1,10 do clock=i*20000;local b,e=s.read(4096);assert(b and #b==4096,tostring(e))end
        assert(closed==1 and clock>180000)
        ''')

    def test_stream_idle_timeout_and_total_bound(self):
        self.run_lua(r'''
        response='HTTP/1.1 200 OK\r\nContent-Length: 40960\r\n\r\n'..string.rep('x',40960)
        fragment=512;local s=assert(p.open_stream('http://example.invalid/x'))
        assert(#s.read(4096)==4096);stall=true
        local b,e=s.read(4096);assert(b==nil and e=='HTTP_IDLE_TIMEOUT',tostring(e));assert(closed==1 and released==1)
        cursor=1;stall=false;clock=0;s=assert(p.open_stream('http://example.invalid/x'))
        clock=900001;b,e=s.read(4096);assert(b==nil and e=='HTTP_TIMEOUT',tostring(e))
        ''')

    def test_chunked_fragmented_reads_and_cleanup(self):
        self.run_lua(r'''
        response='HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n2\r\nDA\r\n2;test=yes\r\nTA\r\n0\r\n\r\n'
        local stream,e=p.open_stream('http://example.invalid/file')
        assert(stream,tostring(e))
        assert(not request:find('Range:',1,true))
        assert(stream.read(2)=='DA' and stream.read(2)=='TA' and stream.read(2)=='')
        assert(closed==1 and released==1 and largest<=512)
        assert(stream.read(1)=='' and stream.close())
        ''')

    # SAM | 2026-10-24 +08:00 | Terminal callback cannot discard buffered final chunk; absent terminal framing still rejects.
    def test_terminal_error_drains_only_complete_chunked_response(self):
        for complete in (True, False):
            suffix = '0\\r\\n\\r\\n' if complete else ''
            self.run_lua("response='HTTP/1.1 200 OK\\r\\nTransfer-Encoding: chunked\\r\\n\\r\\n4\\r\\nDATA\\r\\n" + suffix + "';fragment=7;local old=socket.rx;socket.rx=function(...)local ok,n=old(...);if cursor>#response then callback(nil,socket.EVENT,-1)end;return ok,n end;local s,e=p.open_stream('http://example.invalid/x');assert(s,tostring(e));local body,why=s.read(16);" + ("assert(body=='DATA' and s.read(1)=='',tostring(why))" if complete else "assert(body==nil and why=='HTTP_EOF',tostring(why))") + ";assert(closed==1 and released==1)")

    # SAM | 2026-10-24 +08:00 | The modem must finish bounded reads before the peer closes; our socket still closes on EOF.
    def test_keepalive_request_keeps_client_owned_cleanup(self):
        self.run_lua("response='HTTP/1.1 200 OK\\r\\nContent-Length: 4\\r\\n\\r\\nDATA';local s,e=p.open_stream('http://example.invalid/x');assert(s,tostring(e));assert(request:find('Connection: keep-alive',1,true));assert(closed==0);assert(s.read(8)=='DATA' and closed==1 and released==1)")

    def test_content_length_and_pause_close(self):
        self.run_lua(r'''
        response='HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\nDATA'
        local stream=assert(p.open_stream('http://example.invalid/file'))
        assert(stream.read(16)=='DATA' and stream.read(1)=='')
        assert(closed==1)
        cursor=1;stream=assert(p.open_stream('http://example.invalid/file'));allowed=false
        local b,e=stream.read(1);assert(not b and e=='BUSINESS_PAUSED')
        assert(closed==2 and released==2)
        ''')

    def test_conflicting_framing_and_invalid_chunk_rejected(self):
        for body in [
            r"response='HTTP/1.1 200 OK\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nDATA\r\n0\r\n\r\n'",
            r"response='HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n4g\r\nDATA\r\n0\r\n\r\n'",
            r"response='HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nFFFFFF\r\n'",
        ]:
            self.run_lua(body+r'''
            local s,e=p.open_stream('http://example.invalid/file')
            if s then local b,why=s.read(16);assert(not b and why)else assert(e)end
            assert(closed==1 and released==1)
            ''')

    def test_early_close_releases_owned_socket(self):
        self.run_lua(r'''
        response='HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nDATA\r\n0\r\n\r\n'
        local s=assert(p.open_stream('http://example.invalid/file'))
        local r,e=get();assert(not r and e=='HTTP_BUSY')
        assert(s.close() and closed==1 and released==1)
        local b,e=s.read(1);assert(not b and e=='HTTP_STREAM_CLOSED')
        ''')


if __name__=='__main__':
    unittest.main()
