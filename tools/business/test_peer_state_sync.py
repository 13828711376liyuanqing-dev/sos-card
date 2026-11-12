"""SAM | 2026-10-25 +08:00 | Replay real SIM/IP callbacks through CAT business runtime; never access a device."""
from pathlib import Path
import os
import unittest

import test_sim_recovery


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get("YP001_CAT_SOURCE", str(ROOT / "Air780EGH")))


class PeerStateSyncTests(unittest.TestCase):
    def setUp(self):
        fixture = test_sim_recovery.SimRecoveryTests()
        fixture.setUp()
        self.lua = fixture.lua
        self.lua.execute(f'package.path="{SOURCE.as_posix()}/?.lua;"..package.path')
        self.lua.execute('''
            saves=0
            package.loaded.business_store={new=function() return {
                load=function() return {next_id=1,alarm_active=false,alarm_id=0,call_in={}} end,
                save=function() saves=saves+1;return true end} end,file_port=function() return {} end}
            package.loaded.mqtts_main={business_identity=function() return "TEST" end}
            json={encode=function(v) return v.op..":"..(v.state or v.code or "") end}
            ms=1000;mcu={ticks=function() return ms end}
            runtime=require("business_runtime")
            runtime.bind_sip_status(function() return {task_running=false,state="STATE_IDLE"} end)
            function mqtt_online()
                online();runtime.mqtt_ready()
                assert(runtime.ota_status().idle and runtime.ota_status().network=="mqtt")
            end
        ''')

    # SAM | 2026-11-07 +08:00 | Exercise the exact-topic normal router, which consumes bindings before legacy GR echo.
    def test_normal_phone_router_projects_committed_destination_once(self):
        self.lua.execute('''
            local projected={}
            json.encode=function(v)
                if v.op=="phone_bind" then projected[#projected+1]=v.call_out end
                return v.op or "reply"
            end
            _G.uart_send_raw=function()return true end
            local value={MsgType="phoneBindMsg",CmdType=0,CallOut="+8613800138000",CallInList={}}
            local raw='{"CallInList":[]}'
            assert(not runtime.downlink("wrong_topic",value,raw))
            assert(saves==0 and #projected==0)
            assert(runtime.downlink("/iotplat/render3/WARNCARD3/TEST/down_raw",value,raw))
            assert(saves==1 and #projected==1 and projected[1]==value.CallOut)
            assert(runtime.downlink("/iotplat/render3/WARNCARD3/TEST/down_raw",{MsgType="phoneBindMsg",CmdType=1},"{}"))
            assert(saves==2 and projected[2]=="")
        ''')

    def test_duplicate_ip_ready_preserves_live_mqtt_permission(self):
        self.lua.execute('''
            mqtt_online();local generation=observer.generation()
            for i=1,3 do
                sys.publish("IP_READY","192.0.2.1",socket.LWIP_GP)
                local s=runtime.ota_status()
                assert(s.network=="mqtt" and s.idle,
                    "duplicate IP_READY revoked a live MQTT OTA permission: "..s.network)
            end
            assert(observer.generation()==generation and saves==0)
        ''')

    def test_ip_loss_revokes_and_ip_alone_cannot_restore_permission(self):
        self.lua.execute('''
            mqtt_online();sys.publish("IP_LOSE",socket.LWIP_GP)
            assert(not runtime.ota_status().idle and runtime.ota_status().network=="offline")
            sys.publish("IP_READY","192.0.2.2",socket.LWIP_GP)
            assert(not runtime.ota_status().idle and runtime.ota_status().network=="ip")
            runtime.mqtt_ready();assert(runtime.ota_status().idle)
            assert(saves==0)
        ''')

    def test_mqtt_loss_is_not_hidden_by_duplicate_ip_ready(self):
        self.lua.execute('''
            mqtt_online();runtime.mqtt_lost()
            assert(not runtime.ota_status().idle)
            sys.publish("IP_READY","192.0.2.1",socket.LWIP_GP)
            assert(runtime.ota_status().network=="ip" and not runtime.ota_status().idle)
            runtime.mqtt_ready();assert(runtime.ota_status().idle)
        ''')

    def test_sim_loss_rejects_late_ip_and_mqtt_callbacks(self):
        for state in ("NORDY", "SIM_PIN"):
            with self.subTest(state=state):
                self.setUp()
                self.lua.execute(f'''
                    mqtt_online();sys.publish("SIM_IND","{state}")
                    assert(runtime.ota_status().network=="no_sim" and not runtime.ota_status().idle)
                    sys.publish("IP_READY","192.0.2.1",socket.LWIP_GP);runtime.mqtt_ready()
                    assert(runtime.ota_status().network=="no_sim" and not runtime.ota_status().idle)
                    sys.publish("SIM_IND","RDY");sys.publish("IP_READY","192.0.2.2",socket.LWIP_GP)
                    assert(runtime.ota_status().network=="ip" and not runtime.ota_status().idle)
                    runtime.mqtt_ready();assert(runtime.ota_status().idle and saves==0)
                ''')

    def test_unrelated_adapter_cannot_revoke_live_mqtt(self):
        self.lua.execute('''
            mqtt_online();sys.publish("IP_READY","198.51.100.1",99);sys.publish("IP_LOSE",99)
            assert(runtime.ota_status().network=="mqtt" and runtime.ota_status().idle)
        ''')


if __name__ == "__main__":
    unittest.main()
