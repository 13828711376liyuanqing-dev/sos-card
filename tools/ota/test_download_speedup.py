"""SAM | 2026-11-04 +08:00 | OTA download speed-up (device-only download_tuning): 16 KiB chunks, several steps per tick
within the burst budget, business-busy stops the burst, per-chunk checkpoints stay within the manager's 16 KiB gap,
no tuning keeps one 4 KiB step per tick; beacon progress text. Host fixtures only, not board evidence."""
from test_runtime import check
from test_default_native_path import SETUP

SIZE = 100000
head = SETUP[:SETUP.index('local r=make()')]
assert head.count('5000') == 4 and 'native_fota_port=np}' in head
head = head.replace('5000', str(SIZE))
# Each HTTP request takes 600 ms of device time; record request sizes and durable checkpoints.
head = head.replace("http_get=function(url,h)local a,b=h.Range:match('bytes=(%d+)%-(%d+)');a=tonumber(a);b=tonumber(b)",
    "http_get=function(url,h)local a,b=h.Range:match('bytes=(%d+)%-(%d+)');a=tonumber(a);b=tonumber(b)\n"
    "   clock=clock+600;gets[#gets+1]=b-a+1;if busy_after and #gets>=busy_after then idle=false end")


def script(tuning, body, io_limit=16384):
    # io_limit mirrors the real candidate port's per-call limit (ota_candidates.lua); None = undeclared (4 KiB).
    setup = head.replace('native_fota_port=np}', 'native_fota_port=np,download_tuning=%s}' % tuning)
    setup = setup.replace('local np=', 'dp.io_limit=%s\nlocal np=' % ('nil' if io_limit is None else io_limit), 1)
    return 'gets={};busy_after=nil\n' + setup + '''
local r=make();assert(r:accept(command));local j=r:status().job
local function frame(op,phase,safe)
 return 'OTA_GR='..json.encode({op=op,phase=phase,reason='ok',commit_safe=safe,
  job=j.id,hash=j.hash,target=j.target,version=j.version,epoch=1})
end
assert(r:on_gr_line(frame('GRANT','DOWNLOADING',false)))
local function step_tick()local n=#gets;r:tick();return #gets-n end
''' + body


if __name__ == '__main__':
    check('tuned: 16 KiB chunks, burst stops at the 3 s budget, per-chunk checkpoints, then PREPARED', script(
        '{chunk_size=16384,burst_ms=3000}', '''
assert(r:tick()==false or true)
local first=#gets
-- 600 ms per request: steps at t0+600..3000 -> the 5th request ends the burst.
assert(first==5,'burst '..first)
for i=1,first do assert(gets[i]==16384) end
assert(r:status().progress.committed==5*16384,'checkpoint '..tostring(r:status().progress.committed))
assert(r:transfer_progress()=='D'..(5*16384)..'/'..%d)
local ticks=1
while r:status().phase~='PREPARED' and ticks<10 do step_tick();ticks=ticks+1 end
assert(r:status().phase=='PREPARED' and ticks==2,'ticks '..ticks..' '..tostring(r:status().phase))
assert(#gets==7 and gets[7]==%d-6*16384)
''' % (SIZE, SIZE)))

    check('tuned: business busy mid-burst stops after the current chunk and the next tick waits', script(
        '{chunk_size=16384,burst_ms=3000}', '''
busy_after=2
r:tick()
assert(#gets==2,'gets '..#gets)
assert(r:status().progress.committed==2*16384)
assert(step_tick()==0 and r:status().phase=='PAUSED')
idle=true;busy_after=nil
assert(step_tick()>0)
'''))

    # SAM | 2026-11-04 +08:00 | Board 11:50: the real candidate file port refused 16 KiB writes (4 KiB limit) ->
    # write_readback_failed spent the trial ticket. Exercise the real ota_candidates port; only the file system is faked.
    check('tuned with the REAL candidate file port: 16 KiB chunks stored via 4 KiB file calls, read back intact', script(
        '{chunk_size=16384,burst_ms=3000}', '''
''').replace('local r=make()', '''
fsfiles,fswrites,fsreads={},{},{}
local fakeio={exists=function(p)return fsfiles[p]~=nil end,
 open=function(p,mode)
  if mode=='wb' then fsfiles[p]='' elseif fsfiles[p]==nil then return nil end
  local pos=0
  return {seek=function(_,how,n)if how=='end' then pos=#fsfiles[p] else pos=n end;return pos end,
   read=function(_,n)fsreads[#fsreads+1]=n;local s=fsfiles[p]:sub(pos+1,pos+n);pos=pos+#s;return s end,
   write=function(_,s)fswrites[#fswrites+1]=#s;local d=fsfiles[p];fsfiles[p]=d:sub(1,pos)..s..d:sub(pos+#s+1);pos=pos+#s;return true end,
   close=function()return true end}
 end}
local real=require('ota_candidates').new({},fakeio)
local ldp={}
for k,v in pairs(real) do ldp[k]=v end
ldp.http_get=dp.http_get;ldp.checkpoint=dp.checkpoint
dp=ldp
local r=make()''', 1) + '''
local path=require('ota_candidates').path(j.hash);fsfiles[path]=''
r:tick()
assert(#gets==5,'gets '..#gets)
for i=1,5 do assert(gets[i]==16384,'chunk '..gets[i]) end
assert(#fsfiles[path]==5*16384,'stored '..#fsfiles[path])
for _,n in ipairs(fswrites) do assert(n<=4096,'fs write '..n) end
for _,n in ipairs(fsreads) do assert(n<=4096,'fs read '..n) end
assert(r:status().progress.committed==5*16384)
assert(r:transfer_progress()=='D'..(5*16384)..'/%d')
''' % SIZE)

    check('a tuning chunk above the file port limit is clamped to it', script(
        '{chunk_size=65536,burst_ms=3000}', '''
r:tick();assert(gets[1]==4096,'port without io_limit -> 4 KiB, got '..gets[1])
''', io_limit=None))

    check('untuned: one 4 KiB step per tick as before', script('nil', '''
r:tick();assert(#gets==1 and gets[1]==4096)
r:tick();assert(#gets==2 and gets[2]==4096)
assert(r:status().progress.committed==8192)
'''))

    check('tuned: burst budget needs a working clock (no clock -> one step per tick)', script(
        '{chunk_size=16384,burst_ms=3000}', '''
mcu=nil
r:tick();assert(#gets==1 and gets[1]==16384,'gets '..#gets)
r:tick();assert(#gets==2)
'''))
