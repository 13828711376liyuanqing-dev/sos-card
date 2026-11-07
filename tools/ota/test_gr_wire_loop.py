"""SAM | 2026-10-23 +08:00 | Actual CAT Lua sender and GR C receiver exchange wire bytes; host Flash/verify remain models."""
from pathlib import Path
import os,subprocess,sys
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua53 import LuaRuntime
out=R/'logs/ota_gr_wire_loop_20261023';out.mkdir(exist_ok=True)
g=Path('D:/Program Files/GUI Guider/environment/mingw/bin/gcc.exe')
env=dict(os.environ,PATH=str(g.parent)+os.pathsep+os.environ.get('PATH',''))
src=R/'ble_app_uart_c/Src/user/ota'
subprocess.run([str(g),'-std=c99','-Wall','-Wextra','-Werror','-I'+str(src),str(R/'tools/ota/test_gr_wire_peer.c'),str(src/'yp001_ota_receive.c'),str(src/'yp001_ota_wire.c'),'-o',str(out/'peer.exe')],env=env,check=True)
peer=subprocess.Popen([str(out/'peer.exe')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,text=True)
lua=LuaRuntime(encoding=None,unpack_returned_tuples=True)
lua.execute(b"package.path=.....'/Air780EGH/?.lua;'..package.path;w=require('ota_wire')",R.as_posix().encode())
clock=[0];dropped=[False];sent=[0]
def send(raw):
    sent[0]+=1
    f=lua.globals().w.decode(raw)
    peer.stdin.write(raw.hex()+'\n');peer.stdin.flush()
    reply=bytes.fromhex(peer.stdout.readline().strip())
    assert reply,'C peer rejected frame'
    if f[b'type']==4 and not dropped[0]:dropped[0]=True;return True
    decoded=lua.globals().w.decode(reply);assert decoded is not None
    s=lua.globals().sender
    assert s.on_frame(s,decoded)
    return True
lua.globals().py_send=send
lua.globals().py_now=lambda:clock[0]
try:
    lua.execute(b'''
      sender=require('ota_gr_transfer').new({send=function(raw)return py_send(raw)end,
        now=function()return py_now()end,idle=function()return true end,
        read=function(_,_,n)return string.rep('x',n)end})
      job={id=string.rep('a',64),hash=string.rep('b',64),size=5000,target='GR5526',version='1.5.0'}
      assert(sender:start(job,'/ota_test',7))
    ''')
    for _ in range(100):
        lua.execute(b'sender:step()');clock[0]+=500
        if lua.eval(b'sender:ready(job,7)'):break
    else:raise AssertionError('cross-language transfer never verified')
    assert dropped[0] and sent[0]==14,(dropped,sent)
    peer.stdin.close();assert peer.wait(timeout=5)==0,peer.stderr.read()
    print('PASS actual Lua/C wire loop: 5000 bytes, dropped DATA ACK, duplicate replay, sector durability, VERIFY; host models only')
finally:
    if peer.poll() is None:peer.kill();peer.wait()
