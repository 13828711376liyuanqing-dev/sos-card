"""SAM | 2026-10-29 20:11 +08:00 | Round-2 (1.5.1->1.5.2) whole-bundle host flow on the CAT1 receiver, device-mode runtime.
Start = a device-like post-round-1 store (IDLE, 1.5.1 release complete, 1.5.1 trial RUNNING, all R4/R6/t151 records as history).
Flow: accept -> GR grant mints the 1.5.2 ticket -> GR staged/PREPARED -> ACTIVATE -> DENY boot_commit_failed (GR 1.5.1 defect 1) -> one
automatic re-ACTIVATE -> GR result success -> RELEASED -> cleanup -> CAT1 component accepted/granted -> CAT proof (4 ACKed chunks) ->
PREPARED -> ACTIVATE -> GRANT INSTALL_PENDING without commit_safe (defect 2) -> install-only path (rebuild + baseline + receipt, all before
authority) -> commit-safe STATUS -> REAL ota_native_fota start (fota.init 5 s) -> 62 chunks -> commit (rehash 11 s + scan 5 s) -> REBOOT
request -> REBOOT_GRANT -> rtos.reboot. Timings are the board measurements; GR is simulated (replies only), vendor FOTA/bundle/download are stubs.
--old <dir>: the same steps on an older receiver reproduce the round-1 stops (no re-ACTIVATE; CAT1 GRANT -> ACTIVATION_RECHECK_FAILED).
Proves control flow and timing only, not the device.
Usage: python test_ota152_flow.py <receiver source dir> [--old <old receiver source dir>]"""
import sys
from pathlib import Path
from test_cat_manager import runtime

