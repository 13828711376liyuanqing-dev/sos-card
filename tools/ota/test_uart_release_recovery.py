"""SAM | 2026-10-26 +08:00 | Real CAT writer/sender with a phase-gated peer; bounded release and DATA-ACK loss, no device access."""
from test_uart_flash_window import runtime


def check(drop_release=0, drop_data=0, lose_every_release=False):
    l = runtime()
    l.globals().drop_release = drop_release
    l.globals().drop_data = drop_data
    l.globals().lose_every_release = lose_every_release
    l.execute('''
local sender
local publish=sys.publish
sys.publish=function(e,f)
 publish(e,f)
 if e=='OTA2_TX_SENT' then sender:on_tx_sent(f)
 elseif e=='OTA2_FRAME' then sender:on_frame(f)
 elseif e=='OTA2_TX_FAILED' then sender:on_tx_failed(f)end
end
sender=require('ota_gr_transfer').new({track_tx=true,now=function()return clock end,
 idle=function()return idle end,owns=ota_uart_owned,read=function(_,_,n)return string.rep('x',n)end,
 send=ota_uart_send,cancel=ota_uart_cancel})
assert(sender:start({id=string.rep('a',64),hash=string.rep('b',64),size=5000,version='1.5.0',target='GR5526'},'/candidate',2))
local peer_phase,token,peer_at,request,accepted=0,0,0,nil,0
local writes,ack_index,operations,retries,max_sends=0,0,0,0,0
local parser=w.parser(function(f)
 if f.type==241 and peer_phase==1 then
  assert(f.offset==0);peer_phase=3;peer_at=clock;operations=operations+1
  if request.type==1 then
   feed(w.encode(2,request.session,request.sequence,request.offset,string.pack('<I2I2I4I4I4',512,4096,442368,0,1)))
  else
   if request.type==4 then accepted=math.max(accepted,request.offset+#request.payload)end
   if request.type~=4 or drop_data==0 then
    feed(w.encode(128,request.session,request.sequence,request.offset,
      string.pack('<BBI2I4I4I4',request.type,0,1,accepted,math.floor(accepted/4096)*4096,5000)))
   else drop_data=drop_data-1 end
  end
  feed(quiet(242,token))
 elseif f.type==243 then
  ack_index=ack_index+1
  if not lose_every_release and ack_index~=drop_release and f.sequence==token and peer_phase==3 then peer_phase=0 end
 elseif f.type<240 then
  -- Mirrors the real GR dispatcher: an outstanding release prevents the next operation.
  if peer_phase~=0 then return end
  request=f;token=token+1;peer_phase=1;feed(quiet(240,token))
 end
end)
for tick=1,2500 do
 clock=tick*10
 if peer_phase==3 and clock-peer_at>2000 and retries<3 then
  retries=retries+1;feed(quiet(242,token))
 end
 sender:step();pump()
 for burst=1,20 do
  if writes>=#written then break end
  writes=writes+1;parser:feed(written[writes]);sent()
 end
 local s=sender:status();max_sends=math.max(max_sends,s.attempts)
 if s.phase=='FAILED' or s.offset>=512 then break end
end
result_phase=sender:status().phase;result_reason=sender:status().reason
result_offset=sender:status().offset;result_max_sends=max_sends
result_faulted=ota_uart_faulted();result_operations=operations
''')
    g = l.globals()
    return {k: g['result_' + k] for k in ('phase', 'reason', 'offset', 'max_sends', 'faulted', 'operations')}


def test_release_loss():
    for which in (1, 2):
        s = check(drop_release=which)
        assert s['offset'] >= 512 and not s['faulted'], (which, s)


def test_data_ack_loss():
    s = check(drop_data=1)
    assert s['offset'] >= 512 and not s['faulted'], s
    s = check(drop_data=999)
    assert s['phase'] == 'FAILED' and s['reason'] == 'GR_UART_TIMEOUT', s
    assert s['max_sends'] == 3, s


def test_combined_loss():
    s = check(drop_release=1, drop_data=1)
    assert s['offset'] >= 512 and not s['faulted'], s
    s = check(lose_every_release=True)
    assert s['phase'] == 'FAILED' or s['faulted'], s
    assert s['max_sends'] <= 3, s


if __name__ == '__main__':
    test_release_loss()
    test_data_ack_loss()
    test_combined_loss()
    print('PASS release ACK loss, DATA ACK loss and bounded coupled recovery')
