# SAM | 2026-10-11 03:20 +08:00 | Test the current CAT1 entry with host stubs because board networking cannot be exercised by Python.
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "logs/cat1_antenna_20261010/python_deps"))
from lupa.lua54 import LuaRuntime


def runtime(prelude):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(prelude)
    return lua


def source(lua, name):
    lua.execute((ROOT / "Air780EGH" / name).read_text(encoding="utf-8-sig"))


def check_sim_recovery():
    lua = runtime('''
        events={}; tasks={}; lines={}; auto_args=nil; sent={}
        log={info=function()end,warn=function()end,error=function()end}
        sys={subscribe=function(k,f)events[k]=f end,
             taskInit=function(f)table.insert(tasks,coroutine.create(f)) end,
             wait=function()coroutine.yield()end,
             publish=function(...)table.insert(sent,{...})end}
        socket={LWIP_GP=1,localIP=function()return '10.0.0.2'end}
        mobile={imsi=function()return '123456'end,status=function()return 1 end,
                setAuto=function(...)auto_args={...}end}
        _G.uart_send_raw=function(...)table.insert(lines,table.concat({...},' '));return true end
        package.preload.netdrv_4g=function()return {}end
    ''')
    source(lua, "netdrv_device.lua")
    lua.execute('''
        assert(#tasks>0, 'startup SIM check missing')
        assert(coroutine.resume(tasks[1]))
        assert(auto_args and auto_args[1]==10000, 'SIM recovery not configured')
        events.SIM_IND('NORDY')
        assert(table.concat(lines,'|'):find('NORDY'), 'SIM removal not reported')
        assert(sent[#sent][1]=='SIM_LOST', 'SIM loss not sent to services')
        assert(not lines[#lines]:find('REG=1'), 'stale registration reported after SIM removal')
        events.SIM_IND('RDY')
        assert(table.concat(lines,'|'):find('SIM_ENV%] RDY'), 'SIM ready not reported')
        events.IP_READY('10.0.0.2',socket.LWIP_GP)
        assert(lines[#lines]:find('IP_READY=10.0.0.2'), 'IP not reported')
        events.IP_LOSE(socket.LWIP_GP)
        assert(lines[#lines]:find('IP_LOSE'), 'IP loss not reported')
    ''')
    print("PASS SIM startup, recovery configuration, removal/return, IP transitions")


# SAM | 2026-10-12 +08:00 | Legacy automatic-FOTA acceptance is replaced by rejection gates.
def check_fota():
    lua = runtime("""
        at_cmd_handlers={}; events={}; lines={}; starts=0
        log={warn=function()end}
        sys={subscribe=function(k,f)events[k]=f end}
        package.preload.libfota2=function() error('native FOTA must not load') end
        package.preload.ota_runtime=function() return {
            start=function() starts=starts+1; return {status=function()return {phase='IDLE'}end} end
        } end
        function respond(s) lines[#lines+1]=s end
    """)
    source(lua, 'update.lua')
    lua.execute("""
        assert(starts==1)
        at_cmd_handlers.FOTA_CHECK('FOTA_CHECK',respond)
        assert(lines[#lines]:find('REJECTED'))
        events.CAT1_FOTA_REQ()
        at_cmd_handlers.FOTA_STATUS('FOTA_STATUS',respond)
        assert(lines[#lines]=='IDLE')
    """)
    print('PASS FOTA boot and manual entries cannot auto-install or reboot')


def check_dfu_fota_interlock():
    lua = runtime("""
        at_cmd_handlers={}; lines={}; tasks={}
        log={info=function()end,warn=function()end,error=function()end}
        sys={taskInit=function(f)tasks[#tasks+1]=f end}
        os={remove=function()error('legacy erase forbidden')end}
        function respond(s)lines[#lines+1]=s end
    """)
    source(lua, 'dfu_transfer.lua')
    lua.execute("""
        for _,busy in ipairs({false,true}) do
            _G.cat1_fota_active=busy
            for _,name in ipairs({'DFU_DL','DFU_START','DFU_ERASE','DFU_ABORT'}) do
                at_cmd_handlers[name](name..'=http://example.invalid/fw',respond)
                assert(lines[#lines]:find('REJECTED'))
            end
        end
        assert(#tasks==0)
    """)
    print('PASS legacy DFU mutation rejects both idle and concurrent cases')


def check_sim_loss_retires_services():
    mqtt = runtime('''
        events={}; messages={}; at_cmd_handlers={}
        log={info=function()end,warn=function()end,error=function()end}
        sys={subscribe=function(k,f)events[k]=f end,
             taskInit=function()end,taskInitEx=function()end,
             sendMsg=function(...)table.insert(messages,{...})end}
        mobile={imei=function()return '123456789012345'end}
        package.preload.mqtts_receiver=function()return {proc=function()end}end
        package.preload.mqtts_sender=function()return {TASK_NAME_PREFIX='mqtts_',TASK_NAME='mqtts_sender',is_ready=function()return true end}end
        _G.uart_send_raw=function()end
    ''')
    source(mqtt, "mqtts_main.lua")
    mqtt.execute('''
        assert(events.SIM_LOST, 'MQTT lacks SIM loss handler')
        events.SIM_LOST()
        assert(messages[#messages][2]=='MQTT_EVENT' and messages[#messages][3]=='CLOSE')
    ''')
    sip = runtime('''
        events={}; messages={}; at_cmd_handlers={}
        log={info=function()end,warn=function()end,error=function()end}
        sys={subscribe=function(k,f)events[k]=f end,
             taskInitEx=function()end,sendMsg=function(...)table.insert(messages,{...})end}
        package.preload.exsip=function()return {TRANSPORT_UDP='udp'}end
        package.preload.audio_drv=function()return {}end
        package.preload.tts=function()return {init=function()end,play=function()end}end
        package.preload.exaudio=function()return {}end
    ''')
    source(sip, "sip.lua")
    sip.execute('''
        assert(events.SIM_LOST, 'SIP lacks SIM loss handler')
        at_cmd_handlers.SIP_INIT('SIP_INIT',function()end)
        events.SIM_LOST()
        assert(messages[#messages][3]=='MSG_ERROR', 'SIP active session not retired')
    ''')
    print("PASS SIM loss retires MQTT and SIP sessions")


if __name__ == "__main__":
    check_sim_recovery()
    check_fota()
    check_dfu_fota_interlock()
    check_sim_loss_retires_services()
