"""SAM | 2026-10-26 +08:00 | Transfer every byte of the actual R6-size component through real CAT writer/sender; peer Flash/signature are simulated, never device acceptance."""
from test_uart_flash_window import runtime

def check():
    lua=runtime()
    lua.execute('''
local sender;local publish=sys.publish
sys.publish=function(e,f)
 publish(e,f)
 if e=='OTA2_TX_SENT' then sender:on_tx_sent(f)
 elseif e=='OTA2_FRAME' then sender:on_frame(f)
 elseif e=='OTA2_TX_FAILED' then sender:on_tx_failed(f) end
end
local size=432328
sender=require('ota_gr_transfer').new({track_tx=true,now=function()return clock end,idle=function()return idle end,
 owns=ota_uart_owned,read=function(_,at,n)assert(at>=0 and at+n<=size);return string.rep('x',n)end,
 send=ota_uart_send,cancel=ota_uart_cancel})
assert(sender:start({id=string.rep('a',64),hash=string.rep('b',64),size=size,version='1.5.0',target='GR5526'},'/candidate',4))
local phase,token,request,accepted,durable=0,0,nil,0,0
local seen,data_count,verified,late_release=0,0,false,false
local parser=w.parser(function(f)
 if f.type<240 then
  assert(phase==0,'NEW_OPERATION_BEFORE_RELEASE');request=f;token=token+1;phase=1;feed(quiet(240,token))
 elseif f.type==241 then
  assert(phase==1 and f.sequence==token and f.offset==0);phase=3
  if request.type==1 then
   feed(w.encode(2,4,request.sequence,0,string.pack('<I2I2I4I4I4',512,4096,442368,0,1)))
  else
   if request.type==4 then
    assert(request.offset==accepted,'DATA_SKIP_OR_DUPLICATE');accepted=accepted+#request.payload;data_count=data_count+1
    durable=accepted==size and size or math.floor(accepted/4096)*4096
   elseif request.type==6 then assert(accepted==size and durable==size);verified=true end
   feed(w.encode(128,4,request.sequence,request.offset,string.pack('<BBI2I4I4I4',request.type,0,verified and 3 or 1,accepted,durable,size)))
  end
  if request.type==4 and request.offset==274432 and not late_release then
   late_release=true;clock=clock+2999;feed(quiet(242,token));clock=clock+2
  else feed(quiet(242,token)) end
 elseif f.type==243 then assert(f.sequence==token);phase=0 end
end)
for tick=1,30000 do
 clock=clock+10;sender:step();pump()
 for burst=1,12 do
  if seen>=#written then break end
  seen=seen+1;parser:feed(written[seen]);sent()
 end
 local s=sender:status()
 assert(s.phase~='FAILED',s.reason);assert(not ota_uart_faulted(),'FULL_TRANSFER_UART_FAULT')
 if s.phase=='VERIFIED' and phase==0 then break end
end
local final=sender:status()
assert(accepted==size and durable==size and final.phase=='VERIFIED' and verified and late_release)
assert(data_count==math.ceil(size/512));result={bytes=accepted,blocks=data_count,phase=final.phase,late_release_at=274432}
''')
    v=lua.globals().result
    print('PASS real CAT writer/sender full component',v['bytes'],'bytes',v['blocks'],'blocks; peer Flash/signature simulated; deadline race at',v['late_release_at'])

if __name__=='__main__':check()
