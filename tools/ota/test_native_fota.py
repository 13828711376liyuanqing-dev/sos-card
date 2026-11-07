# SAM | 2026-10-24 +08:00 | Fixtures use explicit installation evidence; legacy pending flags are rejected separately.
"""SAM | 2026-10-23 +08:00 | Exercise native commit ordering without touching hardware."""
from test_cat_manager import runtime

SETUP = '''
local module = require('ota_native_fota')
calls={}; disk=nil; safe=true; owner=true; clock=10; fail_save=false
local function event(s) calls[#calls+1]=s end
port={
 load=function() return disk,true end,
 save=function(r) if fail_save then return false end;disk=json.decode(json.encode(r));event(r.phase);return true end,
 safe=function()return safe end, owner=function()return owner end,
 verify=function()return true end, now=function()return clock end,
 read=function(path,offset,n)return string.rep('x',n) end,
 native_contract_verified=function()return true end,
 native={init=function()event('init');return true end,wait=function()return true end,
 run=function(s)event('run');return true,#s==904,0 end,
 isDone=function()return true,true end,
 finish=function(ok)event(ok and 'finish_true' or 'finish_false');return true end}
}
job={id='test',target='CAT1',hash=string.rep('a',64),size=5000,version='1.5.0'}
f=module.new(port)
'''

def check(name, body):
    lua = runtime()
    lua.execute(SETUP + body)
    print('PASS', name)

