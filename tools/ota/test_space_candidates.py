"""SAM | 2026-10-26 +08:00 | Exercise production space handler with read-only candidate IO and missing/error cases."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_cat_manager import runtime

def check(source=None):
    root=Path(__file__).resolve().parents[2]
    text=(Path(source) if source else root/'Air780EGH/update.lua').read_text(encoding='utf-8-sig')
    block=text[text.index('_G.at_cmd_handlers.OTA_SPACE ='):text.index('-- SAM | 2026-10-23 +08:00 | Explicit read-only inventory')]
    lua=runtime()
    lua.execute('''
      _G.at_cmd_handlers={}
      local old=string.rep('a',64);local new=string.rep('b',64)
      instance={status=function()return {phase='PAUSED',job={hash=new,size=432328},retired={job={hash=old}}}end}
      local paths=require('ota_candidates')
      local files={[paths.path(old)]=429256}
      io={fsstat=function()return true,128,116,4096 end,
          exists=function(p)return files[p]~=nil end,
          open=function(p,mode)
            assert(mode=='rb' and p==paths.path(old),'unexpected file access')
            return {seek=function(_,mode)assert(mode=='end');return files[p]end,close=function()return true end}
          end}
    ''')
    lua.execute(block)
    lua.execute('''
      local function query(cmd)
        local text;_G.at_cmd_handlers.OTA_SPACE(cmd,function(s)text=s end)
        return json.decode(text:sub(11))
      end
      local s=query('OTA_SPACE=FILES')
      assert(s.retired_bytes==429256 and s.current_bytes==0,'candidate sizes missing or incorrect')
      assert(s.free_bytes==49152 and not s.install_enabled)
      ota_uart_faulted=function()return false end;ota_uart_idle=function()return true end
      s=query('OTA_SPACE=FILES');assert(s.uart_faulted==false and s.uart_idle==true,'false readiness must remain explicit')
      s=query('OTA_SPACE');assert(s.retired_bytes==nil and s.current_bytes==nil)
      io.exists=function()return nil end
      s=query('OTA_SPACE=FILES');assert(s.current_bytes==nil and s.retired_bytes==nil,'unknown must not become zero')
      io.exists=function()return true end;io.open=function()error('private read exception')end
      s=query('OTA_SPACE=FILES');assert(s.current_bytes==nil and s.retired_bytes==nil)
      instance.status=function()return {phase='IDLE'}end
      s=query('OTA_SPACE=FILES');assert(s.current_bytes==nil and s.retired_bytes==nil)
    ''')
    print('PASS space candidate read-only sizes, absent=0, unknown/error omitted, no task or user-file writes')

if __name__=='__main__':check(sys.argv[1] if len(sys.argv)>1 else None)
