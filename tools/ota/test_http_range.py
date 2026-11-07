"""SAM | 2026-10-23 +08:00 | Fault-inject bounded native socket reads before enabling any device OTA transport."""
import unittest
from test_cat_manager import runtime


class HttpRangeTests(unittest.TestCase):
    def setUp(self):
        self.lua = runtime()
        self.lua.execute('''
        M=require('ota_http_range')
        clock=0;closed=0;released=0;created=0;reads=0;largest=0;allowed=true;fragment=17
        response='HTTP/1.1 206 Partial Content\\r\\nContent-Length: 4\\r\\nContent-Range: bytes 0-3/100\\r\\nETag: "x"\\r\\n\\r\\nDATA'
        cursor=1; stall=false; txfail=false; connect_stall=false; native_overflow=false
        socket={ON_LINE=1,TX_OK=2,EVENT=3,CLOSED=4,
          create=function(_,cb) created=created+1;callback=cb;return {} end,
          config=function()return true end,
          connect=function()return true,not connect_stall end,
          tx=function(_,s) request=s;return not txfail,false,true end,
          rx=function(_,b,flag,limit)
            reads=reads+1;largest=math.max(largest,limit);assert(flag==0 and limit<=512 and #b.data==0)
            if stall then return true,0 end
            local n=native_overflow and limit+1 or math.min(limit,fragment)
            local data=response:sub(cursor,cursor+n-1);cursor=cursor+#data
            b.data=b.data..data -- Native socket.rx appends at buff.used, never overwrites old used bytes.
            return true,#data
          end,
          close=function()closed=closed+1 end,release=function()released=released+1 end}
        zbuff={create=function()
          return {data='',clear=function(self)self.data=string.rep('\0',#self.data)end,
            del=function(self)self.data=''end,
            query=function(self,offset,n)return self.data:sub(offset+1,offset+n)end}
        end}
        deps={socket=socket,zbuff=zbuff,now_ms=function()return clock end,
          wait=function(ms)clock=clock+ms;if pause_wait then allowed=false end end,
          can_read=function()return allowed end,native_rx_limit_verified=true}
        p=assert(M.new(deps))
        function get()return p.http_get('http://example.invalid/fw.zip',{Range='bytes=0-3'},4)end
        ''')

    # SAM | 2026-10-24 +08:00 | Native clear retains used; a second receive must append only after del resets that length.
    def test_native_append_reuses_empty_used_buffer(self):
        self.lua.execute("fragment=7;local r,e=get();assert(r and r.body=='DATA',tostring(e));assert(reads>2 and closed==1 and released==1)")

    def test_fragmented_success_and_close(self):
        self.lua.execute('''local r,e=get();assert(r and not e and r.body=='DATA' and r.status==206)
          assert(r.headers.etag=='"x"' and closed==1 and released==1 and largest<=512)
          assert(request:find('Connection: keep-alive',1,true) and request:find('Accept-Encoding: identity',1,true))''')

    # SAM | 2026-10-24 +08:00 | Official socket.tx full=true is transient; ignore done and retry only until the request is accepted.
    def test_tx_full_waits_and_accepted_request_is_not_resent(self):
        self.lua.execute('''
          local attempts=0;local accepted=0;local sent_request;local old_wait=deps.wait
          socket.tx=function(_,data)
            attempts=attempts+1
            if not sent_request then sent_request=data else assert(sent_request==data)end
            if attempts==1 then callback(nil,socket.TX_OK,0);return true,true,true end
            accepted=accepted+1;return true,false,false
          end
          deps.wait=function(ms)
            old_wait(ms)
            if accepted>0 then callback(nil,socket.TX_OK,0)end
          end
          local r,e=get();assert(r and r.body=='DATA',tostring(e))
          assert(attempts==2 and accepted==1 and clock>=40 and closed==1 and released==1)
        ''')

    def test_tx_full_does_not_skip_accepted_request_ack(self):
        self.lua.execute('''
          local attempts=0
          socket.tx=function()
            attempts=attempts+1
            if attempts==1 then callback(nil,socket.TX_OK,0);return true,true,true end
            return true,false,false
          end
          local r,e=get();assert(not r and e=='HTTP_TIMEOUT',tostring(e))
          assert(attempts==2 and reads==0 and released==1 and clock<=30020)
        ''')

    def test_tx_full_timeout_pause_and_peer_close_cleanup(self):
        self.lua.execute('''
          socket.tx=function()return true,true,true end
          local r,e=get();assert(not r and e=='HTTP_TIMEOUT',tostring(e))
          assert(reads==0 and released==1 and clock<=30020)
        ''')
        self.setUp()
        self.lua.execute('''
          socket.tx=function()return true,true,false end;pause_wait=true
          local r,e=get();assert(not r and e=='BUSINESS_PAUSED',tostring(e));assert(released==1)
        ''')
        self.setUp()
        self.lua.execute('''
          local attempts=0
          socket.tx=function()attempts=attempts+1;callback(nil,socket.CLOSED,0);return true,true,false end
          local r,e=get();assert(not r and e=='HTTP_EOF',tostring(e))
          assert(attempts==1 and reads==0 and released==1)
        ''')

    def test_ignored_range_rejected_before_body(self):
        self.lua.execute('''response='HTTP/1.1 200 OK\\r\\nContent-Length: 999999\\r\\n\\r\\n'..string.rep('X',9999)
          local r,e=get();assert(not r and e=='HTTP_RANGE_REQUIRED' and cursor<512 and released==1)''')

    def test_ambiguous_compressed_and_chunked_headers(self):
        for header in ['Content-Length: 4\r\ncontent-length: 4', 'Content-Length: 5',
                       'Content-Length: 4\r\nTransfer-Encoding: chunked',
                       'Content-Length: 4\r\nContent-Encoding: gzip',
                       'Content-Length: +4', 'Content-Length: 4\r\n folded: invalid']:
            with self.subTest(header=header):
                self.setUp()
                self.lua.globals().bad_header = header
                self.lua.execute('''response='HTTP/1.1 206 Partial Content\\r\\n'..bad_header..'\\r\\n\\r\\nDATA'
                  local r,e=get();assert(not r and released==1,tostring(e))''')

    def test_header_limit(self):
        self.lua.execute('''response='HTTP/1.1 206 Partial Content\\r\\nX: '..string.rep('A',5000)
          local r,e=get();assert(not r and e=='HTTP_HEADER_LIMIT' and cursor<=4097 and released==1)''')

    def test_timeout_and_pause_cleanup(self):
        self.lua.execute('''stall=true;local r,e=get();assert(not r and e=='HTTP_TIMEOUT' and clock<=30020 and released==1)''')
        self.setUp()
        self.lua.execute('''stall=true;pause_wait=true;local r,e=get();assert(not r and e=='BUSINESS_PAUSED' and released==1)''')

    def test_connect_and_send_failures(self):
        self.lua.execute('''connect_stall=true;local r,e=get();assert(not r and e=='HTTP_TIMEOUT' and released==1 and reads==0)''')
        self.setUp()
        self.lua.execute('''txfail=true;local r,e=get();assert(not r and e=='HTTP_SEND' and released==1)''')

    def test_injection_and_https_do_not_open(self):
        self.lua.execute('''for _,u in ipairs({'http://host/x\\r\\nInjected: 1','http://a@host/x','https://host/x','http://host:0/x'})do
          local r,e=p.http_get(u,{Range='bytes=0-3'},4);assert(not r and created==0,tostring(e))end
          local r,e=p.http_get('http://host/x',{Range='bytes=0-3',['If-Range']='"x"\\r\\nX: y'},4)
          assert(not r and created==0)''')

    def test_native_contract_required(self):
        self.lua.execute('''deps.native_rx_limit_verified=false;local r,e=M.new(deps);assert(not r and e=='HTTP_NATIVE_CONTRACT')''')

    def test_native_userdata_modules(self):
        self.lua.execute('''local native=assert(io.tmpfile());local old=getmetatable(native)
          debug.setmetatable(native,{__index=socket});deps.socket=native
          local r,e=M.new(deps);assert(r,tostring(e));assert(r.http_get('http://host/x',{Range='bytes=0-3'},4))
          debug.setmetatable(native,old);native:close()
          deps.socket=setmetatable({},{__index=function()error('private error')end})
          r,e=M.new(deps);assert(not r and e=='HTTP_NATIVE_API')''')

    def test_native_limit_violation_closes(self):
        self.lua.execute('''native_overflow=true;response=string.rep('A',9000)
          local r,e=get();assert(not r and e=='HTTP_NATIVE_OVERFLOW' and released==1)''')

    def test_bad_range_and_redirect(self):
        self.lua.execute('''local r,e=p.http_get('http://host/x',{Range='bytes=0-4'},4);assert(not r and created==0)
          response='HTTP/1.1 302 Found\\r\\nLocation: http://other/x\\r\\nContent-Length: 0\\r\\n\\r\\n'
          r,e=get();assert(not r and e=='HTTP_RANGE_REQUIRED' and released==1)''')

    # SAM | 2026-10-24 +08:00 | A terminal callback may race buffered response bytes; only a complete framed response may succeed.
    def test_terminal_error_after_final_buffered_bytes(self):
        self.lua.execute("local old=socket.rx;socket.rx=function(...)local ok,n=old(...);if cursor>#response then callback(nil,socket.EVENT,-1)end;return ok,n end;local r,e=get();assert(r and r.body=='DATA',tostring(e));assert(released==1)")

    def test_connect_failure_is_not_permitted_to_drain(self):
        self.lua.execute("socket.connect=function()return true,false end;deps.wait=function(ms)clock=clock+ms;callback(nil,socket.ON_LINE,-1)end;local r,e=get();assert(not r and e=='HTTP_SOCKET',tostring(e));assert(released==1 and reads==0)")

    def test_terminal_error_with_truncated_body_still_fails(self):
        self.lua.execute("response=response:sub(1,-2);local old=socket.rx;socket.rx=function(...)local ok,n=old(...);if cursor>#response then callback(nil,socket.EVENT,-1)end;return ok,n end;local r,e=get();assert(not r and (e=='HTTP_EOF' or e=='HTTP_SOCKET'),tostring(e));assert(released==1)")

    def test_peer_close_after_buffered_data(self):
        self.lua.execute('''local old=socket.rx;socket.rx=function(...)
          local ok,n=old(...);if cursor>#response then callback(nil,socket.CLOSED,0)end;return ok,n end
          local r,e=get();assert(r and r.body=='DATA',tostring(e))''')

    def test_peer_close_short_body(self):
        self.lua.execute('''response=response:sub(1,-2);local old=socket.rx;socket.rx=function(...)
          local ok,n=old(...);if cursor>#response then callback(nil,socket.CLOSED,0)end;return ok,n end
          local r,e=get();assert(not r and e=='HTTP_EOF' and released==1,tostring(e))''')


if __name__ == '__main__':
    unittest.main()
