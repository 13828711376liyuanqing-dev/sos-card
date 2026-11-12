"""SAM | 2026-10-13 09:14 +08:00 | Exercise CAT alarm persistence and delivery boundaries offline because device and platform are unavailable."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "logs/cat1_antenna_20261010/python_deps"))
from lupa.lua54 import LuaRuntime


ROOT = Path(__file__).resolve().parents[2] / "Air780EGH"


class BusinessTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(f'package.path = "{ROOT.as_posix()}/?.lua;" .. package.path')
        self.lua.execute('''
            saved=nil; events={}; published={}; dials={}; now=1800000000; ms=1000; synced=true
            store={load=function() return saved end,save=function(_,v) saved=v; return true end}
            port={store=store,emit=function(v) events[#events+1]=v end,
                imei=function() return "123456789012345" end,csq=function() return 20 end,
                version=function() return "001.000.000" end,
                time=function() return now end,time_valid=function() return synced end,millis=function() return ms end,
                publish=function(kind,v,cb) published[#published+1]={kind=kind,msg=v}; cb(true) end,
                dial=function(number) dials[#dials+1]=number; return true end,
                call_control=function() return true end}
            core=require("business_core")
            s=core.new(port)
            -- SAM | 2026-10-14 21:09 +08:00 | Standalone business tests inject a ready observer; physical/observer transitions are exercised in test_sim_recovery.py.
            -- SAM | 2026-10-20 16:36 +08:00 | Model the shared measured signal interface used by runtime and AT_INFO.
            package.loaded.netdrv_device={ip_ready=function() return true end,status=function() return "RDY" end,csq=function() return 20 end}
        ''')

    def value(self, expression):
        return self.lua.eval(expression)

    # SAM | 2026-11-07 +08:00 | The persisted phone owner must project state to GR only after successful storage.
    def test_committed_phone_snapshot_and_hello_restore(self):
        self.lua.execute('''
            local number="12345678901234567890123456789012"
            s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut=number,CallInList={}})
            assert(events[#events].op=="phone_bind" and events[#events].call_out==number)
            events={};s=core.new(port);s:hello()
            assert(events[1].op=="hello" and events[1].call_out==number)
            assert(#dials==0)
        ''')

    def test_failed_phone_save_does_not_project_uncommitted_number(self):
        self.lua.execute('''
            s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="10004",CallInList={}})
            events={};port.store.save=function()return false end
            s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="10008",CallInList={}})
            for _,event in ipairs(events) do assert(event.op~="phone_bind") end
            assert(s:state().call_out=="10004" and saved.call_out=="10004")
        ''')

    def test_phone_clear_projects_empty_destination(self):
        self.lua.execute('''
            s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="10004",CallInList={}})
            events={};s:downlink({MsgType="phoneBindMsg",CmdType=1})
            assert(events[#events].op=="phone_bind" and events[#events].call_out=="")
            assert(s:state().call_out==nil)
        ''')

    def test_all_changed_lua_sources_parse(self):
        for name in ("business_core.lua", "business_store.lua", "business_runtime.lua",
                     "main.lua", "uart_app.lua", "mqtts_main.lua", "mqtts_sender.lua",
                     "mqtts_receiver.lua"):
            with self.subTest(name=name):
                result = self.lua.eval("load")(ROOT.joinpath(name).read_text(encoding="utf-8"))
                self.assertIsNotNone(result)

    def test_duplicate_alarm_and_reboot_do_not_redial(self):
        self.lua.execute('s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="18812345678",CallInList={}})')
        self.lua.execute('s:command({op="alarm",id=0}); s:command({op="alarm",id=0})')
        self.assertEqual(self.value('#dials'), 1)
        self.assertEqual(self.value('saved.alarm_id'), 1)
        self.assertEqual(self.value('saved.call_attempted'), True)
        self.lua.execute('s=core.new(port); s:hello(); s:command({op="alarm",id=0})')
        self.assertEqual(self.value('#dials'), 1)
        self.assertEqual(self.value('events[#events].op'), 'alarm_state')
        self.lua.execute('s:hello()')
        self.assertEqual(self.value('events[#events-2].state'), 'unknown')

    # SAM | 2026-11-04 +08:00 | QP owns dialing; state synchronization must still persist and publish SOS.
    def test_qp_alarm_sync_never_dials_but_keeps_alarm_delivery(self):
        self.lua.execute('s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="18812345678",CallInList={}})')
        self.lua.execute('s:command({op="alarm",id=0,dial=false}); s:network("mqtt")')
        self.assertEqual(self.value('#dials'), 0)
        self.assertTrue(self.value('saved.alarm_active'))
        self.assertEqual(self.value('published[1].msg.MsgType'), 'sosMsg')
        self.lua.execute('s:command({op="alarm",id=0,dial=false}); s=core.new(port); s:command({op="alarm",id=0,dial=false})')
        self.assertEqual(self.value('#dials'), 0)
        self.lua.execute('s:command({op="cancel",id=saved.alarm_id})')
        self.assertFalse(self.value('saved.alarm_active'))

    def test_invalid_dial_owner_does_not_start_alarm(self):
        self.lua.execute('s:command({op="alarm",id=0,dial="false"})')
        self.assertEqual(self.value('saved == nil'), True)

    def test_broker_ack_does_not_clear_alarm(self):
        self.lua.execute('s:command({op="alarm",id=0}); s:network("mqtt")')
        self.assertEqual(self.value('#published'), 1)
        self.assertEqual(self.value('published[1].msg.MsgType'), 'sosMsg')
        self.assertEqual(self.value('saved.alarm_active'), True)
        self.assertEqual(self.value('saved.alarm_acked'), False)
        self.lua.execute('s:downlink({MsgType="sosReplyMsg",Status="success",Time=now})')
        self.assertEqual(self.value('saved.alarm_acked'), True)
        self.assertEqual(self.value('events[#events].op'), 'alarm_ack')

    def test_store_failure_rejects_alarm(self):
        self.lua.execute('store.save=function() return false,"STORE_COMMIT_FAILED" end; s:command({op="alarm",id=0})')
        self.assertEqual(self.value('#dials'), 0)
        self.assertEqual(self.value('events[#events].code'), 'STORE_COMMIT_FAILED')

    # SAM | 2026-10-25 +08:00 | Recover the durable platform acknowledgement after a UART backlog or CAT reset.
    def test_hello_replays_current_durable_alarm_ack(self):
        self.lua.execute('''
            s:command({op="alarm",id=0});s:network("mqtt")
            s:downlink({MsgType="sosReplyMsg",Status="success",Time=now})
            events={};s=core.new(port);s:hello()
            local found=false
            for _,v in ipairs(events)do if v.op=='alarm_ack' and v.id==saved.alarm_id then found=true end end
            assert(found,'durable alarm acknowledgement disappeared after restart')
            s:command({op='cancel',id=saved.alarm_id});events={};s:hello()
            for _,v in ipairs(events)do assert(v.op~='alarm_ack','cancelled alarm replayed acknowledgement')end
        ''')

    def test_unsynced_time_keeps_alarm_without_cloud_publish(self):
        self.lua.execute('synced=false; s:command({op="alarm",id=0}); s:network("mqtt")')
        self.assertEqual(self.value('saved.alarm_active'), True)
        self.assertEqual(self.value('#published'), 0)
        self.lua.execute('synced=true; s:time()')
        self.assertEqual(self.value('#published'), 1)

    def test_four_attempts_then_next_online_compensates_same_event(self):
        self.lua.execute('s:command({op="alarm",id=0}); s:network("mqtt")')
        self.lua.execute('s:network("mqtt"); s:time()')
        self.assertEqual(self.value('#published'), 1)
        self.lua.execute('for i=1,3 do ms=ms+60000; s:tick() end')
        self.assertEqual(self.value('#published'), 4)
        self.lua.execute('ms=ms+60000; s:tick(); s:network("mqtt")')
        self.assertEqual(self.value('#published'), 4)
        self.lua.execute('s:network("offline"); s:network("mqtt")')
        self.assertEqual(self.value('#published'), 5)
        self.assertEqual(self.value('published[1].msg.RelatedValue'), self.value('published[5].msg.RelatedValue'))

    def test_phone_reply_and_low_battery_are_persisted_then_delivered(self):
        self.lua.execute('''
            s:downlink({MsgType="phoneBindMsg",CmdType=0,
                CallOut="18812345678",CallInList={"18812345679"}})
            assert(saved.phone_reply~=nil)
            s:command({op="battery",known=true,battery=24})
            assert(saved.low_battery_pending.level==24)
            s:network("mqtt")
        ''')
        self.assertEqual(self.value('published[1].msg.MsgType'), 'onlineMsg')
        self.assertEqual(self.value('published[2].msg.MsgType'), 'phoneBindReplyMsg')
        self.assertEqual(self.value('published[3].msg.MsgType'), 'lowBatteryMsg')
        self.assertEqual(self.value('saved.phone_reply'), None)
        self.assertEqual(self.value('saved.low_battery_pending'), None)
        self.lua.execute('s:command({op="battery",known=true,battery=23})')
        self.assertEqual(self.value('#published'), 3)

    def test_cancel_and_call_are_separate(self):
        self.lua.execute('s:command({op="alarm",id=0}); s:call("ended")')
        self.assertEqual(self.value('saved.alarm_active'), True)
        self.lua.execute('s:command({op="cancel",id=1})')
        self.assertEqual(self.value('saved.alarm_active'), False)
        self.lua.execute('s:command({op="alarm",id=1})')
        self.assertEqual(self.value('saved.alarm_active'), False)
        self.assertEqual(self.value('#dials'), 0)

    # SAM | 2026-10-14 20:53 +08:00 | Reproduce late network callbacks after SIM loss because no-SIM must remain authoritative until SIM readiness.
    def test_sim_loss_blocks_late_network_events_and_cloud_sends(self):
        self.lua.execute('''
            s:command({op="alarm",id=0}); s:network("mqtt")
            local id=saved.alarm_id
            local attempted=saved.call_attempted
            s:network("no_sim")
            local before=#published
            ms=ms+60001
            s:network("offline"); s:network("ip"); s:network("mqtt")
            s:tick(); s:hello()
            assert(#published==before, "late MQTT callback published after SIM loss")
            assert(events[#events-3].op=="network" and events[#events-3].state=="no_sim",
                "hello must retain no-SIM state")
            assert(saved.alarm_active and saved.alarm_id==id and saved.call_attempted==attempted)
        ''')

    def test_sim_ready_reopens_network_without_redial_or_parameter_reset(self):
        self.lua.execute('''
            s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="18812345678",CallInList={}})
            s:command({op="alarm",id=0}); s:network("mqtt")
            local id=saved.alarm_id
            s:network("no_sim"); s:network("mqtt")
            assert(events[#events].state=="no_sim", "stale MQTT must be ignored")
            local before=#published
            ms=ms+60001
            s:network("registering"); s:network("ip"); s:network("mqtt")
            assert(events[#events].op=="network" and events[#events].state=="mqtt")
            assert(#published>before and #dials==1)
            assert(saved.alarm_active and saved.alarm_id==id and saved.call_out=="18812345678")
        ''')

    def test_runtime_sim_loss_and_ready_follow_actual_subscriptions(self):
        self.lua.execute('''
            package.loaded.business_store={new=function() return store end,file_port=function() return {} end}
            package.loaded.mqtts_main={business_identity=function() return "TEST" end}
            saved={next_id=2,alarm_active=true,alarm_id=1,call_attempted=true,call_in={}}
            json={encode=function(v) return v.op..":"..(v.state or v.code or "") end}
            mobile={imei=function() return "123456789012345" end,getCsq=function() return 20 end}
            mcu={ticks=function() return ms end}; socket={sntp=function() end}
            subs={}; sent={}
            sys={subscribe=function(name,fn) subs[name]=fn end,taskInit=function() end,publish=function() end}
            _G.uart_send_raw=function(v) sent[#sent+1]=v; return true end
            local function latest_network()
                for i=#sent,1,-1 do
                    if sent[i]:find("BUS_EVT=network:",1,true) then return sent[i] end
                end
            end
            runtime=require("business_runtime")
            runtime.mqtt_ready(); subs.SIM_LOST()
            assert(sent[#sent]=="BUS_EVT=network:no_sim")
            subs.IP_LOSE(); subs.IP_READY(); runtime.mqtt_ready()
            assert(sent[#sent]=="BUS_EVT=network:no_sim", "runtime revived a removed SIM")
            subs.SIM_STATE("RDY"); subs.IP_READY(); runtime.mqtt_ready()
            assert(latest_network()=="BUS_EVT=network:mqtt")
            subs.SIM_STATE("NORDY"); runtime.mqtt_ready()
            assert(sent[#sent]=="BUS_EVT=network:no_sim")
            assert(saved.alarm_active and saved.alarm_id==1 and saved.call_attempted)
        ''')

    def test_runtime_sip_error_callback_uses_live_service(self):
        self.lua.execute('''
            package.loaded.business_store={new=function() return {
                load=function() return {next_id=1,alarm_active=false,alarm_id=0,
                    call_out="18812345678",call_in={}} end,
                save=function() return true end} end,
                file_port=function() return {} end}
            package.loaded.mqtts_main={business_identity=function() return "TEST" end}
            json={encode=function(v) return v.op..":"..(v.state or v.code or "") end,
                decode=function() return {op="alarm",id=0} end}
            mobile={imei=function() return "123456789012345" end,
                getCsq=function() return 20 end}
            mcu={ticks=function() return 1000 end}
            socket={}
            sys={subscribe=function() end,taskInit=function() end,publish=function() end}
            _G.at_cmd_handlers={SIP_CALL=function(_,send) send("ERROR: sip register timeout") end}
            sent={}
            _G.uart_send_raw=function(value) sent[#sent+1]=value; return true end
            runtime=require("business_runtime")
            runtime.command("alarm")
        ''')
        self.assertEqual(self.value('sent[#sent]'), 'BUS_EVT=call:failed')
        self.lua.execute('''
            runtime.downlink("/iotplat/render3/WARNCARD3/TEST/down_raw",
                {MsgType="phoneBindMsg",CmdType=0,CallOut="123",CallInList={}},
                '{"MsgType":"phoneBindMsg","CmdType":0,"CallOut":"123","Call\\\\u0049nList":{},"x":{"CallInList":[]}}')
        ''')
        self.assertEqual(self.value('sent[#sent]'), 'BUS_EVT=notice:PHONE_DATA_INVALID')

    def test_runtime_accept_hangup_reports_command_errors(self):
        # SAM | 2026-10-13 13:24 +08:00 | Exercise actual runtime callbacks because pcall success is not SIP command acceptance.
        self.lua.execute('''
            package.loaded.business_store={new=function() return store end,file_port=function() return {} end}
            saved={next_id=2,alarm_active=true,alarm_id=1,call_attempted=true,call_in={}}
            package.loaded.mqtts_main={business_identity=function() return "TEST" end}
            command={op="accept"}; sent={}; controls={}
            json={encode=function(v) return v.op..":"..(v.state or v.code or "") end,
                decode=function() return command end}
            mobile={imei=function() return "123456789012345" end,getCsq=function() return 20 end}
            mcu={ticks=function() return ms end}; socket={}
            sys={subscribe=function() end,taskInit=function() end,publish=function() end}
            _G.uart_send_raw=function(v) sent[#sent+1]=v; return true end
            local function reject(key,cb) controls[#controls+1]=key; cb("ERROR: SIP not initialized") end
            _G.at_cmd_handlers={SIP_ACCEPT=reject,SIP_HANGUP=reject}
            runtime=require("business_runtime"); runtime.command("accept")
            assert(sent[#sent]=="BUS_EVT=notice:CALL_CONTROL_FAILED")
            command={op="hangup"}; runtime.command("hangup")
            assert(controls[#controls]=="SIP_HANGUP" and sent[#sent]=="BUS_EVT=notice:CALL_CONTROL_FAILED")
            local function deferred(key,cb) controls[#controls+1]=key; later=cb end
            _G.at_cmd_handlers.SIP_ACCEPT=deferred
            local before=#sent; command={op="accept"};runtime.command("accept");assert(#sent==before)
            later("ERROR: late accept failure");assert(sent[#sent]=="BUS_EVT=notice:CALL_CONTROL_FAILED")
            _G.at_cmd_handlers.SIP_HANGUP=deferred
            before=#sent;command={op="hangup"};runtime.command("hangup");assert(#sent==before)
            later("ERROR: late hangup failure");assert(sent[#sent]=="BUS_EVT=notice:CALL_CONTROL_FAILED")
            _G.at_cmd_handlers.SIP_HANGUP=function(key,cb) cb("OK") end
            before=#sent;command={op="hangup"};runtime.command("hangup");assert(#sent==before)
            _G.at_cmd_handlers.SIP_HANGUP=function() error("driver failure") end
            runtime.command("hangup");assert(sent[#sent]=="BUS_EVT=notice:CALL_CONTROL_FAILED")
            _G.at_cmd_handlers.SIP_HANGUP=nil;runtime.command("hangup")
            assert(sent[#sent]=="BUS_EVT=notice:CALL_CONTROL_FAILED")
            for _,v in ipairs(sent) do assert(not v:find("BUS_EVT=call:",1,true)) end
            assert(saved.alarm_active==true and saved.alarm_id==1)
        ''')

    def test_mqtt_crlf_cannot_inject_uart_business_or_ota_frame(self):
        self.lua.execute('''
            package.loaded.exgnss={rmc=function() return nil end}
            package.loaded.dfu_transfer={is_binary_mode=function() return false end}
            uart={setup=function() end,on=function() end}
            subs={}; publishes={}
            sys={taskInit=function() end,subscribe=function(name,fn) subs[name]=fn end,
                publish=function(...) publishes[#publishes+1]={...} end}
            log={info=function() end,warn=function() end,error=function() end}
            mobile={imei=function() return "123456789012345" end}
            require("uart_app")
            subs.RECV_DATA_FROM_SERVER("[MQTTS_EVT] ","untrusted/topic",
                "x\\r\\nBUS_EVT={\\\"op\\\":\\\"hello\\\",\\\"alarm_active\\\":false}\\r\\nOTA_CTL=ABORT")
        ''')
        self.assertEqual(self.value('#publishes'), 0)
        self.lua.execute('subs.RECV_DATA_FROM_SERVER("[MQTTS_EVT] ","/iotplat/render3/WARNCARD3/id/down_raw","unknown")')
        self.assertEqual(self.value('#publishes'), 0)

    # SAM | 2026-10-20 16:39 +08:00 | Execute the actual AT_INFO handler so supported APIs and unknown fallbacks are checked at the UART boundary.
    def test_at_info_uses_live_registration_and_shared_signal(self):
        self.lua.execute('''
            package.loaded.exgnss={rmc=function() return nil end}
            package.loaded.dfu_transfer={is_binary_mode=function() return false end}
            uart={setup=function() end,on=function() end}
            sys={taskInit=function() end,subscribe=function() end}
            log={info=function() end,warn=function() end,error=function() end}
            mobile={status=function() return 1 end}
            require("uart_app")
            function info()
                local lines={}
                _G.at_cmd_handlers.AT_INFO("AT_INFO",function(...)
                    local t={};for _,v in ipairs({...}) do t[#t+1]=tostring(v) end
                    lines[#lines+1]=table.concat(t)
                end)
                return table.concat(lines,"\\n")
            end
            local text=info()
            assert(text:find("Network: REG=1",1,true) and text:find("CSQ: 20",1,true))
            mobile.status=function() error("unavailable") end
            package.loaded.netdrv_device.csq=function() return 99 end
            text=info()
            assert(text:find("Network: UNKNOWN",1,true) and text:find("CSQ: 99",1,true))
        ''')

    def test_stale_puback_cannot_clear_new_phone_or_low_battery_event(self):
        self.lua.execute('''
            sent={}; port.publish=function(kind,msg,cb) sent[#sent+1]={msg=msg,cb=cb} end
            s=core.new(port); s:network("mqtt")
            s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="18812345678",CallInList={}})
            old_phone=sent[#sent].cb
            s:downlink({MsgType="phoneBindMsg",CmdType=0,CallOut="18812345679",CallInList={}})
            old_phone(true)
            assert(saved.phone_reply.seq==2)
            s:command({op="battery",known=true,battery=24})
            old_low=sent[#sent].cb
            s:command({op="battery",known=true,battery=30})
            s:command({op="battery",known=true,battery=23})
            old_low(true)
            assert(saved.low_battery_pending.level==23)
        ''')
        self.assertEqual(self.value('saved.phone_reply.seq'), 2)
        self.assertEqual(self.value('saved.low_battery_pending.level'), 23)

    def test_stale_alarm_and_online_callbacks_ignore_new_generation(self):
        self.lua.execute('''
            sent={}; port.publish=function(kind,msg,cb) sent[#sent+1]={msg=msg,cb=cb} end
            s=core.new(port)
            s:command({op="battery",known=true,battery=50})
            s:command({op="alarm",id=0}); s:network("mqtt")
            old_sos=sent[1].cb; old_online=sent[2].cb
            s:command({op="cancel",id=1})
            s:command({op="alarm",id=0})
            s:network("offline"); s:network("mqtt")
            old_sos(false); old_online(true)
            assert(saved.alarm_id==2)
            assert(events[#events].code~="SOS_PUBACK_FAILED")
            assert(#sent>=4)
        ''')
        self.assertEqual(self.value('saved.alarm_id'), 2)

    def test_unknown_whitelist_rejects_incoming_but_verified_empty_accepts(self):
        self.lua.execute('''
            controls={}; port.call_control=function(op) controls[#controls+1]=op; return true end
            s:incoming("123")
            assert(events[#events].op=="call" and events[#events].state=="incoming")
            store.load=function() return nil,"STORE_CORRUPT" end
            s=core.new(port)
            s:incoming("123")
        ''')
        self.assertEqual(self.value('controls[#controls]'), 'hangup')
        self.assertEqual(self.value('events[#events].code'), 'STORE_CORRUPT')


if __name__ == "__main__":
    unittest.main()
