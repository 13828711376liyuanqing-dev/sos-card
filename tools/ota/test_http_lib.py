"""SAM | 2026-11-06 +08:00 | Range segments through the firmware HTTP library (device: `http` is userdata, request().wait() -> code, headers, body).
Same 206 / Content-Range / length / ETag checks as the raw socket path; streaming reads and hosts without the library keep the raw socket."""
import unittest
from test_cat_manager import runtime


class HttpLibTests(unittest.TestCase):
    def setUp(self):
        self.lua = runtime()
        self.lua.execute('''
        M=require('ota_http_range')
        clock=0;allowed=true;raw_created=0;calls=0;sent=nil
        code=206;body='DATA'
        hdr={['Content-Range']='bytes 0-3/100',['ETag']='"x"',['Content-Length']='4'}
        lib_error=false
        http={request=function(method,url,headers,payload,opts)
          calls=calls+1;sent={method=method,url=url,headers=headers,opts=opts}
          if lib_error then error('boom') end
          return {wait=function()return code,hdr,body end}
        end}
        socket={ON_LINE=1,TX_OK=2,EVENT=3,CLOSED=4,
          create=function()raw_created=raw_created+1;return {} end,
          config=function()return true end,
          connect=function()return true,true end,
          tx=function()return true,false,true end,
          rx=function()return false,0 end,
          close=function()end,release=function()end}
        zbuff={create=function()
          return {data='',clear=function(self)end,del=function(self)self.data=''end,
            query=function(self,offset,n)return self.data:sub(offset+1,offset+n)end}
        end}
        deps={socket=socket,zbuff=zbuff,now_ms=function()return clock end,wait=function(ms)clock=clock+ms end,
          can_read=function()return allowed end,native_rx_limit_verified=true}
        p=assert(M.new(deps))
        function get(h)return p.http_get('http://example.invalid/fw.zip?appId=1&signature=abc',h or {Range='bytes=0-3'},4)end
        ''')

    def test_range_segment_through_library(self):
        self.lua.execute('''local r,e=get();assert(r and not e and r.body=='DATA' and r.status==206,tostring(e))
          assert(calls==1 and raw_created==0)
          assert(sent.method=='GET' and sent.url=='http://example.invalid/fw.zip?appId=1&signature=abc')
          assert(sent.headers.Range=='bytes=0-3' and sent.opts.timeout==30000)
          assert(r.headers.etag=='"x"' and r.headers['content-range']=='bytes 0-3/100')''')

    def test_unquoted_etag_and_duplicate_style_headers(self):
        self.lua.execute('''hdr.ETag='file_abc.zip';local r,e=get();assert(r and r.headers.etag=='"file_abc.zip"',tostring(e))''')

    def test_wrong_status_content_range_and_length_rejected(self):
        self.lua.execute('''code=200;local r,e=get();assert(not r and e=='HTTP_RANGE_REQUIRED',tostring(e))
          code=206;body='DAT';r,e=get();assert(not r and e=='HTTP_LENGTH',tostring(e))
          body='DATA';hdr['Content-Range']='bytes 4-7/100';r,e=get();assert(not r and e=='HTTP_CONTENT_RANGE',tostring(e))
          hdr['Content-Range']='bytes 0-3/100';hdr.ETag=nil;r,e=get();assert(not r and e=='HTTP_ETAG',tostring(e))''')

    def test_if_range_must_match_entity(self):
        self.lua.execute('''local r,e=get({Range='bytes=0-3',['If-Range']='"y"'});assert(not r and e=='HTTP_ENTITY_CHANGED',tostring(e))
          r,e=get({Range='bytes=0-3',['If-Range']='"x"'});assert(r and r.body=='DATA',tostring(e));assert(sent.headers['If-Range']=='"x"')''')

    def test_library_error_and_pause(self):
        self.lua.execute('''lib_error=true;local r,e=get();assert(not r and e=='HTTP_LIB_ERROR',tostring(e));lib_error=false
          allowed=false;r,e=get();assert(not r and e=='BUSINESS_PAUSED',tostring(e))''')

    def test_no_library_keeps_raw_socket(self):
        self.lua.execute('''http=nil;local r,e=get();assert(not r and raw_created==1,tostring(e))''')

    def test_streaming_keeps_raw_socket(self):
        self.lua.execute('''local r,e=p.open_stream('http://example.invalid/fw.zip');assert(raw_created==1 and calls==0,tostring(e))''')


if __name__ == '__main__':
    unittest.main()
