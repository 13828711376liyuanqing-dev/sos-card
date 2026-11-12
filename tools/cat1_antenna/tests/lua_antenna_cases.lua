-- SAM | 2026-10-10 16:51 +08:00 | Verify lifecycle with API stubs because host evidence is distinct from RF acceptance.
out={}; now=0; active={}; opens=0; closes=0
sys.timerLoopStart=function(f,ms) sample=f; return 1 end
sys.timerStop=function() sample=nil end
mcu={ticks2=function() return 0,now end}
ex={DEFAULT=1,setup=function() end,
 open=function(_,p) active[p.tag]=true; opens=opens+1 end,
 close=function(_,p) active[p.tag]=nil; closes=closes+1 end,
 is_active=function(_,p) return active[p.tag] end,
 is_fix=function() return false end,rmc=function() return {lat=23,lng=113} end}
package.loaded.exgnss=ex
_G.uart_send_raw=function(s) table.insert(out,s); return true end
function command(s) local k=s:match('^[^=]+'); at_cmd_handlers[k](s) end
require('antenna_test')
command('AT+ANTSTART=ALL,2')
assert(out[#out]:find('type=ACK op=START ok=1 mode=ALL interval=2',1,true))
now=2000; sample()
assert(out[#out]:find('fix=0',1,true) and out[#out]:find('lat=NA',1,true))
command('AT+ANTSTART=ALL,2'); assert(opens==1)
command('AT+ANTSTOP'); assert(closes==1 and sample==nil)
command('AT+ANTSTOP'); assert(closes==1)
command('AT+ANTSTART=LTE,0'); assert(out[#out]:find('ok=0',1,true))
_G.dfu_transfer_active=true
command('AT+ANTSTART=LTE,2'); assert(out[#out]:find('error=DFU_BUSY',1,true))
_G.dfu_transfer_active=false
command('AT+ANTSTART=GNSS,1'); _G.dfu_transfer_active=true; sample()
assert(not active.antenna_test and sample==nil)
print('PASS antenna lifecycle, invalid input, missing metrics, no fix, DFU')
_G.dfu_transfer_active=false
mobile={csq=function() return 99 end,status=function() return 5 end,
 rsrp=function() return 0 end,rsrq=function() error('unavailable') end}
command('AT+ANTSTART=LTE,1'); sample()
assert(out[#out]:find('csq=99 reg=5 rsrp=NA rsrq=NA',1,true))
command('AT+ANTSTOP')
local oldopen=ex.open
ex.open=function() error('hardware unavailable') end
command('AT+ANTSTART=GNSS,1'); assert(out[#out]:find('error=GNSS_OPEN',1,true) and sample==nil)
ex.open=oldopen
command('AT+ANTSTART=GNSS,1'); now=2050; events.GNSS_STATE('FIXED')
ex.is_fix=function() return true end
now=3000; sample()
assert(out[#out]:find('lat=23 lon=113',1,true) and out[#out]:find('ttff_ms=50',1,true))
command('AT+ANTSTOP')
local oldactive=ex.is_active; ex.is_active=nil
command('AT+ANTSTART=GNSS,1'); assert(out[#out]:find('error=GNSS_UNAVAILABLE',1,true))
ex.is_active=oldactive
local oldtimer=sys.timerLoopStart; sys.timerLoopStart=function() return nil end
command('AT+ANTSTART=ALL,2'); assert(out[#out]:find('error=TIMER_FAILED',1,true) and not active.antenna_test)
sys.timerLoopStart=oldtimer
command('AT+ANTSTATUS'); assert(out[#out]:find('running=0',1,true))
print('PASS CSQ99, API exception, TTFF event, missing GNSS API, timer failure')
-- SAM | 2026-10-10 16:58 +08:00 | Model official ticks2 split because low milliseconds wrap every 1000 seconds.
mcu.ticks2=function(mode) assert(mode==1); return math.floor(now/1000000), now%1000000 end
now=999900; ex.is_fix=function() return false end
command('AT+ANTSTART=GNSS,1'); now=1000100; sample()
assert(out[#out]:find('elapsed_ms=200 ',1,true), 'ticks2 split boundary elapsed incorrect')
command('AT+ANTSTOP')
print('PASS official ticks2 million-millisecond split boundary')