if __name__ == '__main__':
    # SAM | 2026-10-24 +08:00 | Official fota.run cache >64KiB requires waiting, not aborting a valid write.
    check('native backpressure waits without dropping the accepted block or replaying it', '''
      local runs=0;local waits=0
      port.native.wait=function()waits=waits+1;return true end
      port.native.run=function(s)runs=runs+1;event('run');return true,#s==904,runs==1 and 65537 or 0 end
      assert(f:start(job,'candidate',7))
      local ok,why=f:step();assert(ok and why=='WAIT_CACHE');assert(f:status().offset==4096 and runs==1)
      local n=#calls;local w=waits
      ok,why=f:step();assert(ok and why=='WAIT_CACHE' and #calls==n and waits==w)
      clock=10.099;assert(f:step());assert(runs==1)
      clock=10.1;port.native.wait=function()return false end
      assert(f:step());assert(runs==1 and f:status().offset==4096)
      port.native.wait=function()return true end
      assert(f:step());assert(runs==2 and f:status().offset==5000)
      assert(f:step());assert(f:status().phase=='COMMITTED')
      for _,v in ipairs(calls)do assert(v~='finish_false')end
    ''')
    check('backpressure does not extend authority or the original overall timeout', '''
      port.native.run=function()return true,false,70000 end
      assert(f:start(job,'candidate',7));assert(f:step());owner=false
      local ok,why=f:step();assert(not ok and why=='AUTHORITY_LOST')
      assert(f:status().phase=='HOLD' and calls[#calls-1]=='finish_false')
      local n=#calls;assert(not f:step());assert(#calls==n)
    ''')
    check('timeout while waiting for native cache still cancels and holds', '''
      port.native.run=function()return true,false,70000 end
      assert(f:start(job,'candidate',7));assert(f:step());clock=131
      local ok,why=f:step();assert(not ok and why=='TIMEOUT_OR_CLOCK')
      assert(f:status().phase=='HOLD' and calls[#calls-1]=='finish_false')
    ''')
    for cache in ['-1','0/0','math.huge','65537.5','2147483648',"'bad'",'nil']:
        check('malformed native cache is rejected: '+cache, '''
          port.native.run=function()return true,false,'''+cache+''' end
          assert(f:start(job,'candidate',7));local ok,why=f:step()
          assert(not ok and why=='WRITE_FAILED');assert(f:status().phase=='HOLD')
        ''')
    # SAM | 2026-10-23 +08:00 | Required code identity survives reset and cannot be replaced by a caller's healthy/version flags.
    check('native persists signed code identity before init and requires readback after boot', '''
      job.source='1.0.2';job.bundle={manifest_sha256=string.rep('b',64)}
      local expected={files={['main.luac']=string.rep('c',64)},file_count=1,version='001.005.000',
        package_sha256=job.hash,manifest_sha256=job.bundle.manifest_sha256,build_record_sha256=string.rep('d',64)}
      port.require_code_identity=true
      local bad=true;port.expected_identity=function()if bad then return nil end;return expected end
      local ok,why=f:start(job,'candidate',7);assert(not ok and why=='BOOT_IDENTITY_REQUIRED');assert(#calls==0)
      bad=false;assert(f:start(job,'candidate',7));assert(disk.code_identity_required and disk.expected_identity.files['main.luac']==string.rep('c',64))
      expected.files['main.luac']='changed';assert(disk.expected_identity.files['main.luac']==string.rep('c',64))
      assert(f:step());assert(f:step());assert(f:step());f=module.new(port)
      local info={job=job.id,hash=job.hash,epoch=7,version=job.version,healthy=true,installation_verified=true,data_ok=true}
      local ready=false;port.code_identity=function(e)assert(e.package_sha256==job.hash);return ready,'BOOT_IDENTITY_CHECKING' end
      assert(not f:confirm(job,7,info));assert(disk.phase=='COMMITTED')
      ready=true;local accepted,result=f:confirm(job,7,info);assert(accepted and result.code_identity==true)
      -- An old confirmed record without a real code proof cannot be retired under the production requirement.
      disk.result.code_identity=nil;f=module.new(port)
      assert(not f:retire({job=job,epoch=7,version=job.version}))
    ''')
    # SAM | 2026-10-23 +08:00 | A controlled reset must have durable intent and never replay after reboot or accept a stale task.
    check('native controlled reboot persists once and preserves confirmation evidence', '''
      job.source='1.0.2';local reboots=0
      port.reboot=function()assert(disk.phase=='REBOOTING');reboots=reboots+1;return true end
      assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());assert(f:step())
      assert(not f:reboot(job,8));safe=false;assert(not f:reboot(job,7));safe=true
      fail_save=true;assert(not f:reboot(job,7));assert(reboots==0);fail_save=false
      assert(f:reboot(job,7));assert(reboots==1);assert(not f:reboot(job,7))
      f=module.new(port);assert(not f:reboot(job,7));assert(reboots==1)
      assert(f:confirm(job,7,{job=job.id,hash=job.hash,epoch=7,version=job.version,
        healthy=true,installation_verified=true,data_ok=true}))
    ''')
    # SAM | 2026-10-23 +08:00 | Retire only a matching confirmed transaction; tombstone makes a lost manager acknowledgement safe to repeat.
    check('released native record permits next upgrade with durable idempotent retirement', '''
      job.source='1.0.2';assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());assert(f:step())
      local token={job=job,epoch=7,version=job.version}
      assert(not f:retire(token))
      f=module.new(port);assert(f:confirm(job,7,{job=job.id,hash=job.hash,epoch=7,version=job.version,
        healthy=true,installation_verified=true,data_ok=true}))
      token.epoch=8;assert(not f:retire(token));token.epoch=7
      fail_save=true;assert(not f:retire(token));fail_save=false
      assert(f:retire(token));assert(f:status().phase=='IDLE')
      f=module.new(port);assert(f:status().phase=='IDLE');assert(f:retire(token))
      job.id='next';assert(f:start(job,'candidate',8));assert(not f:retire(token))
      assert(f:step());assert(f:step());assert(f:step());f=module.new(port)
      assert(f:confirm(job,8,{job=job.id,hash=job.hash,epoch=8,version=job.version,
        healthy=true,installation_verified=true,data_ok=true}))
    ''')
    # SAM | 2026-10-23 +08:00 | Post-boot confirmation must bind the durable commit and health evidence before reporting success.
    check('post boot confirmation binds task and persists result without replay', '''
      job.source='1.0.2';assert(f:start(job,'candidate',7));assert(f:step());assert(f:step());assert(f:step())
      local info={job=job.id,hash=job.hash,epoch=7,version=job.version,healthy=true,installation_verified=true,data_ok=true}
      assert(not f:confirm(job,7,info),'pre-reboot result accepted')
      f=module.new(port);local n=#calls
      info.epoch=8;assert(not f:confirm(job,7,info));info.epoch=7
      info.data_ok=false;assert(not f:confirm(job,7,info));info.data_ok=true
      fail_save=true;assert(not f:confirm(job,7,info));fail_save=false
      local ok,result=f:confirm(job,7,info);assert(ok and result.version==job.version)
      assert(f:status().phase=='CONFIRMED' and disk.phase=='CONFIRMED')
      assert(#calls==n+1 and calls[#calls]=='CONFIRMED')
      f=module.new(port);assert(f:confirm(job,7,info));assert(not f:start(job,'candidate',7))
    ''')
    # SAM | 2026-10-23 +08:00 | Recovery must retain the durable identity without replaying native writes.
    check('reboot preserves durable task and commit uncertainty', '''
      assert(f:start(job,'candidate',7));assert(f:step());assert(f:step())
      port.native.finish=function(ok)fail_save=true;return true end
      assert(not f:step());assert(disk.phase=='COMMITTING')
      local n=#calls;f=module.new(port);local s=f:status()
      assert(s.phase=='RECOVERY_HOLD' and s.recovery_phase=='COMMITTING')
      assert(s.job.id==job.id and s.job.hash==job.hash and s.job.version=='1.5.0')
      assert(s.path=='candidate' and s.epoch==7 and s.offset==5000)
      s.job.id='changed';assert(f:status().job.id==job.id)
      disk.job.id='external';assert(f:status().job.id==job.id)
      assert(not f:step());assert(not f:start(job,'candidate',7));assert(#calls==n)
    ''')
    check('bounded chunks and durable intent precede native commit', '''
      assert(f:start(job,'candidate',1));assert(calls[1]=='INTENT' and calls[2]=='init')
      assert(f:step());assert(f:status().offset==4096)
      assert(f:step());assert(f:status().offset==5000)
      assert(f:step());assert(f:status().phase=='COMMITTED')
      assert(calls[#calls-2]=='COMMITTING' and calls[#calls-1]=='finish_true')
      assert(not f:step());assert(not f:start(job,'candidate',1))
    ''')
    check('unverified vendor contract and unsafe state do not initialize', '''
      port.native_contract_verified=function()return false end
      assert(not f:start(job,'candidate',1));assert(#calls==0)
      port.native_contract_verified=function()return true end;safe=false
      assert(not f:start(job,'candidate',1));assert(#calls==0)
    ''')
    check('lost authority aborts without commit', '''
      assert(f:start(job,'candidate',1));owner=false
      assert(not f:step());assert(f:status().phase=='HOLD')
      assert(calls[#calls-1]=='finish_false')
    ''')
    check('failed durable intent prevents native initialization', '''
      fail_save=true;assert(not f:start(job,'candidate',1));assert(#calls==0)
    ''')
    check('reset never replays any native operation', '''
      assert(f:start(job,'candidate',1));local n=#calls
      f=module.new(port);assert(f:status().phase=='RECOVERY_HOLD')
      assert(not f:step());assert(not f:start(job,'candidate',1));assert(#calls==n)
    ''')
    check('read that yields into unsafe state cannot feed native writer', '''
      assert(f:start(job,'candidate',1))
      port.read=function(p,o,n)safe=false;return string.rep('x',n) end
      assert(not f:step());for _,v in ipairs(calls)do assert(v~='run' and v~='finish_true')end
    ''')
    check('wait timeout holds and cancels', '''
      assert(f:start(job,'candidate',1));port.native.wait=function()return false end
      clock=131;assert(not f:step());assert(f:status().phase=='HOLD')
    ''')
    check('early native completion and failed commit journal never authorize finish', '''
      assert(f:start(job,'candidate',1));port.native.run=function()return true,true,0 end
      assert(not f:step());for _,v in ipairs(calls)do assert(v~='finish_true')end
    ''')
    check('commit journal failure blocks finish true', '''
      assert(f:start(job,'candidate',1));assert(f:step());assert(f:step())
      fail_save=true;assert(not f:step())
      for _,v in ipairs(calls)do assert(v~='finish_true')end
    ''')
    check('unreadable journal rejects initialization', '''
      port.load=function()return nil,false end;f=require('ota_native_fota').new(port)
      assert(not f:start(job,'candidate',1));assert(#calls==0)
    ''')
    check('vendor finish failure stays held instead of claiming commit', '''
      assert(f:start(job,'candidate',1));assert(f:step());assert(f:step())
      port.native.finish=function()return false end
      assert(not f:step());assert(f:status().phase=='HOLD')
    ''')
    check('reset after finish with lost final journal never replays commit', '''
      assert(f:start(job,'candidate',1));assert(f:step());assert(f:step())
      port.native.finish=function(ok)event('finish_true');fail_save=true;return true end
      assert(not f:step());assert(disk.phase=='COMMITTING')
      local n=#calls;f=require('ota_native_fota').new(port)
      assert(not f:step());assert(#calls==n and f:status().phase=='RECOVERY_HOLD')
    ''')