SETUP = r'''
package.path=src..'/?.lua;'..package.path
for k in pairs(package.loaded) do if k:match('^ota_') then package.loaded[k]=nil end end
OTA_TRIAL_MD5=string.rep('9',32);OTA_TRIAL_SOURCE='1.5.1';OTA_TRIAL_TARGET='1.5.2';PRODUCT_VERSION='1.5.1'
OTA_T151_MD5=OTA_TRIAL_MD5 -- old receivers only
log={info=function()end,warn=function()end,error=function()end}
_G.ota_uart_faulted=function()return false end;_G.ota_uart_owned=function()return false end;_G.dfu_transfer_active=false
_G.uart_send_raw=function()return true end
ticks=1000;mcu={ticks=function()ticks=ticks+10;return ticks end}
reboots=0;rtos={reboot=function()reboots=reboots+1 end}
diag={};_G.ota_diag=function(x)diag[#diag+1]=x end
MAN=string.rep('3',64)
GRJ={id=string.rep('1',64),hash=string.rep('2',64),target='GR5526',size=440000,md5=string.rep('4',32)}
CATJ={id=string.rep('7',64),hash=string.rep('8',64),target='CAT1',size=250531,md5=string.rep('6',32)}
comp='GR5526';clk=100000
port.now=function()return clk end
port.resolve=function(c)local j=clone(comp=='GR5526' and GRJ or CATJ);j.source=c.CurrentVersion;j.version=c.TargetVersion;j.url=c.Address
 j.bundle={md5=c.Md5:lower(),manifest_sha256=MAN};return j end
package.loaded.ota_platform={default=function()return port end,bundle=function(bp,b)return b end}
fake_bundle={component=function(_,t)local j=r:status().job;return {sha256=j.hash,md5=j.md5,size=j.size}end,
 summary=function()return {manifest_sha256=MAN,etag='e',device_installable=true}end,
 component_port=function()return {} end,close=function()end,cat_proof=function()return string.rep('a',1808)end}
package.loaded.ota_bundle={open=function(bp)fake_bundle.preflight_step=function()if bp.owns_bundle(MAN)~=true then return false,'GR_BUNDLE_OWNERSHIP_REQUIRED' end;return true,'VERIFIED' end;return fake_bundle end}
package.loaded.ota_download={new=function()return {start=function()return true end,step=function()return true end,verify=function()return true end,
 status=function()local j=r:status().job;return {state='DOWNLOADED',offset=j.size,path=require('ota_candidates').path(j.hash)}end}end}
package.loaded.ota_gr_transfer={new=function()return {start=function()return true end,step=function()return true end,status=function()return {phase='VERIFIED'}end,
 ready=function()return true end,pause=function()end,on_frame=function()return false end,on_tx_sent=function()end,on_tx_failed=function()end}end}
inits=0;hashes=0;snaps=0;reads=0;commits=0
dp={size=function()return 0 end,remove=function()return true end,read=function(p,o,n)reads=reads+1;return string.rep('x',n)end,
 verify_file=function(p,j)hashes=hashes+1;ticks=ticks+11000;return {size=j.size,sha256=j.sha256,md5=j.md5}end}
package.loaded.ota_data_inventory={transaction_snapshot=function(job,path,can_read,boot,allow)snaps=snaps+1;ticks=ticks+5000
 return {schema=1,complete=true,scope='root_files_kv_unverified',kv_unverified=true,digest=string.rep('d',64),files=3,keys=0}end}
nfp={native={init=function()inits=inits+1;ticks=ticks+5000;return true end,wait=function()return true end,run=function(d)written=(written or 0)+#d;return true,written>=CATJ.size,0 end,
 isDone=function()return true,(written or 0)>=CATJ.size end,finish=function()return true end},load=function()return nil,true end,
 save=function(x)if type(x)=='table' and x.phase=='COMMITTING' then commits=commits+1 end;return true end,
 native_contract_verified=function()return true end,require_data_identity=true,allow_unavailable_kv=true,now=function()return 100 end,
 -- SAM | 2026-11-10 | production gate: the unverified-KV scope is allowed for an upgrade of the running version (ota_trial eligible)
 first_trial=require('ota_trial').new({core_sha256='29a3f2dc4eb07badc1093bf8b48f04fa54b40a6d537d1c0814dcfadf53693eec',evidence_sha256=string.rep('a',64)},
  function()return {model='Air780EGH',core='V2052',bits=64,fs_bytes=524288,version=PRODUCT_VERSION} end)}
R=dofile(src..'/ota_runtime.lua')
function boot()r=R.new({store=newstore(),codec=json,download_port=dp,native_fota_port=nfp,
 bundle_port={verify_manifest=function()return true end,free_bytes=function()return 495616 end}})end
-- GR simulation: explicit replies, plus an optional responder for QUERY / CAT_PROOF / REBOOT.
function msg(op,phase,epoch,safe)local m=reply(r,op,phase,epoch);m.reason='ok';m.commit_safe=safe~=false;return m end
function gr(op,phase,epoch,safe)return r:on_gr_line('OTA_GR='..json.encode(msg(op,phase,epoch,safe)))end
function acts()local n=0;for _,x in ipairs(sent)do if x.op=='ACTIVATE' then n=n+1 end end;return n end
seen=0;gr_phase=nil;gr_safe=true
function respond()
 while seen<#sent do seen=seen+1;local x=sent[seen]
  if x.op=='CAT_PROOF' then local a=msg('PROOF_ACK',gr_phase or 'DOWNLOADING',x.epoch);a.offset=x.offset+#x.data/2;r:on_gr_line('OTA_GR='..json.encode(a))
  elseif x.op=='QUERY' and gr_phase then gr('STATUS',gr_phase,x.epoch,gr_safe)
  elseif x.op=='REBOOT' then local g=msg('REBOOT_GRANT','INSTALL_PENDING',x.epoch);g.ticket=x.ticket;r:on_gr_line('OTA_GR='..json.encode(g)) end
 end
end
function pump(n,done)for i=1,n do r:tick();respond();if done() then return true end end;return done() end
sys=sys or {};sys.publish=function()return true end;sys.wait=function()local s=r:status();if gr_phase and s.job then gr('STATUS',gr_phase,s.epoch,gr_safe) end end
-- Device-like history after round 1 (shapes as the round-1 validators accepted them).
OLD5='83c3ec64d40ab2340cf745e116d2b3ed'
local h={schema=1,phase='IDLE',outbox={},next_id=40,failures={[string.rep('e',64)]=1},retries={[string.rep('a',64)]={count=2,next_retry=200,permanent=false}},
 release={manifest=string.rep('b',64),command={MsgType='otaMsg',CurrentVersion='1.0.2',TargetVersion='1.5.1',Address='https://example.invalid/old.zip',Md5=OLD5,Time=7},
  gr_hash=string.rep('c',64),cat_hash=string.rep('d',64),gr_finished=true,gr_done=true,gr_cleaned=true,cat_finished=true,cat_done=true,cat_cleaned=true},
 trial={id=string.rep('c',64),hash=string.rep('c',64),epoch=5,md5=OLD5,status='RUNNING'},
 t151=true,t151_prior={id=string.rep('f',64),hash=string.rep('f',64),epoch=4,md5=string.rep('f',32),status='SPENT'},t151i='FINISHED',t151k='FINISHED',t151kn=3,t151k2=true,
 t151k_reason='ACTIVATION_RECHECK_FAILED',gr_r4='FINISHED'}
assert(newstore():save(h));boot();assert(not r:status().error,'HISTORY_REJECTED '..tostring(r:status().error))
'''

