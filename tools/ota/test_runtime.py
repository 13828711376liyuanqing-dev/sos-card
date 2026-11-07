# SAM | 2026-10-24 +08:00 | Fixtures use explicit installation evidence; legacy pending flags are rejected separately.
"""SAM | 2026-10-12 19:40 +08:00 | Integration guards run offline against production Lua."""
from test_cat_manager import runtime


def check(name, script):
    lua = runtime()
    lua.execute('''
      callbacks={}; tasks={}; replies={}; published={}; reboots=0
      sys={subscribe=function(n,f)callbacks[n]=f end,
        taskInit=function(f)tasks[#tasks+1]=f end,publish=function(n,...) published[#published+1]=n end}
      log={info=function()end,warn=function()end,error=function()end}
      rtos={reboot=function()reboots=reboots+1 end}
      -- SAM | 2026-10-29 20:09 +08:00 | Receiver update.lua writes its plain-text diagnostics to uart.VUART_0; host stub only.
      vuart={};uart={VUART_0=32,setup=function()return 0 end,write=function(id,s)vuart[#vuart+1]=s;return true end}
      _G.at_cmd_handlers={}
      _G.uart_send_raw=function(s)replies[#replies+1]=s;return true end
      R=require('ota_runtime')
    ''')
    lua.execute(script)
    print('PASS', name)


