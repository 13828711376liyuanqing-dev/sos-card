"""SAM | 2026-10-24 +08:00 | Diagnostic TLS requires a CA and bounded Filebin redirects; production HTTP does not silently gain TLS."""
import unittest
from test_cat_manager import runtime
import test_http_range as http_fixture


class TlsTests(unittest.TestCase):
    def test_tls_ca_is_required_and_passed_in_eighth_config_argument(self):
        f=http_fixture.HttpRangeTests();f.setUp()
        f.lua.execute('''
        p=assert(M.new_diagnostic(deps))
        local r,e=p.http_get('https://filebin.net/test',{Range='bytes=0-3'},4)
        assert(not r and e=='HTTP_TLS_CA')
        deps.tls_ca=function(host)assert(host=='filebin.net');return 'TRUSTED_CA'end
        local configured=false
        socket.config=function(sc,port,udp,tls,a,b,c,ca)
          assert(tls==true and udp==false and ca=='TRUSTED_CA')
          configured=true;return true
        end
        p=assert(M.new_diagnostic(deps))
        local r,e=p.http_get('https://filebin.net/test',{Range='bytes=0-3'},4)
        assert(r and r.body=='DATA' and configured,tostring(e))
        p=assert(M.new(deps))
        local r,e=p.http_get('https://filebin.net/test',{Range='bytes=0-3'},4)
        assert(not r and e=='HTTP_URL')
        ''')

    def test_header_probe_discards_html_body_and_keeps_cookie_header(self):
        f=http_fixture.HttpRangeTests();f.setUp()
        f.lua.execute('''
        response='HTTP/1.1 200 OK\\r\\nSet-Cookie: verified=ok; Secure; HttpOnly\\r\\nContent-Length: 50000\\r\\n\\r\\nHTML'
        p=assert(M.new_diagnostic(deps))
        local r,e=p.probe('http://example.invalid/test',{Range='bytes=0-0'})
        assert(r and r.status==200 and r.body=='' and r.headers['set-cookie']=='verified=ok; Secure; HttpOnly',tostring(e))
        assert(closed==1 and released==1)
        ''')

    def test_filebin_resolution_and_cookie_do_not_escape_allowlist(self):
        lua=runtime()
        lua.execute('''
        local calls={};local mode='ok'
        package.loaded.ota_http_range={new_diagnostic=function(d)
          assert(type(d.tls_ca)=='function' and d.tls_ca('filebin.net') and not d.tls_ca('evil.invalid'))
          return {
            probe=function(url,h)
              calls[#calls+1]={url=url,cookie=h.Cookie}
              if url=='https://filebin.net/bin/fw.zip' then
                if not h.Cookie then return {status=200,headers={['set-cookie']='verified=ok; Secure'}}end
                local host=mode=='evil' and 'evil.invalid' or 'storage.filebin.net'
                local scheme=mode=='http' and 'http' or 'https'
                return {status=302,headers={location=scheme..'://'..host..'/signed?token=private'}}
              end
              return {status=206,headers={}}
            end,
            http_get=function(url,h,n)
              assert(url=='https://storage.filebin.net/signed?token=private' and not h.Cookie)
              return {status=206,body='DATA',headers={ETag='"x"'},final_url=url}
            end}
        end}
        local module=require('ota_diag_net')
        local p=assert(module.new({can_read=function()return true end}))
        local url='https://filebin.net/bin/fw.zip'
        local r,e=p.http_get(url,{Range='bytes=0-3'},4)
        assert(r and r.body=='DATA' and r.final_url==url,tostring(e))
        assert(calls[2].cookie=='verified=ok')
        for _,m in ipairs({'evil','http'})do
          mode=m;p=assert(module.new({can_read=function()return true end}))
          local r,e=p.http_get(url,{Range='bytes=0-3'},4)
          assert(not r and e=='DIAG_REDIRECT_HOST',tostring(e))
        end
        ''')


if __name__=='__main__':
    unittest.main()
