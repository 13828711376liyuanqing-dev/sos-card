"""SAM | 2026-10-24 +08:00 | Probe UART registration, async/busy boundaries and absence of installation side effects."""
import unittest
from test_cat_manager import runtime

SETUP = '''
local tasks,replies={},{};local calls=0;local idle=true;local phase='IDLE';local clock=1
sys={subscribe=function()end,taskInit=function(f)tasks[#tasks+1]=f end,wait=function()end}
mcu={ticks=function()return clock end};_G.at_cmd_handlers={};_G.PRODUCT_VERSION='1.0.2'
local function denied()error('side effect forbidden')end
fota={init=denied,run=denied,finish=denied};fskv={init=denied,set=denied};io={open=denied}
package.loaded.ota_runtime={start=function()return {status=function()return {phase=phase}end,accept=denied}end}
package.loaded.ota_platform={default=function()return {idle=function()return idle end}end}
package.loaded.ota_crypto={new=function()return {}end}
package.loaded.ota_trust={}
package.loaded.ota_http_range={new=denied,new_diagnostic=denied}
package.loaded.ota_diag_net={new=function(d)
 assert(d.native_rx_limit_verified~=true)
 return {http_get=function()end}
end}
package.loaded.ota_bundle={open=denied,open_diagnostic=function(p,input)
 calls=calls+1;assert(p.can_read() and (input.url=='http://example.invalid/test.zip' or input.url=='https://filebin.net/bin/fw.zip'))
 return {summary=function()return {source_version='1.0.2',target_version='1.5.0'}end,
 preflight_step=function()assert(p.can_read());return true,'VERIFIED'end,
 diagnostic_step=function()assert(p.can_read());return true,{stage='COMPLETE',gr_verified=true,cat_verified=true}end}
end}
require('update')
local handler=_G.at_cmd_handlers.OTA_NET_CHECK
assert(type(handler)=='function','missing diagnostic UART command')
local function send(s)replies[#replies+1]=s end
local function command(url)
 return 'OTA_NET_CHECK='..json.encode({Address=url or 'http://example.invalid/test.zip',Md5=string.rep('a',32),CurrentVersion='1.0.2',TargetVersion='1.5.0'})
end
'''


class CommandTests(unittest.TestCase):
    def check(self, body):
        runtime().execute(SETUP+body)

    def test_explicit_async_no_install_and_busy(self):
        self.check('''
        assert(#tasks==0);handler(command(),send);assert(#tasks==1 and calls==0)
        handler(command(),send);assert(#tasks==1 and replies[#replies]:find('BUSY',1,true))
        tasks[1]();assert(calls==1)
        local line=replies[#replies];assert(line:find('"install_enabled":false',1,true) and line:find('"stage":"COMPLETE"',1,true))
        assert(not line:find('http://',1,true))
        handler(command(),send);assert(#tasks==2)
        ''')

    def test_https_malformed_and_busy_business_do_not_schedule(self):
        self.check('''
        handler(command('https://example.invalid/test.zip'),send)
        assert(#tasks==0 and replies[#replies]:find('DIAG_TLS_HOST',1,true))
        handler('OTA_NET_CHECK={broken}',send);assert(#tasks==0)
        idle=false;handler(command(),send);assert(#tasks==0)
        idle=true;phase='INSTALLING';handler(command(),send);assert(#tasks==0)
        ''')

    def test_lost_idle_before_task_blocks_read_and_sanitizes_error(self):
        self.check('''
        handler(command(),send);assert(#tasks==1);idle=false;tasks[1]()
        assert(calls==0 and replies[#replies]:find('BUSINESS_PAUSED',1,true))
        ''')

    def test_known_filebin_https_is_scheduled_without_global_tls_gate(self):
        self.check('''
        handler(command('https://filebin.net/bin/fw.zip'),send)
        assert(#tasks==1 and calls==0);tasks[1]();assert(calls==1)
        assert(replies[#replies]:find('"stage":"COMPLETE"',1,true))
        ''')

    def test_compact_command_avoids_gr_cli_json_quote_processing(self):
        self.check('''
        handler('OTA_NET_CHECK=1.0.2,1.5.0,'..string.rep('a',32)..',https://filebin.net/bin/fw.zip',send)
        assert(#tasks==1);tasks[1]();assert(calls==1)
        ''')

    def test_task_creation_failure_does_not_leave_probe_busy(self):
        self.check('''
        sys.taskInit=function()error('private details')end
        assert(pcall(handler,command(),send))
        assert(replies[#replies]:find('DIAG_TASK_START',1,true))
        assert(not replies[#replies]:find('private',1,true))
        sys.taskInit=function(f)tasks[#tasks+1]=f end
        handler(command(),send);assert(#tasks==1)
        ''')


if __name__ == '__main__':
    unittest.main()
