"""SAM | 2026-10-26 +08:00 | Check read-only IDLE diagnostics without invoking OTA or exposing arbitrary errors."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime

def check(path):
    text=path.read_text(encoding='utf-8-sig')
    start=text.index('_G.at_cmd_handlers.FOTA_STATUS =')
    end=text.index('\nend',start)+4
    lua=LuaRuntime()
    lua.execute("at_cmd_handlers={};output={};state={phase='IDLE'};instance={status=function()return state end};function send(s)output[#output+1]=s end")
    lua.execute('local instance=instance\n'+text[start:end])
    for reason in ['OUTBOX_FULL','BUSINESS_PAUSED','HTTP_BUSY',None,'https://secret.invalid/token']:
        lua.globals().instance.last_tick_reason=reason
        lua.execute('output={};at_cmd_handlers.FOTA_STATUS("FOTA_STATUS",send)')
        lines=list(lua.globals().output.values())
        assert lines[0]=='IDLE'
        if reason and '://' not in reason:
            assert 'OTA_STEP='+reason in lines,(str(path),reason,lines)
        assert not any('secret' in x for x in lines)
    lua.execute('state.outbox={{id=1},{id=2}};output={};at_cmd_handlers.FOTA_STATUS("FOTA_STATUS",send)')
    assert 'OTA_OUTBOX=2' in list(lua.globals().output.values())
    print('PASS read-only IDLE step visibility and error sanitization')

if __name__=='__main__':check(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'Air780EGH/update.lua')