GR_PART = r'''
-- 1. Start (what OTA_TRIAL does) and the GR grant mints the 1.5.2 ticket.
local cmd={MsgType='otaMsg',CurrentVersion='1.5.1',TargetVersion='1.5.2',Address='https://example.invalid/y.zip',Md5=OTA_TRIAL_MD5,Time=9}
local ok,why=r:accept(cmd);assert(ok,'ACCEPT '..tostring(why));assert(r:status().phase=='WAIT_GR' and sent[#sent].op=='REQUEST','NO_REQUEST')
gr('GRANT','DOWNLOADING',7);local s=r:status()
if not old then assert(s.phase=='GR_GRANTED' and s.trial.status=='ARMED' and s.trial.epoch==7 and s.trial_prior.epoch==5,'NO_MINT') else
 s=newstore():load();s.trial={id=s.job.id,hash=s.job.hash,epoch=7,md5=OTA_TRIAL_MD5,status='ARMED'};assert(newstore():save(s));boot();gr('STATUS','DOWNLOADING',7) end
-- 2. GR candidate staged; PREPARED acknowledged; one ACTIVATE.
assert(pump(4,function()return r:status().phase=='PREPARED' end),'GR_NOT_PREPARED '..tostring(r:status().reason)..' '..tostring(r.last_tick_reason))
gr('STATUS','PREPARED',7);local a0=acts();r:tick();assert(r:status().phase=='WAIT_ACTIVATE' and acts()==a0+1,'NO_ACTIVATE '..tostring(r.last_tick_reason))
-- 3. Defect 1: ACTIVATE denied boot_commit_failed with GR owner still INSTALL_PENDING.
local d=msg('DENY','INSTALL_PENDING',7);d.reason='boot_commit_failed';r:on_gr_line('OTA_GR='..json.encode(d))
for i=1,8 do r:tick() end
'''

GR_NEW = r'''
s=r:status();assert(s.phase=='WAIT_ACTIVATE' and s.io=='RUNNING' and s.trial.status=='RUNNING' and acts()==a0+2,'NO_SINGLE_RESEND '..tostring(s.phase)..' '..tostring(s.io)..' '..acts())
for i=1,30 do r:tick() end;assert(acts()==a0+2,'SECOND_RESEND')
gr('STATUS','INSTALL_PENDING',7);assert(r:status().phase=='WAIT_ACTIVATE','STATUS_CHANGED_WAIT')
gr('GRANT','INSTALL_PENDING',7,grant_safe);s=r:status()
assert(s.phase==(grant_safe and 'INSTALLING' or 'RECOVERY_HOLD'),'GR_GRANT '..tostring(s.phase)..' '..tostring(s.reason))
local c=msg('STATUS','COMPLETE',7);c.outcome='success';c.version='1.5.2';assert(r:on_gr_line('OTA_GR='..json.encode(c)))
-- A durable STATUS COMPLETE both records the result and releases (manager on_gr falls through COMPLETE_PENDING -> IDLE).
s=r:status();assert(s.phase=='IDLE' and s.release.gr_done and s.io2.v=='FINISHED' and s.trial.status=='RUNNING','GR_RESULT '..tostring(s.phase)..' '..json.encode(s.io2)..' '..tostring(s.trial.status))
'''

CAT_PART = r'''
-- 4. CAT1 component of the same bundle.
comp='CAT1';clk=clk+100000;seen=#sent
assert(pump(4,function()return r:status().phase=='WAIT_GR' end),'CAT1_NOT_ACCEPTED '..tostring(r:status().phase)..' '..tostring(r.last_tick_reason))
assert(r:status().job.target=='CAT1')
gr('GRANT','DOWNLOADING',8);seen=#sent
assert(pump(20,function()return r:status().phase=='PREPARED' end),'CAT1_NOT_PREPARED '..tostring(r:status().reason)..' '..tostring(r.last_tick_reason))
local np=0;for _,x in ipairs(sent)do if x.op=='CAT_PROOF' then np=np+1 end end;assert(np==4,'PROOF_CHUNKS '..np)
gr('STATUS','PREPARED',8);local a1=acts();r:tick();assert(r:status().phase=='WAIT_ACTIVATE' and acts()==a1+1,'CAT1_NO_ACTIVATE')
-- 5. Defect 2: the CAT1 GRANT arrives without commit_safe (computed after GR's owner write).
gr('GRANT','INSTALL_PENDING',8,false);s=r:status()
'''

