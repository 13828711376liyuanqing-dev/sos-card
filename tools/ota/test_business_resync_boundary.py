"""SAM | 2026-10-26 +08:00 | A recovery hello needs an explicit boundary before GR's quarantined text parser."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "logs/cat1_antenna_20261010/python_deps"))
from lupa.lua53 import LuaRuntime


def main():
    source = (ROOT / "Air780EGH/business_runtime.lua").read_text(encoding="utf-8-sig")
    start = source.index("local uart_pending,")
    end = source.index("local service", start)
    lua = LuaRuntime()
    lua.execute(r'''
sent={};blocked=false;events={}
json={encode=function(v)return '{"op":"'..v.op..'","id":'..(v.id or 0)..'}' end}
sys={publish=function(e)events[#events+1]=e end}
uart_send_raw=function(s)
 if blocked then return false end
 sent[#sent+1]=s;return true
end
''')
    lua.execute(source[start:end] + "\n_G.emit_test=emit;_G.flush_test=flush_uart")
    lua.execute(r'''
assert(emit_test({op='hello',id=1}))
assert(sent[1]:sub(1,10)=='\r\nBUS_EVT=', 'RECOVERY_HELLO_HAS_NO_LEADING_BOUNDARY')
assert(#sent==1, 'boundary and hello must be one queue item')
assert(emit_test({op='network',id=2}))
assert(sent[2]:sub(1,8)=='BUS_EVT=', 'ordinary events changed framing')
blocked=true;sent={}
assert(emit_test({op='hello',id=3})==false)
assert(emit_test({op='hello',id=4})==false)
assert(emit_test({op='call',id=5})==false)
assert(business_uart_backlog())
blocked=false;flush_test();flush_test()
assert(#sent==2 and sent[1]=='\r\nBUS_EVT={"op":"hello","id":4}')
assert(sent[2]=='BUS_EVT={"op":"call","id":5}' and not business_uart_backlog())
''')
    # Use the actual serialized UART owner too: CRLF must survive intact and
    # cannot escape while GR owns a granted quiet window.
    from test_uart_flash_window import runtime
    writer = runtime()
    writer.execute('json={encode=function(v)return \'{"op":"\'..v.op..\'"}\' end}')
    writer.execute(source[start:end] + "\n_G.emit_test=emit")
    writer.execute(r'''
assert(emit_test({op='hello'}));pump()
assert(written[1]=='\r\nBUS_EVT={"op":"hello"}\r\n');sent()
feed(quiet(240));pump();sent()
local count=#written;assert(emit_test({op='hello'}));pump()
assert(#written==count,'resync boundary escaped a granted Flash lease')
feed(quiet(242));pump();sent()
assert(written[#written]=='\r\nBUS_EVT={"op":"hello"}\r\n')
''')
    print("PASS production emitter: recovery boundary atomic, retained under queue pressure, latest hello preserved; ordinary events unchanged")
    print("PASS actual UART writer: boundary bytes preserved and held until quiet release")


if __name__ == "__main__":
    main()
