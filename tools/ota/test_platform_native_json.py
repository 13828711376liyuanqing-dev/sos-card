"""SAM | 2026-10-24 +08:00 | Native JSON userdata must reach UART; unsupported codecs must still fail closed."""
import unittest
from test_cat_manager import runtime

class Encoder:
    def __init__(self, encode): self.encode = encode

class NativeJsonTests(unittest.TestCase):
    def test_native_userdata_sender(self):
        lua=runtime()
        lua.globals().json=Encoder(lua.globals().json.encode)
        lua.execute('''
        assert(type(json)=='userdata')
        local sent
        uart_send_raw=function(s)sent=s;return true end
        assert(require('ota_platform').default().send_gr({op='REQUEST'}))
        assert(sent=='OTA_CTL={"op":"REQUEST"}')
        ''')

    def test_absent_broken_and_oversize_codec_refused(self):
        lua=runtime()
        lua.execute('''
        local p=require('ota_platform').default();local writes=0
        uart_send_raw=function()writes=writes+1;return true end
        for _,v in ipairs({false,{}, {encode=function()error('native')end}, {encode=function()return string.rep('x',1001)end}})do
          json=v;assert(not p.send_gr({op='REQUEST'}))
        end
        json=nil;assert(not p.send_gr({}));assert(writes==0)
        ''')

if __name__=='__main__': unittest.main()