CAT_NEW = r'''
assert(s.phase=='RECOVERY_HOLD' and s.io=='ARMED' and s.reason=='CAT1_INSTALL_ARMED' and inits==0,'NOT_ARMED '..tostring(s.phase)..' '..tostring(s.reason))
-- 6. Install-only path: rebuild + baseline + receipt before authority; GR answers QUERY with commit-safe STATUS INSTALL_PENDING.
gr_phase='INSTALL_PENDING';gr_safe=false;seen=#sent;local h0=hashes
pump(3,function()return false end);assert(r:status().io=='ARMED' and inits==0,'UNSAFE_STATUS_SPENT_OR_STARTED '..tostring(r:status().io))
gr_safe=true
assert(pump(10,function()return r:status().phase=='INSTALLING' end),'NO_INSTALL '..tostring(r:status().phase)..' '..tostring(r:status().reason)..' '..tostring(r.last_tick_reason)..' '..table.concat(diag,'|'))
assert(inits==1 and acts()==a1+1 and r:status().io=='RUNNING','START '..inits)
-- 7. Writes, then the commit with the slow rehash/scan, then REBOOT -> REBOOT_GRANT -> reset dispatched once.
assert(pump(80,function()return reboots>0 end),'NO_REBOOT reads='..reads..' commits='..commits..' '..tostring(r:native_diag())..' '..tostring(r.last_tick_reason)..' '..table.concat(diag,'|'))
assert(reads==62 and commits==2 and reboots==1 and inits==1 and snaps==4,'COMMIT reads='..reads..' commits='..commits..' snaps='..snaps) -- COMMITTING: intent + commit; snapshots: baseline, final-chunk + post-isDone commit checks, pre-reboot
s=r:status();assert(s.phase=='INSTALLING' and s.trial.status=='RUNNING' and s.io=='RUNNING','END_STATE '..tostring(s.phase))
'''

# SAM | 2026-10-29 22:55 +08:00 | Board 22:44: the DENY arrives, then GR's STATUS answering a QUERY sent before it.
BOARD_2244 = r'''
local d=msg('DENY','INSTALL_PENDING',7);d.reason='boot_commit_failed';r:on_gr_line('OTA_GR='..json.encode(d))
gr('STATUS','INSTALL_PENDING',7)
'''
# From the device state now (RECOVERY_HOLD, io2 ARMED n=0, reason ACTIVATION_STATUS_REQUIRES_RECOVERY), reflash = reboot, then GR STATUS.
RESUME_2244 = r'''
local x=newstore():load();x.phase='RECOVERY_HOLD';x.reason='ACTIVATION_STATUS_REQUIRES_RECOVERY';x.io2={id=x.job.id,n=0,v='ARMED'};assert(newstore():save(x));boot()
s=r:status();assert(s.phase=='RECOVERY_HOLD' and s.reason=='INSTALL_RECOVERY_INTERRUPTED' and s.io=='SPENT' and s.trial.status=='SPENT','REBOOT_STATE '..tostring(s.reason))
local b0=acts();gr('STATUS','INSTALL_PENDING',7,false);assert(acts()==b0 and r:status().phase=='RECOVERY_HOLD','UNSAFE_RESENT')
gr('STATUS','INSTALL_PENDING',7);s=r:status();assert(acts()==b0+1 and s.phase=='WAIT_ACTIVATE' and s.io=='RUNNING' and s.io_n==1,'NO_RESUME '..acts()..' '..tostring(s.phase))
gr('STATUS','INSTALL_PENDING',7);for i=1,30 do r:tick() end;assert(acts()==b0+1,'SECOND_RESUME')
gr('GRANT','INSTALL_PENDING',7);local c=msg('STATUS','COMPLETE',7);c.outcome='success';c.version='1.5.2';assert(r:on_gr_line('OTA_GR='..json.encode(c)))
s=r:status();assert(s.phase=='IDLE' and s.release.gr_done and s.io2.v=='FINISHED' and s.trial.status=='RUNNING','RESUME_RESULT '..json.encode(s.io2))
-- never a second resume for the same job: back to a hold with n=1 -> no ACTIVATE
'''
RESUME_ONCE = r'''
local x=newstore():load();x.phase='RECOVERY_HOLD';x.reason='INSTALL_RECOVERY_INTERRUPTED';x.io2={id=x.job.id,n=1,v='SPENT'};assert(newstore():save(x));boot()
local b0=acts();gr('STATUS','INSTALL_PENDING',7);for i=1,10 do r:tick() end;assert(acts()==b0 and r:status().phase=='RECOVERY_HOLD','RESUMED_TWICE')
'''

