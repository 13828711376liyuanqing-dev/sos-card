"""SAM | 2026-10-14 21:09 +08:00 | Drive actual SIM/MQTT/SIP Lua modules offline because this board cannot exercise physical card removal."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua54 import LuaRuntime

ROOT = Path(__file__).resolve().parents[2] / 'Air780EGH'


class SimRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(f'package.path="{ROOT.as_posix()}/?.lua;"..package.path')
        self.lua.execute('''
            callbacks={}; tasks={}; messages={}; events={}; lines={}; warnings={}; auto_calls={}
            anonymous=0; physical_ip=true; imsi=""; registered=1
            log={info=function() end,error=function(...) warnings[#warnings+1]={...} end,
                 warn=function(...) warnings[#warnings+1]={...} end}
            sys={}
            function sys.subscribe(n,f)
                callbacks[n]=callbacks[n] or {}; table.insert(callbacks[n],f)
            end
            function sys.publish(n,...)
                events[#events+1]={n,...}
                for _,f in ipairs(callbacks[n] or {}) do f(...) end
            end
            function sys.taskInit(f)
                anonymous=anonymous+1; tasks["anon"..anonymous]=coroutine.create(f)
            end
            function sys.taskInitEx(f,n) tasks[n]=coroutine.create(f) end
            function sys.wait(ms) return coroutine.yield("wait",ms) end
            function sys.waitUntil(n,ms) return coroutine.yield("event",n,ms) end
            function sys.waitMsg(n) return coroutine.yield("msg",n) end
            function sys.sendMsg(n,tag,...) messages[#messages+1]={name=n,value={tag,...}} end
            function sys.cleanMsg(n)
                for i=#messages,1,-1 do if messages[i].name==n then table.remove(messages,i) end end
            end
            function sys.timerStart(f,ms) return {f=f,ms=ms} end
            function sys.timerLoopStart(f,ms) return {f=f,ms=ms} end
            function sys.timerStop() end
            function step(n,...)
                assert(tasks[n],"missing task "..n)
                local ok,a,b=coroutine.resume(tasks[n],...); assert(ok,tostring(a)); return a,b
            end
            function pump(n)
                for i,v in ipairs(messages) do
                    if v.name==n then table.remove(messages,i); return step(n,v.value) end
                end
                error("missing message for "..n)
            end
            function count_event(n)
                local c=0; for _,v in ipairs(events) do if v[1]==n then c=c+1 end end; return c
            end
            function latest_line(prefix)
                for i=#lines,1,-1 do if lines[i]:sub(1,#prefix)==prefix then return lines[i] end end
            end
            mobile={setAuto=function(...) auto_calls[#auto_calls+1]={n=select("#",...),...} end,
                    imsi=function() return imsi end,status=function() return registered end,
                    imei=function() return "123456789012345" end,getCsq=function() return 20 end}
            socket={LWIP_GP=1,dft=function() return 1 end,adapter=function() return physical_ip end,
                    localIP=function() return "192.0.2.1" end,setDNS=function() end,sntp=function() end}
            _G.at_cmd_handlers={}
            _G.uart_send_raw=function(...)
                local t={};for i,v in ipairs({...}) do t[i]=tostring(v) end
                lines[#lines+1]=table.concat(t," ");return true
            end
            observer=require("netdrv_device")
            function online()
                sys.publish("SIM_IND","RDY"); sys.publish("IP_READY","192.0.2.1",1)
            end
        ''')

    def check(self, code):
        self.lua.execute(code)

    # SAM | 2026-10-20 16:36 +08:00 | Exercise the deployed mobile.csq API and unknown/error boundaries rather than the nonexistent getCsq stub.
    def test_signal_uses_current_api_and_rejects_stale_or_invalid_values(self):
        self.check('''
            mobile.csq=function() return 25 end
            assert(observer.csq()==99)
            online();assert(observer.csq()==25)
            for _,v in ipairs({0,31,99}) do mobile.csq=function() return v end;assert(observer.csq()==v) end
            for _,v in ipairs({-1,32,100,12.5,"25",false}) do
                mobile.csq=function() return v end;assert(observer.csq()==99)
            end
            mobile.csq=function() error("modem unavailable") end;assert(observer.csq()==99)
            mobile.csq=nil;assert(observer.csq()==99)
            mobile.csq=function() return 28 end
            sys.publish("SIM_IND","NORDY");assert(observer.csq()==99)
        ''')

    def test_bootstrap_does_not_override_live_removed_or_locked_card(self):
        for state in ('NORDY', 'SIM_PIN'):
            with self.subTest(state=state):
                self.setUp()
                self.check(f'sys.publish("SIM_IND","{state}"); imsi="cached"; step("anon1")')
                self.check(f'assert(observer.status()=="{state}" and not observer.ready())')

    def test_locked_sim_retires_network_once_and_rejects_late_ip(self):
        self.check('''
            online(); sys.publish("SIM_IND","SIM_PIN")
            assert(count_event("SIM_LOST")==1,"locked SIM did not retire sessions")
            local n=#lines
            sys.publish("SIM_IND","SIM_PIN");sys.publish("IP_READY","192.0.2.1",1)
            assert(#lines==n and count_event("SIM_LOST")==1)
            assert(not observer.ready() and not observer.ip_ready())
        ''')

    def test_fresh_sim_and_ip_required_before_network_readiness(self):
        self.check('''
            assert(not observer.ready() and not observer.ip_ready())
            online(); assert(observer.ready() and observer.ip_ready())
            sys.publish("SIM_IND","NORDY");sys.publish("IP_READY","192.0.2.1",1)
            assert(not observer.ip_ready())
            sys.publish("SIM_IND","RDY");assert(observer.ready() and not observer.ip_ready())
            sys.publish("IP_READY","192.0.2.1",2);assert(not observer.ip_ready())
            sys.publish("IP_READY","192.0.2.1",1);assert(observer.ip_ready())
            sys.publish("IP_LOSE",2);assert(observer.ip_ready())
            sys.publish("IP_LOSE",1);assert(not observer.ip_ready())
        ''')

    def test_auto_recovery_configured_once_with_reserved_nil_parameter(self):
        self.check('''
            step("anon1");step("anon1")
            assert(#auto_calls==1 and auto_calls[1].n==5)
            assert(auto_calls[1][1]==10000 and auto_calls[1][2]==0 and auto_calls[1][3]==5)
            assert(auto_calls[1][4]==nil and auto_calls[1][5]==60000)
        ''')

    def test_missing_auto_api_does_not_fabricate_sim_readiness(self):
        self.check('mobile.setAuto=nil;step("anon1");assert(#warnings>0 and not observer.ready())')

    # SAM | 2026-10-20 17:49 +08:00 | Finish host-verifiable recovery boundaries while physical hotplug awaits the next board revision.
    def test_auto_api_exception_leaves_state_unknown_and_task_alive(self):
        self.check('''
            mobile.setAuto=function() error("unsupported modem recovery") end
            step("anon1");assert(#warnings>0 and not observer.ready())
            step("anon1");assert(coroutine.status(tasks.anon1)=="suspended")
            online();assert(observer.ip_ready())
        ''')

    def test_duplicate_ready_does_not_retire_an_existing_ip_session(self):
        self.check('''
            online();local generation=observer.generation()
            sys.publish("SIM_IND","RDY")
            assert(observer.ip_ready() and observer.generation()==generation)
            assert(count_event("SIM_LOST")==0)
            sys.publish("IP_READY","192.0.2.1",1)
            assert(observer.generation()==generation)
        ''')

    def mqtt(self):
        self.check('''
            clients={}; business_ready=0; business_lost=0; receives=0
            package.loaded.mqtts_receiver={proc=function() receives=receives+1 end}
            package.loaded.mqtts_sender={TASK_NAME_PREFIX="test_",TASK_NAME="sender",is_ready=function() return false end}
            package.loaded.business_runtime={mqtt_ready=function() business_ready=business_ready+1 end,
                mqtt_lost=function() business_lost=business_lost+1 end}
            json={encode=function() return "{}" end}
            mqtt={create=function()
                local c={closed=0,disconnected=0}
                function c:auth() return true end
                function c:on(f) self.cb=f end
                function c:keepalive() end
                function c:will() end
                function c:connect() return true end
                function c:subscribe() return 9 end
                function c:disconnect() self.disconnected=self.disconnected+1 end
                function c:close() self.closed=self.closed+1 end
                clients[#clients+1]=c; return c
            end}
            require("mqtts_main")
        ''')

    def test_mqtt_waits_for_confirmed_sim_and_ip_not_stale_adapter(self):
        self.mqtt()
        self.check('step("test_main");assert(#clients==0);online();step("test_main");assert(#clients==1)')

    def test_mqtt_removed_client_callbacks_cannot_publish_or_receive(self):
        self.mqtt()
        self.check('''
            online();step("test_main");local c=clients[1]
            c.cb(c,"conack");sys.publish("SIM_IND","NORDY")
            c.cb(c,"suback",9,1);c.cb(c,"recv","test","data",{})
            assert(business_ready==0 and receives==0,"retired client revived business")
            assert(c.disconnected>0 and business_lost>0)
            sys.publish("SIM_IND","RDY");c.cb(c,"recv","test","data",{})
            assert(receives==0,"old client accepted after new card readiness")
        ''')

    def test_ip_only_loss_rebuilds_mqtt_without_sim_removal(self):
        self.mqtt()
        self.check('''
            online();step("test_main");local old=clients[1]
            old.cb(old,"conack");pump("test_main")
            old.cb(old,"suback",true,1);pump("test_main")
            sys.publish("IP_LOSE",1);pump("test_main");step("test_main")
            assert(old.closed==1 and observer.ready() and not observer.ip_ready())
            step("test_main");assert(#clients==1)
            sys.publish("IP_READY","192.0.2.2",1);step("test_main")
            local fresh=clients[2];assert(fresh and fresh~=old)
            old.cb(old,"suback",true,1);assert(business_ready==1)
            fresh.cb(fresh,"conack");pump("test_main")
            fresh.cb(fresh,"suback",true,1);pump("test_main")
            assert(business_ready==2)
        ''')

    def sip(self):
        self.check('''
            sip_starts=0; sip_stops=0; audio_stops=0; dial_count=0; sip_callbacks={}
            package.loaded.exsip={on=function(f) sip_callbacks[#sip_callbacks+1]=f end,
                init=function() return true end,start=function() sip_starts=sip_starts+1;return true end,
                stop=function() sip_stops=sip_stops+1 end,dial=function() dial_count=dial_count+1;return true end,
                accept=function() return true end,hangUp=function() return true end}
            package.loaded.audio_drv={initAudioDevice=function() return true end,
                deinitAudioDevice=function() audio_stops=audio_stops+1 end}
            package.loaded.tts={init=function() end,play=function() end}
            package.loaded.exaudio={}
            require("sip")
            function sip_init() _G.at_cmd_handlers.SIP_INIT("SIP_INIT",function() end);step("sip_app_main_task") end
        ''')

    # SAM | 2026-10-20 17:02 +08:00 | Audit full replacement sessions with the deployed boolean SUBACK, not only isolated loss callbacks.
    def test_mqtt_two_remove_reinsert_cycles_resubscribe_and_ignore_old_clients(self):
        self.mqtt()
        self.check('''
            online();step("test_main")
            local current=clients[#clients]
            current.cb(current,"conack");pump("test_main")
            current.cb(current,"suback",true,1);pump("test_main")
            assert(business_ready==1)
            for round=1,2 do
                local old=current
                sys.publish("SIM_IND","NORDY");pump("test_main")
                assert(old.disconnected>0)
                step("test_main");assert(old.closed==1)
                step("test_main");assert(#clients==round)
                sys.publish("SIM_IND","RDY");step("test_main");assert(#clients==round)
                sys.publish("IP_READY","192.0.2.1",1);step("test_main")
                current=clients[#clients];assert(current~=old)
                old.cb(old,"conack");old.cb(old,"suback",true,1)
                old.cb(old,"recv","down","old",{})
                assert(receives==0 and business_ready==round)
                current.cb(current,"conack");pump("test_main")
                assert(business_ready==round)
                current.cb(current,"suback",true,1);pump("test_main")
                assert(business_ready==round+1)
            end
        ''')

    def test_watchdog_does_not_reset_a_newly_recovered_network_generation(self):
        self.check('''
            reboots=0;rtos={reboot=function() reboots=reboots+1 end}
            package.loaded.ota_runtime={instance=function() return {reboot_allowed=function() return true end} end}
            require("network_watchdog");local name="anon"..anonymous
            online();step(name);step(name,false)
            -- The old session timed out, but IP recovers during its 3-second reboot delay.
            sys.publish("IP_LOSE",1);sys.publish("IP_READY","192.0.2.2",1)
            step(name)
            assert(reboots==0,"old watchdog timeout reset the newly recovered network")
        ''')

    # SAM | 2026-10-20 17:15 +08:00 | Preserve real timeout recovery and OTA protection while cancelling obsolete reboot decisions.
    def test_watchdog_feed_during_grace_cancels_reboot(self):
        self.check('''
            reboots=0;rtos={reboot=function() reboots=reboots+1 end}
            package.loaded.ota_runtime={instance=function() return {reboot_allowed=function() return true end} end}
            require("network_watchdog");local name="anon"..anonymous
            online();step(name);step(name,false)
            step(name,true)
            assert(reboots==0,"fresh feed did not cancel delayed reboot")
        ''')

    # SAM | 2026-10-20 17:26 +08:00 | A recovered session must not inherit the five-minute wait accumulated while offline or on a different IP session.
    def test_watchdog_recovery_during_long_wait_gets_a_fresh_window(self):
        for initially_online in (False, True):
            with self.subTest(initially_online=initially_online):
                self.setUp()
                self.check('''
                    reboots=0;rtos={reboot=function() reboots=reboots+1 end}
                    package.loaded.ota_runtime={instance=function() return {reboot_allowed=function() return true end} end}
                    require("network_watchdog");name="anon"..anonymous
                ''')
                if initially_online:
                    self.check('online()')
                self.check('''
                    step(name)
                    sys.publish("SIM_IND","NORDY");online()
                    local ok,kind,event,timeout=coroutine.resume(tasks[name],false)
                    assert(ok and kind=="event" and timeout==300000,"new session inherited old watchdog timeout")
                    assert(reboots==0)
                ''')

    def test_watchdog_unchanged_timeout_reboots_only_when_ota_allows(self):
        for allowed in (True, False):
            with self.subTest(allowed=allowed):
                self.setUp()
                self.check('''
                    reboots=0;rtos={reboot=function() reboots=reboots+1 end}
                    package.loaded.ota_runtime={instance=function() return {
                        reboot_allowed=function() return %s end} end}
                    require("network_watchdog");name="anon"..anonymous
                    online();step(name);step(name,false);step(name,false)
                    assert(reboots==%d,"unchanged timeout or OTA protection changed")
                ''' % ('true' if allowed else 'false', 1 if allowed else 0))

    def test_sip_no_sim_does_not_start_on_stale_adapter(self):
        self.sip()
        self.check('''
            sip_init();assert(sip_starts==0)
            local n=#messages
            _G.at_cmd_handlers.SIP_DIAL("SIP_DIAL=123",function(v) reply=v end)
            assert(reply:find("ERROR",1,true) and #messages==n)
            online();step("sip_app_main_task");assert(sip_starts==1)
        ''')

    def test_sip_loss_closes_audio_and_drops_old_callbacks_after_reinsert(self):
        self.sip()
        self.check('''
            online();sip_init();local old=sip_callbacks[#sip_callbacks]
            old("ready");pump("sip_app_main_task")
            _G.at_cmd_handlers.SIP_DIAL("SIP_DIAL=123",function() end);pump("sip_app_main_task")
            old("call","connected");pump("sip_app_main_task")
            sys.publish("SIM_IND","NORDY");pump("sip_app_main_task")
            assert(sip_stops>0 and audio_stops>0,"SIM loss did not release SIP/audio")
            assert(count_event("SIP_APP_MAIN_LOSE")==1,"active call failure not reported")
            online();old("call","incoming",{from="123"})
            old("call","connected");assert(#messages==0,"old SIP callbacks queued after reinsert")
            step("sip_app_main_task");assert(sip_starts==2 and dial_count==1)
        ''')

    def test_deferred_sip_call_does_not_dial_after_sim_generation_changes(self):
        self.sip()
        self.check('''
            online();_G.at_cmd_handlers.SIP_CALL("SIP_CALL=123",function() end)
            local request="anon"..anonymous
            sys.publish("SIM_IND","NORDY");online();step(request)
            assert(dial_count==0 and tasks.sip_app_main_task==nil,
                "old call request started after SIM replacement")
        ''')

    def test_actual_observer_boot_pin_loss_and_ready_reach_business(self):
        self.check('''
            saved={next_id=3,alarm_active=true,alarm_id=2,call_attempted=true,call_in={}}
            package.loaded.business_store={new=function() return {
                load=function() return saved end,save=function(_,v) saved=v;return true end}
                end,file_port=function() return {} end}
            package.loaded.mqtts_main={business_identity=function() return "TEST" end}
            json={encode=function(v) return (v.op or v.MsgType or "data")..":"..(v.state or v.code or "") end}
            mcu={ticks=function() return 1000 end}
            runtime=require("business_runtime")
            step("anon1")
            assert(latest_line("BUS_EVT=network:")=="BUS_EVT=network:unknown")
            sys.publish("SIM_IND","SIM_PIN")
            assert(latest_line("BUS_EVT=network:")=="BUS_EVT=network:no_sim")
            assert(latest_line("BUS_EVT=notice:")=="BUS_EVT=notice:SIM_PIN_REQUIRED")
            sys.publish("IP_READY","192.0.2.1",1); runtime.mqtt_ready()
            assert(latest_line("BUS_EVT=network:")=="BUS_EVT=network:no_sim")
            online();runtime.mqtt_ready()
            assert(latest_line("BUS_EVT=network:")=="BUS_EVT=network:mqtt")
            sys.publish("SIM_IND","NORDY");runtime.mqtt_lost();runtime.mqtt_ready()
            assert(latest_line("BUS_EVT=network:")=="BUS_EVT=network:no_sim")
            assert(saved.alarm_active and saved.alarm_id==2 and saved.call_attempted)
        ''')

    def test_watchdog_no_sim_and_loss_during_delay_do_not_reboot(self):
        self.check('''
            reboots=0;rtos={reboot=function() reboots=reboots+1 end}
            package.loaded.ota_runtime={instance=function() return {reboot_allowed=function() return true end} end}
            require("network_watchdog");local name="anon"..anonymous
            step(name)
            for i=1,6 do step(name,false) end
            assert(reboots==0,"no-SIM watchdog caused a reboot loop")
            online();step(name,false)
            sys.publish("SIM_IND","NORDY");step(name)
            assert(reboots==0,"SIM loss during watchdog delay caused reboot")
        ''')


if __name__ == '__main__':
    unittest.main()