if __name__ == '__main__':
    # SAM | 2026-10-24 +08:00 | Progress is durable candidate bytes, not transfer success or an installation receipt.
    check('read-only progress reports the committed checkpoint and last tick reason', '''
      local r=R.new({store=newstore(),codec=json,port=port})
      assert(r:accept(command));r.last_tick_reason='BUSINESS_PAUSED'
      local s=r:status();assert(s.progress.target==s.job.target)
      assert(s.progress.total==s.job.size and s.progress.committed==0)
      assert(s.progress.step=='BUSINESS_PAUSED' and activation==0)
    ''')
    # SAM | 2026-10-23 +08:00 | Exercise the production default safety binding; port.safe=true in older injected tests concealed the missing GR gate.
    check('default activation requires fresh matching GR safety and survives expiry without deadlock', '''
      local clock=1000;local idle=true;mcu={ticks=function()return clock end}
      local resolve=port.resolve
      port.resolve=function(c)local j=resolve(c);j.target='CAT1';j.size=8;return j end
      port.safe=function()return nil,'CAPABILITY_UNAVAILABLE' end
      port.idle=function()return idle end
      package.loaded.ota_platform={default=function()return port end}
      local files={}
      local dp={size=function(p)return #(files[p] or '')end,
        truncate=function(p,n)files[p]=(files[p] or ''):sub(1,n);return true end,
        read=function(p,n,k)return files[p]:sub(n+1,n+k)end,
        write=function(p,n,s)files[p]=(files[p] or ''):sub(1,n)..s;return true end,
        http_get=function()return {status=206,headers={['Content-Range']='bytes 0-7/8',
          ['Content-Length']='8',ETag='"v1"'},body='abcdefgh'}end,
        verify_file=function(p,j)return {size=8,sha256=j.sha256,md5=j.md5,signature_valid=true}end}
      local function make()return R.new({store=newstore(),codec=json,download_port=dp})end
      local r=make();assert(r:accept(command));local j=r:status().job
      local function frame(op,phase,safe,epoch)
        return 'OTA_GR='..json.encode({op=op,phase=phase,reason='ok',commit_safe=safe,
          job=j.id,hash=j.hash,target=j.target,version=j.version,epoch=epoch or 1})
      end
      assert(r:on_gr_line(frame('GRANT','DOWNLOADING',true)));assert(r:tick())
      assert(r:on_gr_line(frame('STATUS','PREPARED',true)))
      assert(r:tick(),'fresh GR safety must permit ACTIVATE request')
      assert(r:status().phase=='WAIT_ACTIVATE' and activation==0)
      -- Reconcile PREPARED, then age the snapshot: refresh QUERY even with prepared_ack=true.
      assert(r:on_gr_line(frame('STATUS','PREPARED',true)));clock=4000
      assert(not r:tick());assert(sent[#sent].op=='QUERY' and activation==0)
      assert(not r:on_gr_line(frame('STATUS','PREPARED',true,2)));assert(not r:tick())
      assert(r:on_gr_line(frame('STATUS','PREPARED',false)));assert(not r:tick())
      assert(r:on_gr_line(frame('STATUS','PREPARED',true)));idle=false;assert(not r:tick())
      idle=true;assert(not r:tick(),'busy invalidates previous permission')
      assert(r:on_gr_line(frame('STATUS','PREPARED',true)));r:pause();assert(not r:tick())
      r=make();assert(not r:tick(),'restart must not recover safety from disk')
      assert(r:on_gr_line(frame('STATUS','PREPARED',true)));assert(r:tick())
      -- A status snapshot is not the one-shot installation grant.
      assert(not r:on_gr_line(frame('GRANT','INSTALL_PENDING',false)))
      assert(activation==0 and r:status().phase=='RECOVERY_HOLD')
    ''')
    # SAM | 2026-10-23 +08:00 | Verify actual boot construction and read-only filesystem units, without enabling an unverified native contract.
    check('singleton builds device options and rejects unknown filesystem or native contract', '''
      local idle=false
      package.loaded.business_runtime={ota_status=function()return {known=true,idle=idle}end}
      PRODUCT_VERSION='1.0.2';io.fsstat=function()return true,128,7,4096 end
      local opts=require('ota_device_options').new()
      assert(opts.bundle_port.current_version()=='1.0.2')
      assert(opts.bundle_port.free_bytes()==495616 and not opts.bundle_port.can_read())
      idle=true;assert(opts.bundle_port.can_read())
      io.fsstat=function()return true,128,129,4096 end;assert(opts.bundle_port.free_bytes()==nil)
      io.fsstat=function()return true,256,7,4096 end;assert(opts.bundle_port.free_bytes()==nil)
      assert(opts.http_native.native_rx_limit_verified==false)
      -- SAM | 2026-10-23 +08:00 | Boot must construct the native port while still refusing an unverified core contract; API discovery must have no side effects.
      assert(type(opts.native_fota_port)=='table','default native adapter missing')
      assert(opts.native_fota_port.native_contract_verified()==false)
      assert(opts.native_fota_port.require_code_identity==true)
      local captured;R.new=function(o)captured=o;return {} end
      local first=R.instance();assert(first==R.instance() and captured.bundle_port~=nil)
    ''')
    # SAM | 2026-10-23 +08:00 | Exercise the runtime construction path, not just a decoder injected by ZIP tests.
    check('runtime binds manifest decoder without overwriting explicit adapter', '''
      local captured
      package.loaded.ota_platform={bundle=function(bp,base)captured=bp;return port end,
        default=function()return port end}
      local bp={verify_manifest=function()return true end}
      R.new({store=newstore(),codec=json,bundle_port=bp})
      assert(captured.decode('{"schema":6}').schema==6 and bp.decode==nil)
      local custom=function()return {custom=true} end;bp.decode=custom
      R.new({store=newstore(),codec=json,bundle_port=bp});assert(captured.decode==custom)
    ''')
    # SAM | 2026-10-23 +08:00 | Optional native HTTP binding must not replace caller transports or weaken business gating.
    check('bounded HTTP binding requires explicit native contract and preserves bundle gates', '''
      local calls=0;local captured;local enabled=true
      package.loaded.ota_http_range={new=function(d)calls=calls+1;captured=d;return {http_get=function()end}end}
      local bp={verify_manifest=function()return true end,can_read=function()return enabled end}
      local deps={native_rx_limit_verified=true,can_read=function()return true end}
      R.new({store=newstore(),codec=json,port=port,bundle_port=bp,http_native=deps})
      assert(calls==1 and captured.can_read()==true and bp.http_get==nil)
      enabled=false;assert(captured.can_read()==false)
      assert(deps.can_read()==true,'caller dependencies mutated')
      bp.http_get=function()end
      R.new({store=newstore(),codec=json,port=port,bundle_port=bp,http_native=deps})
      assert(calls==1,'custom transport overwritten')
    ''')
    check('failed native HTTP binding blocks bundle open and candidate writes', '''
      local resolve=port.resolve
      port.resolve=function(c)local j=resolve(c);j.size=8
        j.bundle={md5=c.Md5:lower(),manifest_sha256=string.rep('e',64)};return j end
      local opened=0
      package.loaded.ota_bundle={open=function()opened=opened+1;error('must not open')end}
      local r=R.new({store=newstore(),codec=json,port=port,
        bundle_port={verify_manifest=function()return true end},http_native={}})
      assert(r:accept(command));local j=r:status().job
      assert(r:on_gr_line('OTA_GR='..json.encode({op='GRANT',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='DOWNLOADING'})))
      local ok,e=r:tick();assert(not ok and e=='HTTP_NATIVE_CONTRACT',tostring(e))
      assert(opened==0 and r:status().download==nil and activation==0)
    ''')
    # SAM | 2026-10-23 +08:00 | Native controller must be driven only after durable GR INSTALL_PENDING authority.
    check('runtime drives controlled native install without reporting success or replaying after reset', '''
      local resolve=port.resolve;local files={};local journal;local init=0;local finish=0
      port.resolve=function(c)local j=resolve(c);j.target='CAT1';j.size=8;return j end
      local dp={size=function(p)return #(files[p] or '')end,
        truncate=function(p,n)files[p]=(files[p] or ''):sub(1,n);return true end,
        read=function(p,n,k)return files[p]:sub(n+1,n+k)end,
        write=function(p,n,s)files[p]=(files[p] or ''):sub(1,n)..s;return true end,
        http_get=function()return {status=206,headers={['Content-Range']='bytes 0-7/8',
          ['Content-Length']='8',ETag='"v1"'},body='abcdefgh'}end,
        verify_file=function(p,j)return {size=8,sha256=j.sha256,md5=j.md5,signature_valid=true}end}
      local fp={load=function()return journal,true end,save=function(s)journal=clone(s);return true end,
        safe=function()return true end,owner=function(j,e)return e==1 end,
        verify=function(j,p)return files[p]=='abcdefgh' end,now=function()return 100 end,
        read=dp.read,native_contract_verified=function()return true end,
        native={init=function()init=init+1;return true end,wait=function()return true end,
          run=function(s)assert(s=='abcdefgh');return true,true,0 end,
          isDone=function()return true,true end,finish=function(ok)assert(ok);finish=finish+1;return true end}}
      -- SAM | 2026-10-23 +08:00 | Exercise runtime's real isolated native journal instead of an in-memory record callback.
      fp.load=nil;fp.save=nil
      require('ota_store').file_port=function()return disk end
      local function make()return R.new({store=newstore(),codec=json,port=port,download_port=dp,native_fota_port=fp})end
      local r=make();assert(r:accept(command));local j=r:status().job
      local function gr(op,phase)return r:on_gr_line('OTA_GR='..json.encode({op=op,phase=phase,
        job=j.id,target=j.target,hash=j.hash,version=j.version,epoch=1}))end
      assert(gr('GRANT','DOWNLOADING'));assert(r:tick());assert(init==0)
      assert(gr('STATUS','PREPARED'));assert(r:tick());assert(init==0)
      assert(gr('GRANT','INSTALL_PENDING'));assert(init==1 and activation==0)
      r:tick();r:tick();local journal=require('ota_native_store').new(disk,json).load()
      assert(finish==1 and journal.phase=='COMMITTED')
      assert(r:status().phase=='INSTALLING' and reboots==0)
      r=make();r:tick();assert(init==1 and finish==1 and reboots==0)
      -- SAM | 2026-10-23 +08:00 | Real runtime must confirm the isolated native journal before enqueuing the OTA result.
      port.health=function()return {version=j.version,healthy=true,installation_verified=true,data_ok=true}end
      assert(not r:tick());assert(r:status().phase=='INSTALLING')
      port.health=function()return {job=j.id,hash=j.hash,epoch=1,version=j.version,
        healthy=true,installation_verified=true,data_ok=true}end
      r=make();assert(r:tick());assert(r:status().phase=='COMPLETE_PENDING')
      journal=require('ota_native_store').new(disk,json).load()
      assert(journal.phase=='CONFIRMED' and journal.result.version==j.version)
      assert(init==1 and finish==1 and reboots==0)
      -- SAM | 2026-10-23 +08:00 | Power loss between native retirement and manager acknowledgement must not strand the next upgrade.
      assert(r:on_gr_line('OTA_GR='..json.encode({op='RELEASED',phase='COMPLETE',job=j.id,
        hash=j.hash,target=j.target,version=j.version,epoch=1,outcome='success'})))
      assert(r:status().native_release~=nil)
      local ok,why=r:accept(command);assert(not ok and why=='NATIVE_RELEASE_PENDING')
      local write=disk.write;local cut=true
      disk.write=function(path,raw)
        if cut and path:match('^/yp001_ota_state_') then cut=false;return false end
        return write(path,raw)
      end
      assert(not r:tick())
      journal=require('ota_native_store').new(disk,json).load();assert(journal.phase=='IDLE')
      r=make();assert(r:status().native_release~=nil);assert(r:tick())
      assert(r:status().native_release==nil and r:status().phase=='IDLE')
      port.resolve=function(c)local n=resolve(c);n.target='CAT1';n.size=8
        n.id=string.rep('d',64);n.hash=string.rep('e',64);return n end
      command.CurrentVersion=command.TargetVersion;command.TargetVersion='1.2.0'
      assert(r:accept(command));j=r:status().job
      assert(gr('GRANT','DOWNLOADING'));assert(r:tick())
      assert(gr('STATUS','PREPARED'));assert(r:tick());assert(gr('GRANT','INSTALL_PENDING'))
      assert(init==2 and finish==1 and reboots==0)
    ''')
    # SAM | 2026-10-23 +08:00 | A component build identity must not masquerade as confirmed whole-device OTA success.
    check('CAT1 identity distinguishes build from confirmed release without FOTA writes', '''
      VERSION='001.005.000';PRODUCT_VERSION='1.5.0';FW_RELEASE_BUILD=4;PROJECT='TK_PROJECT_OTA'
      local calls=0
      fota={init=function()calls=calls+1 end,finish=function()calls=calls+1 end}
      require('update')
      local text;_G.at_cmd_handlers.FW_VERSION('FW_VERSION',function(s)text=s end)
      local value=json.decode(text:sub(12))
      assert(value.component=='CAT1' and value.component_version==VERSION and value.product_build_version==PRODUCT_VERSION)
      assert(value.build==4 and value.release_confirmed==false and value.confirmed_product_version==nil)
      assert(calls==0 and reboots==0)
      VERSION=nil;PRODUCT_VERSION=nil;FW_RELEASE_BUILD=nil
      _G.at_cmd_handlers.FW_VERSION('FW_VERSION',function(s)text=s end)
      value=json.decode(text:sub(12));assert(value.component_version=='UNKNOWN' and not value.release_confirmed)
    ''')
    # SAM | 2026-10-20 19:28 +08:00 | Read storage counters only; unknown or malformed capacity must never be represented as usable bytes.
    check('OTA_SPACE validates counters and performs no file writes', '''
      require('update')
      local original=io
      local function query()
        local text;_G.at_cmd_handlers.OTA_SPACE('OTA_SPACE',function(s)text=s end)
        return json.decode(text:sub(11))
      end
      io={fsstat=function(path)assert(path=='/');return true,192,20,4096,'lfs' end}
      local s=query();assert(s.ok and s.total_bytes==786432 and s.used_bytes==81920 and s.free_bytes==704512)
      io.fsstat=function()return true,192,192,4096,'lfs' end
      s=query();assert(s.ok and s.free_bytes==0 and not s.install_enabled)
      for _,v in ipairs({-1,193,1.5,'20'}) do
        io.fsstat=function()return true,192,v,4096,'lfs' end
        s=query();assert(not s.ok and s.free_bytes==nil)
      end
      io.fsstat=function()error('private backend error')end
      s=query();assert(not s.ok and s.error=='FSSTAT_UNAVAILABLE')
      io.fsstat=function()return false,192,0,4096 end
      s=query();assert(not s.ok and s.free_bytes==nil)
      io={};s=query();assert(not s.ok and s.free_bytes==nil)
      io=original
      assert(reboots==0 and activation==0)
    ''')
    # SAM | 2026-10-20 18:20 +08:00 | Probe only function availability; no vendor FOTA API may execute during capability discovery.
    check('OTA_CAPS reports capabilities without initializing or writing FOTA', '''
      local calls=0
      local function forbidden() calls=calls+1;error('must not execute') end
      fota={init=forbidden,wait=forbidden,run=forbidden,file=forbidden,isDone=forbidden,finish=forbidden}
      fskv={get=forbidden,set=forbidden,clear=forbidden}
      socket={rx=forbidden};zbuff={create=forbidden};mcu={ticks=forbidden}
      require('update')
      local text
      _G.at_cmd_handlers.OTA_CAPS('OTA_CAPS',function(s)text=s end)
      local value=json.decode(text:sub(10))
      assert(value.fota_file and value.fota_init and value.fota_isDone and value.fota_finish)
      assert(value.kv_get and value.install_enabled==false)
      assert(value.socket_rx and value.zbuff_create and value.mcu_ticks and value.http_rx_limit_verified==false)
      assert(calls==0 and reboots==0 and activation==0)
      fota=nil;fskv=nil
      _G.at_cmd_handlers.OTA_CAPS('OTA_CAPS',function(s)text=s end)
      value=json.decode(text:sub(10))
      assert(not value.fota_file and not value.kv_get and calls==0)
      -- SAM | 2026-10-20 18:30 +08:00 | Native library representations must be reported before interpreting all-false capability output.
      fota=setmetatable({}, {__index=function() error('lookup unavailable') end})
      _G.at_cmd_handlers.OTA_CAPS('OTA_CAPS',function(s)text=s end)
      value=json.decode(text:sub(10))
      assert(value.module_types.fota=='table' and value.api_types.fota_file=='LOOKUP_ERROR')
      assert(calls==0 and reboots==0)
      -- SAM | 2026-10-20 19:26 +08:00 | Reproduce V2052 native userdata modules using an indexable host userdata without invoking upgrade APIs.
      local native=assert(io.tmpfile())
      local original=getmetatable(native)
      local members={init=forbidden,wait=forbidden,run=forbidden,file=forbidden,isDone=forbidden,finish=forbidden,get=forbidden,fsstat=forbidden}
      debug.setmetatable(native,{__index=members})
      fota=native;fskv=native
      _G.at_cmd_handlers.OTA_CAPS('OTA_CAPS',function(s)text=s end)
      value=json.decode(text:sub(10))
      assert(value.module_types.fota=='userdata' and value.fota_file and value.kv_get)
      assert(value.api_types.fota_file=='function' and calls==0 and reboots==0)
      debug.setmetatable(native,original);native:close()
    ''')
    check('default platform denies unknown release', '''
      local p=require('ota_platform').default()
      local r=R.new({store=newstore(),codec=json,port=p})
      assert(not r:accept(command));assert(r:status().phase=='IDLE');assert(activation==0)
      assert(not r:receive('test/down',command,{retain=false}))
    ''')
    check('receiver requires trusted topic and non-retained metadata but passes ordinary messages', '''
      local r=R.new({store=newstore(),codec=json,port=port});R.set_instance(r)
      port.accept_topic=function(topic)return topic=='test/down' end
      local receiver=require('mqtts_receiver')
      receiver.proc('wrong/down',json.encode(command),{retain=0});assert(r:status().phase=='IDLE')
      receiver.proc('test/down',json.encode(command),{retain=1});assert(r:status().phase=='IDLE')
      receiver.proc('test/down',json.encode(command),{});assert(r:status().phase=='IDLE')
      for _,name in ipairs(published)do assert(name~='RECV_DATA_FROM_SERVER')end
      receiver.proc('other','ordinary business',{});assert(published[#published]=='RECV_DATA_FROM_SERVER')
      receiver.proc('test/down',json.encode(command),{retain=false});assert(r:status().phase=='WAIT_GR')
    ''')
    check('runtime routes GR, excludes echo and validates bounded JSON', '''
      local r=R.new({store=newstore(),codec=json,port=port})
      assert(r:accept(command));local s=r:status()
      local msg={op='GRANT',job=s.job.id,hash=s.job.hash,target=s.job.target,version=s.job.version,epoch=1,phase='DOWNLOADING'}
      assert(r:on_gr_line('OTA_GR='..json.encode(msg)));assert(r:status().phase=='GR_GRANTED')
      assert(not r:on_gr_line('OTA_GR='..string.rep('x',2050)));assert(not r:reboot_allowed())
      R.set_instance(r);require('mqtts_receiver').proc('topic',json.encode(command),{})
      assert(r:status().phase=='GR_GRANTED')
      for _,name in ipairs(published) do assert(name~='RECV_DATA_FROM_SERVER') end
    ''')
    check('old FOTA and DFU entries cannot activate or delete', '''
      R.set_instance(R.new({store=newstore(),codec=json,port=port}))
      package.preload.libfota2=function() error('must not load native FOTA') end
      require('update');require('dfu_transfer')
      local function reply(s) replies[#replies+1]=s end
      for _,n in ipairs({'FOTA_CHECK','DFU_DL','DFU_START','DFU_ERASE','DFU_ABORT'}) do
        _G.at_cmd_handlers[n](n..'=https://example.invalid/fw',reply)
      end
      assert(reboots==0 and activation==0)
      for _,s in ipairs(replies)do assert(s:find('REJECTED')) end
    ''')
    check('watchdog rechecks ownership after delayed reset', '''
      -- SAM | 2026-10-14 21:09 +08:00 | This OTA guard test requires a live logical network; SIM absence is separately tested by test_sim_recovery.py.
      -- SAM | 2026-10-20 17:53 +08:00 | Keep a stable network generation and suspend at the actual grace wait so this test still checks OTA ownership changing before reset.
      package.loaded.netdrv_device={ip_ready=function() return true end,generation=function() return 1 end}
      local r=R.new({store=newstore(),codec=json,port=port});R.set_instance(r)
      local waits=0
      sys.waitUntil=function()
        waits=waits+1
        if waits>1 then coroutine.yield() end
        return false
      end
      sys.wait=function() coroutine.yield() end
      require('network_watchdog');local task=coroutine.create(tasks[1]);assert(coroutine.resume(task))
      assert(r:accept(command));assert(coroutine.resume(task));assert(reboots==0)
    ''')
    check('main manual reboot respects durable pending state', '''
      local r=R.new({store=newstore(),codec=json,port=port});R.set_instance(r);assert(r:accept(command))
      for _,name in ipairs({'audio_drv','gnss_app','uart_app','antenna_test','timer_app','network_watchdog',
        'netdrv_device','update','ntp','mqtts_main','mqtts_sender','mqtts_receiver','sip','tts','dfu_transfer'}) do
        package.loaded[name]=true
      end
      -- SAM | 2026-10-14 21:09 +08:00 | Mock the observer's new read-only interface while retaining the actual main/OTA reboot protection assertion.
      package.loaded.netdrv_device={ip_ready=function()return false end,status=function()return "UNKNOWN" end}
      -- SAM | 2026-10-24 +08:00 | main now consumes SIP's read-only lifecycle export; preserve the real pending-OTA reboot assertion.
      package.loaded.sip={ota_status=function()return {state='STATE_IDLE',task_running=false}end}
      pm={lastReson=function()end,power=function()end};mcu={hardfault=function()end}
      sys.run=function()end;rtos.meminfo=function()return 1,0,0 end
      require('main');local response
      _G.at_cmd_handlers.ATREBOOT('ATREBOOT',function(s)response=s end)
      assert(response:find('REJECTED'));assert(reboots==0)
    ''')
    check('main restores journal before a failing first business module', '''
      local restored=false
      package.loaded.ota_runtime={instance=function()restored=true;return {}end}
      package.preload.audio_drv=function()assert(restored,'journal not restored first');error('business init failure')end
      local ok=pcall(require,'main');assert(not ok and restored);assert(activation==0)
    ''')
    check('outbox requires mapped topic and confirmed single-flight callback', '''
      local r=R.new({store=newstore(),codec=json,port=port})
      assert(not r:accept({MsgType='otaMsg'}));assert(#r:status().outbox==1)
      assert(not r:flush_outbox());local queued={}
      port.outbox_topic=function()return 'test/up' end
      sys.publish=function(event,tag,topic,payload,qos,cb)
        assert(event=='SEND_DATA_REQ' and qos==1);queued[#queued+1]=cb
      end
      assert(r:flush_outbox());assert(not r:flush_outbox());assert(#queued==1)
      queued[1].func(false,queued[1].para);assert(#r:status().outbox==1)
      assert(r:flush_outbox());queued[1].func(true,queued[1].para)
      assert(#r:status().outbox==1,'stale callback cleared current flight')
      queued[2].func(true,queued[2].para);assert(#r:status().outbox==0)
    ''')
    check('corrupt journal direct outbox flush fails closed', '''
      local broken={load=function()return {schema=99},'STORE_CORRUPT'end,save=function()error('must not write')end}
      local r=R.new({store=broken,codec=json,port=port})
      local ok,result=pcall(r.flush_outbox,r);assert(ok and result==false)
    ''')
    check('network retries remain bounded with real downloader across runtime restart', '''
      local resolve=port.resolve;local now=1000;local calls=0
      port.resolve=function(c)local j=resolve(c);j.size=8;j.target='CAT1';return j end
      port.now=function()return now end
      local dp={size=function()return 0 end,truncate=function()return true end,
        read=function()return ''end,write=function()error('network failure must not write')end,
        http_get=function()calls=calls+1;return nil end}
      local function make()return R.new({store=newstore(),codec=json,port=port,download_port=dp})end
      local r=make();assert(r:accept(command));local j=r:status().job
      assert(r:on_gr_line('OTA_GR='..json.encode({op='GRANT',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='DOWNLOADING'})))
      assert(not r:tick());assert(calls==1)
      r=make();assert(not r:tick());assert(calls==1)
      now=0;r=make();assert(not r:tick());assert(calls==1)
      local function recover()
        r=make();assert(not r:tick())
        assert(r:on_gr_line('OTA_GR='..json.encode({op='STATUS',job=j.id,hash=j.hash,
          target=j.target,version=j.version,epoch=1,phase='DOWNLOADING'})))
      end
      now=1030;recover();assert(not r:tick());assert(calls==2)
      now=1090;recover();assert(not r:tick());assert(calls==3)
      now=2000;recover();assert(not r:tick());assert(calls==3)
    ''')
    check('real download engine journals each chunk and resumes across runtime restart', '''
      local resolve=port.resolve
      port.resolve=function(c)local j=resolve(c);j.size=8;j.target='CAT1';return j end
      local files={};local data='abcdefgh';local calls=0
      local dp={chunk_size=4,max_size=1024,
        size=function(p)return files[p] and #files[p] or 0 end,
        truncate=function(p,n)files[p]=(files[p] or ''):sub(1,n);return true end,
        write=function(p,n,s)files[p]=(files[p] or ''):sub(1,n)..s;return true end,
        read=function(p,n,k)return files[p]:sub(n+1,n+k)end,
        http_get=function(url,h,limit)
          calls=calls+1;local a,b=h.Range:match('bytes=(%d+)%-(%d+)');a=tonumber(a);b=tonumber(b)
          if calls>1 then assert(h['If-Range']=='"v1"')end
          return {status=206,headers={['Content-Range']='bytes '..a..'-'..b..'/8',
            ['Content-Length']='4',ETag='"v1"'},body=data:sub(a+1,b+1)}
        end,
        verify_file=function(p,j)return {size=#files[p],md5=j.md5,sha256=j.sha256,signature_valid=true}end}
      local function make()return R.new({store=newstore(),codec=json,port=port,download_port=dp})end
      local r=make();assert(r:accept(command));local j=r:status().job
      assert(r:on_gr_line('OTA_GR='..json.encode({op='GRANT',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='DOWNLOADING'})))
      assert(not r:tick());assert(r:status().download.offset==4)
      r=make();assert(not r:tick());assert(calls==1 and r:status().download.offset==4)
      assert(r:on_gr_line('OTA_GR='..json.encode({op='STATUS',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='DOWNLOADING'})))
      assert(r:tick());assert(r:status().download.offset==8 and r:status().phase=='PREPARED')
      -- Drop first PREPARED request, then drop its reply: QUERY must recover either peer phase.
      local before=#sent
      r=make();assert(not r:tick());assert(r:status().phase=='PREPARED')
      local queried=false
      for i=before+1,#sent do if sent[i].op=='QUERY' then queried=true end end
      assert(queried,'lost PREPARED has no query recovery')
      assert(r:on_gr_line('OTA_GR='..json.encode({op='STATUS',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='DOWNLOADING'})))
      assert(sent[#sent].op=='PREPARED')
      -- GR has advanced, but drop its STATUS. Repeated PREPARED gets phase-invalid DENY.
      r:on_gr_line('OTA_GR='..json.encode({op='DENY',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='PREPARED',reason='phase_invalid'}))
      before=#sent
      for i=1,5 do assert(not r:tick()) end
      queried=false
      for i=before+1,#sent do if sent[i].op=='QUERY' then queried=true end end
      assert(queried,'lost STATUS has no bounded query recovery')
      assert(r:on_gr_line('OTA_GR='..json.encode({op='STATUS',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='PREPARED'})))
      assert(r:tick());assert(r:status().phase=='WAIT_ACTIVATE')
      assert(r:on_gr_line('OTA_GR='..json.encode({op='GRANT',job=j.id,hash=j.hash,
        target=j.target,version=j.version,epoch=1,phase='INSTALL_PENDING'})))
      assert(activation==1 and calls==2)
    ''')

    # SAM | 2026-10-23 +08:00 | Real runtime prepare must use OTA2 staging, not merely test an uncalled sender.
    check('runtime drives actual GR sender and withholds PREPARED until VERIFY ACK', r'''
      local resolve=port.resolve
      port.resolve=function(c)local j=resolve(c);j.size=5000;return j end
      port.stage_gr=function()error('legacy stage path called')end
      local files={};local wire=require('ota_wire');local r;local accepted,durable=0,0
      local dp={chunk_size=5000,size=function(p)return #(files[p] or '')end,
        truncate=function(p,n)files[p]=(files[p] or ''):sub(1,n);return true end,
        read=function(p,o,n)return files[p]:sub(o+1,o+n)end,
        write=function(p,o,v)files[p]=(files[p] or ''):sub(1,o)..v;return true end,
        http_get=function()return {status=206,headers={['Content-Range']='bytes 0-4999/5000',
          ['Content-Length']='5000',ETag='"v1"'},body=string.rep('x',5000)}end,
        verify_file=function(p,j)return {size=#files[p],md5=j.md5,sha256=j.sha256,signature_valid=true}end}
      local gp={now=function()return 0 end,idle=function()return true end,read=dp.read,
        send=function(raw)
          local f=assert(wire.decode(raw));local kind,payload
          -- SAM | 2026-10-26 +08:00 | The real sender now requires physical TX completion; this injected synchronous UART must report it before the peer ACK.
          assert(r:on_tx_sent(f))
          if f.type==1 then kind=2;payload=string.pack('<I2I2I4I4I4',512,4096,442368,0,1)
          else
            kind=128
            if f.type==4 then accepted=accepted+#f.payload;if accepted==5000 or accepted%4096==0 then durable=accepted end end
            if f.type==6 then assert(durable==5000) end
            payload=string.pack('<BBI2I4I4I4',f.type,0,f.type==6 and 3 or 1,accepted,durable,5000)
          end
          assert(r:on_wire_frame(wire.decode(wire.encode(kind,f.session,f.sequence,f.offset,payload))))
          return true
        end}
      r=R.new({store=newstore(),codec=json,port=port,download_port=dp,gr_transfer_port=gp})
      assert(r:accept(command));local j=r:status().job
      assert(r:on_gr_line('OTA_GR='..json.encode({op='GRANT',job=j.id,hash=j.hash,target=j.target,
        version=j.version,epoch=1,phase='DOWNLOADING'})))
      assert(not r:tick());assert(r:status().phase=='PAUSED' and activation==0);assert(r:status().reason=='DOWNLOAD_PENDING', tostring(r:status().reason))
      for i=1,30 do r:pump_gr() end
      assert(r:tick());assert(r:status().phase=='PREPARED' and accepted==5000 and activation==0)
    ''')