OLD_CHECK = r'''
s=r:status();assert(acts()==a0+1 and s.phase=='RECOVERY_HOLD','OLD_GR '..tostring(s.phase)..' '..acts())
print('REPRODUCED round 1 (GR): boot_commit_failed -> RECOVERY_HOLD, no re-ACTIVATE')
'''


def version_pair(source):
    """OTA_TRIAL_SOURCE/TARGET of the receiver under test; None for receivers that predate them."""
    import re
    text = (source / 'main.lua').read_text(encoding='utf-8', errors='replace')
    s = re.search(r"^OTA_TRIAL_SOURCE='([^']+)'", text, re.M)
    t = re.search(r"^OTA_TRIAL_TARGET='([^']+)'", text, re.M)
    return (s.group(1), t.group(1)) if s and t else None


def run(source, body, old=None):
    # SAM | 2026-10-30 09:14 +08:00 | The scenario is written for 1.5.1->1.5.2; re-target it to the receiver's own range (e.g. 1.5.2->1.5.3).
    lua_text = SETUP + body
    pair = version_pair(source)
    if pair and pair != ('1.5.1', '1.5.2'):
        lua_text = lua_text.replace("'1.5.2'", '@T@').replace("'1.5.1'", '@S@').replace('@T@', "'" + pair[1] + "'").replace('@S@', "'" + pair[0] + "'")
    lua = runtime()
    lua.globals().src = source.as_posix()
    lua.globals().old = old
    lua.execute(lua_text)


