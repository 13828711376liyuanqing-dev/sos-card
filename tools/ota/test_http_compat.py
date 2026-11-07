"""SAM | 2026-11-04 +08:00 | New-backend compatibility in ota_http_range (openresty: repeated Accept-Ranges/Vary, unquoted
ETag, empty reason phrase): non-critical repeats pass, critical repeats still fail, plain unquoted ETag is quoted,
odd/weak ETags still fail, ETag change still fails; the streaming (200) path gets the same header rule. Host only."""
import unittest
from test_http_range import HttpRangeTests

NEW = ('HTTP/1.1 206 \\r\\nContent-Length: 4\\r\\nAccept-Ranges: bytes\\r\\nAccept-Ranges: bytes\\r\\n'
       'Content-Range: bytes 0-3/100\\r\\nEtag: file_pWMx.zip\\r\\nVary: Origin\\r\\nVary: A\\r\\nVary: B\\r\\n\\r\\nDATA')


class HttpCompat(HttpRangeTests):
    def get(self, response, extra=''):
        self.lua.execute("response='%s';cursor=1;%s" % (response, extra))
        return self.lua.eval("(function() local r,e=get(); return r and r.headers.etag or false, e end)()")

    def test_new_backend_headers_accepted_and_etag_quoted(self):
        self.assertEqual(self.get(NEW), ('"file_pWMx.zip"', None))

    def test_if_range_matches_quoted_form(self):
        self.lua.execute("response='%s';cursor=1" % NEW)
        self.lua.execute('''local r,e=p.http_get('http://example.invalid/fw.zip',{Range='bytes=0-3',['If-Range']='"file_pWMx.zip"'},4)
          assert(r and r.body=='DATA',tostring(e));assert(request:find('If-Range: "file_pWMx.zip"',1,true))''')

    def test_etag_change_still_rejected(self):
        self.lua.execute("response='%s';cursor=1" % NEW.replace('file_pWMx.zip', 'file_other.zip'))
        self.lua.execute('''local r,e=p.http_get('http://example.invalid/fw.zip',{Range='bytes=0-3',['If-Range']='"file_pWMx.zip"'},4)
          assert(r==nil and e=='HTTP_ENTITY_CHANGED',tostring(e))''')

    def test_critical_repeats_still_rejected(self):
        for dup in ('Content-Length: 4', 'Content-Range: bytes 0-3/100', 'Etag: file_pWMx.zip',
                    'Transfer-Encoding: chunked', 'Content-Encoding: identity', 'Location: http://x/'):
            with self.subTest(dup=dup):
                resp = NEW.replace('\\r\\n\\r\\nDATA', '\\r\\n%s\\r\\n%s\\r\\n\\r\\nDATA' % (dup, dup)) \
                    if dup.split(':')[0] not in ('Content-Length', 'Content-Range', 'Etag') else \
                    NEW.replace('\\r\\n\\r\\nDATA', '\\r\\n%s\\r\\n\\r\\nDATA' % dup)
                self.assertEqual(self.get(resp), (False, 'HTTP_DUPLICATE_HEADER'))

    def test_odd_or_weak_etag_still_rejected(self):
        for bad in ('W/"weak"', 'a b', 'a"b', 'W/x', 'x' * 127):
            with self.subTest(bad=bad):
                self.assertEqual(self.get(NEW.replace('file_pWMx.zip', bad.replace('"', '\\"'))), (False, 'HTTP_ETAG'))

    def test_streaming_200_same_header_rule(self):
        ok = ('HTTP/1.1 200 \\r\\nContent-Length: 4\\r\\nAccept-Ranges: bytes\\r\\nAccept-Ranges: bytes\\r\\n'
              'Etag: file_pWMx.zip\\r\\nVary: A\\r\\nVary: B\\r\\n\\r\\nDATA')
        self.lua.execute("response='%s';cursor=1" % ok)
        self.lua.execute("local s,e=p.open_stream('http://example.invalid/x');assert(s and s.status==200,tostring(e));assert(s.read(4)=='DATA')")
        bad = ok.replace('Content-Length: 4\\r\\n', 'Content-Length: 4\\r\\nContent-Length: 4\\r\\n')
        self.lua.execute("response='%s';cursor=1" % bad)
        self.lua.execute("local s,e=p.open_stream('http://example.invalid/x');assert(s==nil and e=='HTTP_DUPLICATE_HEADER',tostring(e))")

    def test_quoted_etag_unchanged(self):
        self.assertEqual(self.get(NEW.replace('file_pWMx.zip', '\\"v1\\"')), ('"v1"', None))


if __name__ == '__main__':
    names = [n for n in dir(HttpCompat) if n.startswith('test_') and n not in dir(HttpRangeTests)]
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(HttpCompat(n) for n in names))
    raise SystemExit(0 if result.wasSuccessful() else 1)
