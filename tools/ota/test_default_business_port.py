"""SAM | 2026-10-23 20:12 +08:00 | Exercise actual default OTA ports and SIP events; no device writes."""
import unittest
from test_cat_manager import runtime


class DefaultBusinessPortTests(unittest.TestCase):
    def setUp(self):
        self.lua = runtime()
        self.lua.execute('''
          subs={}; lines={}; ip=true; identity='TEST_DEVICE'; ms=100
          saved=nil
          local store={load=function()return saved end,save=function(_,s)saved=clone(s);return true end}
          package.loaded.business_store={new=function()return store end,file_port=function()return {} end}
          package.loaded.mqtts_main={business_identity=function()return identity end}
          package.loaded.netdrv_device={ip_ready=function()return ip end,status=function()return 'RDY' end,csq=function()return 20 end}
          mobile={imei=function()return '123456789012345' end};mcu={ticks=function()return ms end}
          socket={LWIP_GP=1};sys={subscribe=function(n,f)subs[n]=f end,taskInit=function()end,publish=function()end}
          _G.uart_send_raw=function(line)lines[#lines+1]=line;return true end
          b=require('business_runtime');p=require('ota_platform').default()
          function event(n,...)assert(subs[n],n);subs[n](...)end
          function call_state()
            for i=#lines,1,-1 do
              local v=json.decode(lines[i]:sub(9));if v.op=='call' then return v.state end
            end
          end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_ready_reaches_gr_but_never_clears_alarm_or_active_call(self):
        self.check('''
          b.mqtt_ready();assert(p.idle()~=true,'unknown call was treated as idle')
          event('SIP_APP_MAIN_READY');assert(call_state()=='idle','ready never reaches GR')
          assert(p.idle()==true)
          event('SIP_APP_MAIN_CONNECTED');assert(p.idle()~=true)
          event('SIP_APP_MAIN_READY');assert(p.idle()~=true,'late ready hid connected call')
          event('SIP_APP_MAIN_DISCONNECTED');assert(p.idle()==true)
          b.command(json.encode({op='alarm',id=0}));assert(p.idle()~=true)
          event('SIP_APP_MAIN_READY');assert(p.idle()~=true,'ready cancelled alarm')
        ''')

    # SAM | 2026-10-24 +08:00 | On-demand SIP starts stopped, not unknowably active; starting or active sessions must still deny OTA.
    def test_stopped_sip_is_known_but_lifecycle_and_alarm_remain_authoritative(self):
        self.check('''
          local native={state='STATE_IDLE',task_running=false}
          assert(b.bind_sip_status(function()return native end))
          -- SAM | 2026-10-24 +08:00 | Hardware delivers the boot SIM snapshot after main's binding; the retired call must be re-observed on MQTT readiness.
          event('SIM_STATE','RDY');assert(p.idle()==false)
          b.mqtt_ready();assert(p.idle()==true and b.ota_status().call=='idle')
          native={state='STATE_INITING',task_running=true};event('SIP_APP_MAIN_STARTING')
          assert(p.idle()==false)
          native={state='STATE_READY',task_running=true};event('SIP_APP_MAIN_READY');assert(p.idle()==true)
          native={state='STATE_DIALING',task_running=true};assert(p.idle()==false)
          event('SIP_APP_MAIN_STOPPED');assert(p.idle()==false,'stale stopped event hid native dialing')
          native={state='STATE_CONNECTED',task_running=true};event('SIP_APP_MAIN_CONNECTED')
          assert(p.idle()==false)
          b.mqtt_ready();assert(p.idle()==false,'MQTT reconnect hid an active native call')
          native={state='STATE_IDLE',task_running=false};event('SIP_APP_MAIN_STOPPED')
          assert(p.idle()==false,'stopped snapshot hid an active business call')
          event('SIP_APP_MAIN_DISCONNECTED');event('SIP_APP_MAIN_STOPPED');assert(p.idle()==true)
          b.command(json.encode({op='alarm',id=0}));event('SIP_APP_MAIN_STOPPED');assert(p.idle()==false)
        ''')

    def test_network_loss_and_sip_loss_require_new_ready(self):
        self.check('''
          b.mqtt_ready();event('SIP_APP_MAIN_READY');assert(p.idle()==true)
          ip=false;event('IP_LOSE',1);assert(call_state()=='unknown' and p.idle()~=true)
          event('SIP_APP_MAIN_READY');assert(call_state()=='unknown')
          event('SIP_APP_MAIN_DISCONNECTED');assert(call_state()=='unknown','late call end revived retired session')
          ip=true;b.mqtt_ready();assert(p.idle()~=true)
          event('SIP_APP_MAIN_READY');assert(p.idle()==true)
          event('SIP_APP_MAIN_LOSE');assert(call_state()=='unknown' and p.idle()~=true)
        ''')

    def test_default_topics_bind_current_identity_and_no_install_authority(self):
        self.check('''
          assert(p.accept_topic('/iotplat/render3/WARNCARD3/TEST_DEVICE/down_raw')==true)
          assert(p.accept_topic('/iotplat/render3/WARNCARD3/OTHER/down_raw')==false)
          assert(p.outbox_topic({MsgType='otaReplyMsg'})=='/iotplat/datapush3/notsos/WARNCARD3/TEST_DEVICE')
          assert(p.outbox_topic({MsgType='otaResultMsg'})=='/iotplat/datapush3/notsos/WARNCARD3/TEST_DEVICE')
          assert(p.outbox_topic({MsgType='sosMsg'})==nil)
          identity='../+#';assert(p.accept_topic('/iotplat/render3/WARNCARD3/../+#/down_raw')==false)
          assert(p.outbox_topic({MsgType='otaReplyMsg'})==nil)
          identity=nil;assert(p.accept_topic('anything')==false)
          assert(p.safe()~=true and p.activate()~=true,'business readiness fabricated install authority')
        ''')

    def test_status_is_copy_and_store_failure_stays_closed(self):
        self.check('''
          b.mqtt_ready();event('SIP_APP_MAIN_READY')
          local s=b.ota_status();assert(s.idle==true and s.call=='idle')
          s.idle=false;s.call='connected';assert(b.ota_status().idle==true)
          package.loaded.business_runtime=nil
          package.loaded.business_store={new=function()return {load=function()return nil,'CORRUPT' end}end,file_port=function()return {}end}
          b=require('business_runtime');b.mqtt_ready();event('SIP_APP_MAIN_READY')
          assert(b.ota_status().known==false and p.idle()~=true)
        ''')

    def test_actual_hello_reports_compiled_cat_versions(self):
        self.check('''
          _G.VERSION='001.000.002';_G.PRODUCT_VERSION='1.0.2';_G.FW_RELEASE_BUILD=3
          b.command(json.encode({op='hello'}))
          local hello
          -- SAM | 2026-10-28 10:50 +08:00 | Strip the real resync boundary because hello intentionally starts with CRLF.
          for _,line in ipairs(lines)do line=line:gsub('^\\r\\n','');if line:sub(1,8)=='BUS_EVT=' then local v=json.decode(line:sub(9));if v.op=='hello' then hello=v end end end
          assert(hello.component_version=='001.000.002' and hello.product_build_version=='1.0.2' and hello.build==3)
          assert(hello.release_confirmed==nil,'compiled identity fabricated whole-release acceptance')
        ''')

    def test_early_journal_startup_and_service_exceptions_remain_closed(self):
        self.check('''
          local business=package.loaded.business_runtime;local mqtt=package.loaded.mqtts_main
          package.loaded.business_runtime=nil;package.loaded.mqtts_main=nil
          assert(p.idle()==false and p.accept_topic('anything')==false)
          assert(p.outbox_topic({MsgType='otaReplyMsg'})==nil)
          package.loaded.business_runtime={ota_status=function()error('unready')end}
          package.loaded.mqtts_main={business_identity=function()error('unready')end}
          assert(p.idle()==false and p.accept_topic('anything')==false)
          assert(p.outbox_topic({MsgType='otaReplyMsg'})==nil)
          package.loaded.business_runtime=business;package.loaded.mqtts_main=mqtt
        ''')


if __name__ == '__main__':
    unittest.main()
