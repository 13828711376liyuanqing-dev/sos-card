"""SAM | 2026-10-27 +08:00 | Couple production CAT Lua writer and production GR C coordinator/mux; inject an explicit wire loss only, never access a device."""
from pathlib import Path
import ctypes,subprocess,os,json,sys,hashlib
from test_uart_flash_window import runtime

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'logs/r6_dual_quiet_20261027'
GCC=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')

class Bridge:
    def __init__(self,exe,env):
        self.proc=subprocess.Popen([str(exe)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    def call(self,line):
        self.proc.stdin.write(line+'\n');self.proc.stdin.flush();value=self.proc.stdout.readline()
        if not value:raise RuntimeError('GR bridge stopped: '+self.proc.stderr.read())
        return value.rstrip('\r\n')
    def BR_reset(self):assert self.call('reset')=='ok'
    def BR_time(self,t):assert self.call('time '+str(t))=='ok'
    def BR_operation_ms(self,t):assert self.call('operation '+str(t))=='ok'
    def BR_alarm(self,t):assert self.call('alarm '+str(t))=='ok'
    def BR_poll(self):assert self.call('poll')=='ok'
    def BR_pending(self):assert self.call('pending')=='ok'
    def BR_nested(self,t):assert self.call('nested '+str(t))=='ok'
    def state(self):return json.loads(self.call('state'))
    def trace(self):return json.loads(self.call('trace'))
    def BR_now(self):return self.state()['now']
    def BR_phase(self):return self.state()['phase']
    def BR_token(self):return self.state()['token']
    def BR_operations(self):return self.state()['operations']
    def BR_feed(self,buf,n):assert self.call('feed '+ctypes.string_at(buf,n).hex())=='ok'
    def BR_pop(self,buf,cap):
        data=bytes.fromhex(self.call('pop'));assert len(data)<=cap
        ctypes.memmove(buf,data,len(data));return len(data)
    def close(self):
        self.proc.stdin.close();self.proc.wait(timeout=5)

def build():
    OUT.mkdir(exist_ok=True)
    command=[str(GCC),'-std=c99','-Wall','-Wextra','-Werror','-DREPLAY_STANDALONE',
        '-Ible_app_uart_c/Src/user/ota','-Ible_app_uart_c/Src/external/cJSON-1.7.19',
        'tools/ota/gr_quiet_replay_bridge.c','ble_app_uart_c/Src/user/ota/yp001_ota_wire.c',
        'ble_app_uart_c/Src/external/cJSON-1.7.19/cJSON.c','-o',str(OUT/'gr_quiet_bridge.exe')]
    env=dict(os.environ,PATH=str(GCC.parent)+os.pathsep+os.environ.get('PATH',''))
    p=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=60)
    (OUT/'bridge_build.log').write_text(p.stdout+p.stderr,encoding='utf-8');assert p.returncode==0,p.stderr
    return Bridge(OUT/'gr_quiet_bridge.exe',env)

def scenario(gr,delay=1200,drop_first_release=True,operation_ms=15,alarm=False,poll_delay_ms=0,pending_service=False,nested_test=False):
    gr.BR_reset();gr.BR_operation_ms(operation_ms)
    gr.BR_nested(1 if nested_test else 0)
    l=runtime();l.execute("function replay_written(i)return (written[i]:gsub('.',function(c)return string.format('%02x',c:byte())end))end")
    timeline=[];seen=0
    def stamp(at):
        l.globals().clock=at&0xffffffff;gr.BR_time(at&0xffffffff)
    def to_gr(at):
        nonlocal seen
        while seen<len(l.globals().written):
            seen+=1;raw=bytes.fromhex(l.globals().replay_written(seen));buf=ctypes.create_string_buffer(raw)
            for offset in range(0,len(raw),44 if raw[5]>=240 else len(raw)):
                part=raw[offset:offset+44] if raw[5]>=240 else raw
                timeline.append({'ms':at,'direction':'CAT_TO_GR','type':part[5]})
            gr.BR_feed(buf,len(raw))
    def from_gr(at,drop=False):
        buf=ctypes.create_string_buffer(1100)
        while True:
            n=gr.BR_pop(buf,len(buf))
            if not n:break
            raw=buf.raw[:n];kind=raw[5] if raw[:4]==b'OTA2' else None
            timeline.append({'ms':at,'direction':'GR_TO_CAT','type':kind,'dropped':drop and kind==242})
            if not(drop and kind==242):l.execute('feed(...)',raw)
    stamp(0);l.execute('assert(ota_uart_send(frame));pump();sent()');to_gr(0);from_gr(0)
    stamp(delay);l.execute('pump()');to_gr(delay);l.execute('sent()')
    if alarm:gr.BR_alarm(1)
    if poll_delay_ms and not pending_service:
        stamp(delay+poll_delay_ms);l.execute('pump()')
    if pending_service:gr.BR_pending()
    else:gr.BR_poll()
    end=int(gr.BR_now());stamp(end);from_gr(end,drop_first_release)
    retry=end+2001
    stamp(retry-1);l.execute('pump()')
    before_retry=bool(l.globals().ota_uart_faulted())
    stamp(retry)
    if pending_service:gr.BR_pending()
    else:gr.BR_poll()
    from_gr(retry);l.execute('pump()');to_gr(retry);l.execute('sent()')
    faults=[]
    for i in range(1,len(l.globals().events)+1):
        event=l.globals().events[i]
        if event[1]=='OTA_UART_FAULT':faults.append(event[2])
    return {'grant_delay_ms':delay,'operation_ms':operation_ms,'gr_foreground_poll_delay_ms':poll_delay_ms,'pending_service':pending_service,'drop_first_release':drop_first_release,'alarm':alarm,
        'gr_operation_count':int(gr.BR_operations()),'gr_final_quiet_phase':int(gr.BR_phase()),
        'cat_faulted_before_gr_retry':before_retry,'cat_faulted_final':bool(l.globals().ota_uart_faulted()),
        'cat_fault_events':faults,'gr_reset_polls':gr.state()['reset_polls'],'gr_nested_attempts':gr.state()['nested_attempts'],'trace':gr.trace(),'timeline':timeline}

if __name__=='__main__':
    gr=build()
    try:r=scenario(gr)
    finally:gr.close()
    (OUT/'dual_source_reproduction.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))
    print('SCOPE: exact software protocol reproduction with one modeled RELEASE loss; not proof of the missing hardware failure waveform')