def main():
    source = Path(sys.argv[1]).resolve()
    if len(sys.argv) > 3 and sys.argv[2] == '--old':
        old = Path(sys.argv[3]).resolve()
        run(old, GR_PART + OLD_CHECK, True)
        # CAT1 GRANT without commit_safe on the old receiver: from the CAT1 PREPARED state forged into its store.
        run(old, r'''
local s=newstore():load();s.phase='WAIT_ACTIVATE';s.epoch=8;s.prepared_ack=true;s.job=clone(CATJ);s.job.source='1.5.1';s.job.version='1.5.2'
s.job.url='https://example.invalid/y.zip';s.job.bundle={md5=OTA_TRIAL_MD5,manifest_sha256=MAN}
s.release={manifest=MAN,command={MsgType='otaMsg',CurrentVersion='1.5.1',TargetVersion='1.5.2',Address=s.job.url,Md5=OTA_TRIAL_MD5,Time=9},gr_hash=GRJ.hash,cat_hash=CATJ.hash,
 gr_finished=true,gr_done=true,gr_cleaned=true,cat_finished=false,cat_done=false,cat_cleaned=false}
assert(newstore():save(s));boot();gr('STATUS','PREPARED',8);s=newstore():load();s.phase='WAIT_ACTIVATE';assert(newstore():save(s));boot()
gr('GRANT','INSTALL_PENDING',8,false);s=r:status()
assert(s.phase=='RECOVERY_HOLD' and s.reason=='ACTIVATION_RECHECK_FAILED' and inits==0,'OLD_CAT '..tostring(s.phase)..' '..tostring(s.reason))
print('REPRODUCED round 1 (CAT1): GRANT without commit_safe -> RECOVERY_HOLD ACTIVATION_RECHECK_FAILED, no install')
''', True)
        return
    if len(sys.argv) > 2 and sys.argv[2] == '--expect-board-2244':
        # SAM | 2026-10-29 22:55 +08:00 | Board 22:44: a STATUS (reply to a pre-DENY QUERY) inside the re-ACTIVATE wait -> RECOVERY_HOLD, no resend.
        run(source, GR_PART.split('-- 3. Defect 1')[0] + BOARD_2244 + r'''
for i=1,10 do r:tick() end;s=r:status()
assert(s.phase=='RECOVERY_HOLD' and s.reason=='ACTIVATION_STATUS_REQUIRES_RECOVERY' and acts()==a0+1,'NOT_REPRODUCED '..tostring(s.phase)..' '..acts()..' '..tostring(s.reason))
''')
        print('REPRODUCED board 22:44: STATUS inside the re-ACTIVATE wait -> RECOVERY_HOLD ACTIVATION_STATUS_REQUIRES_RECOVERY, resend never sent');return
    if len(sys.argv) > 2 and sys.argv[2] == '--expect-reboot-failure':
        # Runtime before the 20:18 pre-reboot snapshot: the reboot-time scan + refresh outlives GR's 3 s REBOOT_GRANT; no reset is dispatched.
        run(source, GR_PART + GR_NEW.replace('grant_safe', 'true') + CAT_PART + CAT_NEW.split('-- 7.')[0] + r'''
pump(80,function()return reboots>0 end);assert(reboots==0 and r:native_diag():find('^COMMITTED'),'REBOOT_FAILURE_NOT_REPRODUCED '..tostring(r:native_diag()))
''')
        print('REPRODUCED: native COMMITTED but REBOOT_GRANT never dispatches the reset (reboot-time data scan outlives the 3 s grant)');return
    for grant_safe in (True, False):
        run(source, GR_PART + GR_NEW.replace('grant_safe', 'true' if grant_safe else 'false') + CAT_PART + CAT_NEW)
    # SAM | 2026-10-29 22:55 +08:00 | Board 22:44 case on the fixed code: the STATUS inside the wait is ignored and the single resend goes out.
    run(source, GR_PART.split('-- 3. Defect 1')[0] + BOARD_2244 + r'''
for i=1,8 do r:tick() end;s=r:status();assert(s.phase=='WAIT_ACTIVATE' and s.io=='RUNNING' and acts()==a0+2,'2244_NOT_FIXED '..tostring(s.phase)..' '..acts())
''')
    # Recovery of the device's current state after the reflash, and never a second resume.
    run(source, GR_PART.split('-- 3. Defect 1')[0] + RESUME_2244)
    run(source, GR_PART.split('-- 3. Defect 1')[0] + RESUME_ONCE)
    # SAM | 2026-10-29 20:20 +08:00 | Bounds: a second boot_commit_failed after the one re-ACTIVATE holds (no third ACTIVATE) and spends the ticket.
    run(source, GR_PART + r'''
local d2=msg('DENY','INSTALL_PENDING',7);d2.reason='boot_commit_failed';r:on_gr_line('OTA_GR='..json.encode(d2))
for i=1,40 do r:tick() end;local s=r:status()
assert(acts()==a0+2 and s.phase=='RECOVERY_HOLD' and s.io=='SPENT' and s.trial.status=='SPENT','SECOND_DENY '..tostring(s.phase)..' '..acts())
''')
    # CAT1 reboot while armed: spent as INTERRUPTED (ticket kept after GR done), then the runtime re-arms once by itself and installs.
    run(source, GR_PART + GR_NEW.replace('grant_safe', 'true') + CAT_PART + r'''
assert(s.io=='ARMED');boot();s=r:status()
assert(s.phase=='RECOVERY_HOLD' and s.io=='SPENT' and s.reason=='INSTALL_RECOVERY_INTERRUPTED' and s.trial.status=='RUNNING','REBOOT_ARMED '..tostring(s.io)..' '..tostring(s.trial.status))
gr_phase='INSTALL_PENDING';gr_safe=true;seen=#sent
assert(pump(45,function()return r:status().phase=='INSTALLING' end),'NO_AUTO_REARM '..tostring(r:status().io)..' '..table.concat(diag,'|'))
assert(r:status().io_n==1 and inits==1,'REARM_COUNT '..tostring(r:status().io_n))
''')
    # At most three re-arms per job: the fourth is refused with the scope code and nothing changes.
    run(source, GR_PART + GR_NEW.replace('grant_safe', 'true') + CAT_PART + r'''
local x=newstore():load();x.io2.v='SPENT';x.io2.n=3;assert(newstore():save(x));boot();local old=json.encode(newstore():load())
gr_phase='INSTALL_PENDING';seen=#sent;pump(65,function()return false end)
assert(json.encode(newstore():load())==old and inits==0,'FOURTH_ARM');local hit=false;for _,l in ipairs(diag)do if l=='[OTA] arm IO_SCOPE_1011111' then hit=true end end;assert(hit,'NO_SCOPE_DIAG '..table.concat(diag,'|'))
''')
    # OTA_TRIAL start command (update.lua, 2026-11-10 syntax OTA_TRIAL=<target> <url>): no target, URL without md5, zero md5 or a malformed target are refused; the exact form starts.
    run(source, r'''
tasks={};sys.subscribe=function()end;sys.taskInit=function(f)tasks[#tasks+1]=f end
vu={};uart={VUART_0=32,setup=function()return 0 end,write=function(_,x)vu[#vu+1]=x;return true end}
package.loaded.ota_runtime=R;R.set_instance(r);_G.at_cmd_handlers={};dofile(src..'/update.lua')
local h=_G.at_cmd_handlers.OTA_TRIAL;local out={};local function say(x)out[#out+1]=x end
local url='https://example.invalid/d?fileId=1&md5='..OTA_TRIAL_MD5
h('OTA_TRIAL=https://example.invalid/d?md5='..string.rep('5',32),say);assert(out[1]=='OTA_TRIAL=REFUSED','NO_TARGET')
h('OTA_TRIAL=1.5.2 https://example.invalid/d?md5='..string.rep('0',32),say);assert(out[2]=='OTA_TRIAL=REFUSED','ZERO_MD5')
h('OTA_TRIAL=1.5.2 https://example.invalid/d?fileId=1',say);assert(out[3]=='OTA_TRIAL=REFUSED','NO_URL_MD5')
h('OTA_TRIAL=1.5 '..url,say);assert(out[4]=='OTA_TRIAL=REFUSED','BAD_TARGET')
local n=#tasks;h('OTA_TRIAL=1.5.2 '..url,say);assert(#tasks==n+1);tasks[#tasks]();assert(out[5]=='OTA_TRIAL=WAIT_GR' and r:status().phase=='WAIT_GR','START '..tostring(out[5]))
local st={};_G.at_cmd_handlers.FOTA_STATUS('FOTA_STATUS',function(x)st[#st+1]=x end);assert(st[1]=='WAIT_GR','STATUS_LINE')
local io;for _,x in ipairs(st)do if x:find('^OTA_IO=') then io=x end end;assert(io=='OTA_IO=nil/0 TRIAL=RUNNING','IO_LINE '..tostring(io))
''')
    # SAM | 2026-10-29 22:24 +08:00 | OTA_PRUNE (board 22:16 COMPONENT_SPACE): from GR_GRANTED with round-1 history, the archive streams to VUART
    # first, then only the legacy keys go; task/trial/release/retries/failures stay, the store reloads, the task continues, a repeat is a no-op.
    run(source, r'''
tasks={};sys.subscribe=function()end;sys.taskInit=function(f)tasks[#tasks+1]=f end
vu={};uart={VUART_0=32,setup=function()return 0 end,write=function(_,x)vu[#vu+1]=x;return true end}
local s=newstore():load();s.retired={job={id='x'},release={command={Md5='5c38e1d5e9615c98deeb76c77646124a'}},receipt='retired_before_install'}
s.r6_handoff={phase='ACTIVE',epoch=4,install_state='FINISHED',old={job={id='y'}}};s.cancelled={id='z'};assert(newstore():save(s));boot()
local cmd={MsgType='otaMsg',CurrentVersion='1.5.1',TargetVersion='1.5.2',Address='https://example.invalid/y.zip',Md5=OTA_TRIAL_MD5,Time=9}
assert(r:accept(cmd));gr('GRANT','DOWNLOADING',7);local before=r:status();assert(before.phase=='GR_GRANTED' and before.trial_prior)
package.loaded.ota_runtime=R;R.set_instance(r);_G.at_cmd_handlers={};dofile(src..'/update.lua')
local out={};_G.at_cmd_handlers.OTA_PRUNE('OTA_PRUNE',function(x)out[#out+1]=x end)
local arch='';for _,x in ipairs(vu) do local t=x:match('^%[OTA%] PRUNE_ARCHIVE %d+ (.*)\r\n$');if t then arch=arch..t end end
assert(out[1]=='OTA_PRUNE=DONE '..#arch and #arch>100,'PRUNE '..tostring(out[1])..' '..#arch)
local a=json.decode(arch);for _,k in ipairs({'retired','r6_handoff','cancelled','trial_prior','t151','t151k','t151kn','gr_r4'}) do assert(a[k]~=nil,'ARCHIVE_MISSING '..k) end
local x=newstore():load();for _,k in ipairs({'retired','r6_handoff','cancelled','trial_prior','t151','t151_prior','t151i','t151k','t151kn','t151k2','t151k_reason','gr_r4'}) do assert(x[k]==nil,'LEFT '..k) end
for _,k in ipairs({'phase','epoch','job','trial','release','retries','failures','outbox','next_id'}) do assert(json.encode(x[k])==json.encode(before[k]),'CHANGED '..k) end
assert(#json.encode(x)<#json.encode(newstore():load())+1 and #json.encode(x)<1500,'STILL_LARGE '..#json.encode(x))
boot();assert(not r:status().error and r:status().phase=='GR_GRANTED','RELOAD');gr('STATUS','DOWNLOADING',7)
assert(pump(4,function()return r:status().phase=='PREPARED' end),'NOT_CONTINUED '..tostring(r.last_tick_reason))
local ok,t=r:prune_history(true);assert(ok and t=='','REPEAT '..tostring(t))
local y=json.encode(newstore():load());local w0=0;local sv=disk.write;disk.write=function(p,x)w0=w0+1;return sv(p,x)end;local ok2,t2=r:prune_history(false);disk.write=sv
assert(ok2 and t2=='' and w0>=1 and json.encode(newstore():load())==y,'NOOP_REWRITE '..w0) -- board 22:29: replaces the stale journal copy, content unchanged
''')
    # SAM | 2026-10-29 20:24 +08:00 | FOTA_PROBE: refused unless IDLE; times init/wait, then finish(false) only (no run, no finish(true), no reboot).
    run(source, r'''
tasks={};sys.subscribe=function()end;sys.taskInit=function(f)tasks[#tasks+1]=f end
uart={VUART_0=32,setup=function()return 0 end,write=function()return true end}
package.loaded.ota_runtime=R;R.set_instance(r);_G.at_cmd_handlers={};dofile(src..'/update.lua')
calls={};local waits=0
fota={init=function()calls[#calls+1]='init';ticks=ticks+4200;return true end,wait=function()waits=waits+1;calls[#calls+1]='wait';return waits>=3 end,
 finish=function(x)calls[#calls+1]='finish:'..tostring(x);return true end,run=function()calls[#calls+1]='run' end}
local h=_G.at_cmd_handlers.FOTA_PROBE;local out={};local function say(x)out[#out+1]=x end
h('FOTA_PROBE',say);local n=#tasks;tasks[n]();
assert(out[1] and out[1]:find('^FOTA_PROBE init=true/42%d%dms wait=true/%d+ms/3 finish0=true/%d+ms$'),'PROBE_LINE '..tostring(out[1]))
assert(table.concat(calls,',')=='init,wait,wait,wait,finish:false' and reboots==0,'PROBE_CALLS '..table.concat(calls,','))
local cmd={MsgType='otaMsg',CurrentVersion='1.5.1',TargetVersion='1.5.2',Address='https://example.invalid/y.zip',Md5=OTA_TRIAL_MD5,Time=9}
assert(r:accept(cmd));h('FOTA_PROBE',say);assert(out[2]=='FOTA_PROBE=REFUSED WAIT_GR none' or out[2]:find('^FOTA_PROBE=REFUSED WAIT_GR'),'PROBE_NOT_REFUSED '..tostring(out[2]))
''')
    print('PASS ota152 flow: history accepted; 1.5.2 ticket minted at GR grant (1.5.1 ticket kept); boot_commit_failed -> exactly one '
          're-ACTIVATE; GR success (GRANT commit_safe true or false) -> io FINISHED, ticket RUNNING; CAT1 component proof 4 chunks; '
          'CAT1 GRANT without commit_safe -> install-only path; unsafe STATUS only waits; real native start (5 s init) -> 62 chunks -> '
          'commit after 11 s rehash + 5 s scan -> one REBOOT_GRANT reset; second boot_commit_failed holds; CAT1 reboot while armed -> one '
          'automatic re-arm -> install; fourth arm refused; OTA_TRIAL refuses a missing target/URL md5/zero md5/bad target and starts the exact form')


if __name__ == '__main__':
    main()
