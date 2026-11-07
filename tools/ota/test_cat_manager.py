# SAM | 2026-10-24 +08:00 | Fixtures use explicit installation evidence; legacy pending flags are rejected separately.
"""SAM | 2026-10-12 19:41 +08:00 | Execute Lua transaction invariants without device writes."""
from pathlib import Path
import json
import sys,os
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua54 import LuaRuntime, lua_type


def runtime():
    lua = LuaRuntime(unpack_returned_tuples=True)
    def native(x):
        if lua_type(x) == 'table':
            keys = list(x.keys())
            if keys and all(isinstance(k, int) for k in keys) and set(keys) == set(range(1,len(keys)+1)):
                return [native(x[i]) for i in range(1,len(keys)+1)]
            return {str(k):native(x[k]) for k in keys}
        return x
    def table(x):
        if isinstance(x, dict): return lua.table_from({k:table(v) for k,v in x.items()})
        if isinstance(x, list): return lua.table_from([table(v) for v in x])
        return x
    lua.globals().py_encode = lambda x: json.dumps(native(x), separators=(',',':'),sort_keys=True)
    lua.globals().py_decode = lambda x: table(json.loads(x))
    lua.globals().root = ROOT.as_posix()
    lua.execute('''
      package.path=root..'/Air780EGH/?.lua;'..package.path
      json={encode=function(t)return py_encode(t)end,decode=function(s)return py_decode(s)end}
      fs={}; fail_write=false; sent={}; activation=0
      disk={read=function(p)return fs[p], fs[p] and nil or 'missing'end,
        write=function(p,s) if fail_write then fs[p]=s:sub(1,9);return false end fs[p]=s;return true end}
      function clone(t)return json.decode(json.encode(t))end
      function newstore()return require('ota_store').new(disk,json)end
      command={MsgType='otaMsg',CurrentVersion='1.0.0',TargetVersion='1.1.0',
        Address='https://example.invalid/gr.pkg',Md5=string.rep('a',32),Time=1}
      port={resolve=function(c)return {id=string.rep('b',64),hash=string.rep('c',64),target='GR5526',
        version=c.TargetVersion,source=c.CurrentVersion,url=c.Address,md5=c.Md5}end,
        validate=function()return true end,compare=function()return 1 end,
        send_gr=function(m)table.insert(sent,clone(m));return true end,
        idle=function()return true end,safe=function()return true end,
        prepare=function()return true end,verify_candidate=function()return true end,
        activate=function()activation=activation+1;return true end,now=function()return 123 end}
      function newmanager()return require('ota_manager').new(newstore(),port,json)end
      function reply(m,op,phase,epoch)
        local j=m:status().job
        return {op=op,job=j.id,target=j.target,hash=j.hash,epoch=epoch or 1,phase=phase,version=j.version}
      end
    ''')
    # SAM | 2026-10-29 19:52 +08:00 | Run the generic manager suites against any receiver source tree (round-2 OTA refactor regression).
    if os.environ.get('OTA_SOURCE_DIR'):
        lua.execute("package.path=.....'/?.lua;'..package.path", Path(os.environ['OTA_SOURCE_DIR']).as_posix())
    if os.environ.get('OTA_RELEASE_VARIANT'):
        source=ROOT/'logs/uart_window_20261025/capacity_preview'/os.environ['OTA_RELEASE_VARIANT']/'source'
        lua.execute("package.path=.....'/?.lua;'..package.path",source.as_posix())
    return lua


def check(name, script):
    lua=runtime();lua.execute(script);print('PASS',name)


if __name__ == '__main__':
    # SAM | 2026-10-23 +08:00 | Whole-archive proof must survive reset but cannot replace current GR ownership.
    check('archive proof uses durable release journal and fresh matching ownership', '''
      local resolve=port.resolve;local manifest=string.rep('d',64)
      port.resolve=function(c)local j=resolve(c);j.bundle={md5=c.Md5,manifest_sha256=manifest};return j end
      local m=newmanager();assert(m:accept(command))
      assert(not m:owns_bundle(manifest));assert(not m:save_archive_proof(command.Md5,1000,'"v1"',manifest))
      assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:owns_component('GR5526',1,manifest));assert(not m:owns_component('CAT1',1,manifest))
      assert(m:save_archive_proof(command.Md5,1000,'"v1"',manifest))
      assert(m:archive_verified(command.Md5,1000,'"v1"',manifest))
      m=newmanager();assert(not m:owns_bundle(manifest))
      assert(not m:archive_verified(command.Md5,1000,'"v1"',manifest))
      assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')))
      assert(m:archive_verified(command.Md5,1000,'"v1"',manifest))
      assert(not m:archive_verified(command.Md5,1001,'"v1"',manifest))
      assert(not m:archive_verified(command.Md5,1000,'"v2"',manifest))
      assert(not m:save_archive_proof(string.rep('e',32),1000,'"v1"',manifest))
      fail_write=true;assert(not m:save_archive_proof(command.Md5,1000,'"v2"',manifest))
      assert(not m:owns_bundle(manifest))
    ''')
    # SAM | 2026-10-23 +08:00 | A persisted PREPARED acknowledgement cannot activate before checking the current GR state.
    check('recovered prepared state cannot request activation from stale acknowledgement', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')))
      m=newmanager();local ok,why=m:request_activation()
      assert(not ok and why=='GR_RECONCILE_REQUIRED' and sent[#sent].op=='QUERY')
      local bad=reply(m,'STATUS','PREPARED',2);assert(not m:on_gr(bad))
      assert(not m:request_activation());assert(activation==0)
      assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
      assert(sent[#sent].op=='ACTIVATE' and activation==0)
    ''')
    # SAM | 2026-10-23 +08:00 | A durable old grant is not a fresh peer reply after reboot.
    check('recovered download waits for matching GR status and resumes interrupted prepare', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      local calls=0;port.prepare=function()calls=calls+1;return false,'DOWNLOAD_PENDING' end
      m=newmanager();local ok,why=m:prepare();assert(not ok and why=='GR_RECONCILE_REQUIRED')
      assert(calls==0 and sent[#sent].op=='QUERY')
      local bad=reply(m,'STATUS','DOWNLOADING',2);assert(not m:on_gr(bad))
      bad=reply(m,'STATUS','DOWNLOADING');bad.version='9.9.9';assert(not m:on_gr(bad))
      assert(not m:prepare() and calls==0)
      assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')));assert(not m:prepare());assert(calls==1)
      local saved=m:status();saved.phase='PREPARING';assert(newstore():save(saved))
      m=newmanager();assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')))
      assert(m:status().phase=='PAUSED');assert(not m:prepare());assert(calls==2)
    ''')
    # SAM | 2026-10-23 20:02 +08:00 | Continuation failure must retain one platform acknowledgement and a reboot-stable retry budget.
    check('bundle continuation retry budget survives restart without duplicate platform replies', '''
      local original=port.resolve
      port.resolve=function(c)local j=original(c);j.bundle={md5=c.Md5,manifest_sha256=string.rep('d',64)};return j end
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
      local r=reply(m,'STATUS','COMPLETE');r.outcome='success';assert(m:on_gr(r))
      local c=m:pending_cleanup();assert(m:reserve_cleanup(c.target,c.hash));assert(m:cleanup_done(c.target,c.hash))
      local calls=0;local clock=100
      port.now=function()return clock end
      port.resolve=function()calls=calls+1;return nil,'network_error' end
      assert(not m:accept(m:next_command()));assert(calls==1)
      m=newmanager();local ok,why=m:accept(m:next_command());assert(not ok and why=='RETRY_BACKOFF' and calls==1)
      clock=131;assert(not m:accept(m:next_command()));assert(calls==2)
      m=newmanager();clock=192;assert(not m:accept(m:next_command()));assert(calls==3)
      m=newmanager();clock=999;ok,why=m:accept(m:next_command());assert(not ok and why=='FAILED_HASH_LIMIT' and calls==3)
      assert(#m:status().outbox==1 and m:status().release.gr_done)
    ''')
    check('GR bundle failure stops the sequence and reports one whole-release failure', '''
      local original=port.resolve
      port.resolve=function(c)local j=original(c);j.bundle={md5=c.Md5,manifest_sha256=string.rep('d',64)};return j end
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
      local r=reply(m,'STATUS','COMPLETE');r.outcome='fail';r.version=command.CurrentVersion;assert(m:on_gr(r))
      m=newmanager();assert(not m:component_complete('GR5526',string.rep('d',64)) and m:next_command()==nil)
      assert(#m:status().outbox==2 and m:status().outbox[2].payload.Status=='fail')
      local c=m:pending_cleanup();fail_write=true;assert(not m:reserve_cleanup(c.target,c.hash))
      assert(m:status().error,'uncertain cleanup reservation must block deletion')
    ''')
    check('yielding release resolution cannot accept a concurrent task', '''
      local original=port.resolve;local m;local calls=0
      port.resolve=function(c)
        calls=calls+1;local ok,why=m:accept(c);assert(not ok and why=='BUSY')
        return original(c)
      end
      m=newmanager();assert(m:accept(command));assert(calls==1 and m:status().phase=='WAIT_GR')
    ''')
    # SAM | 2026-10-23 19:56 +08:00 | Reproduce loss of the whole-bundle sequence after GR releases its owner.
    check('bundle GR result survives restart and cleanup precedes CAT continuation', '''
      local original=port.resolve;local m
      port.resolve=function(c)
        local j=original(c);j.bundle={md5=c.Md5,manifest_sha256=string.rep('d',64)}
        j.md5=c.Md5;j.size=5000
        if m and m:component_complete('GR5526',j.bundle.manifest_sha256) then
          j.target='CAT1';j.id=string.rep('e',64);j.hash=string.rep('f',64)
        end
        return j
      end
      m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
      local r=reply(m,'STATUS','COMPLETE');r.outcome='success';assert(m:on_gr(r))
      m=newmanager();assert(m:component_complete('GR5526',string.rep('d',64)))
      assert(#m:status().outbox==1,'GR alone cannot report whole-bundle success')
      assert(not m:component_complete('GR5526',string.rep('a',64)))
      assert(m:next_command()==nil,'CAT must wait for GR candidate cleanup')
      local c=m:pending_cleanup();assert(c.target=='GR5526' and c.hash==string.rep('c',64))
      assert(not m:cleanup_done('GR5526',string.rep('0',64)))
      assert(m:reserve_cleanup(c.target,c.hash));assert(m:cleanup_done(c.target,c.hash));m=newmanager()
      assert(m:next_command().TargetVersion==command.TargetVersion)
      local other=clone(command);other.Md5=string.rep('0',32);assert(not m:accept(other))
      assert(m:accept(m:next_command()));assert(m:status().job.target=='CAT1')
      assert(m:on_gr(reply(m,'GRANT','DOWNLOADING',2)))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED',2)));assert(m:request_activation())
      assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING',2)))
      assert(m:finish({version='1.1.0',healthy=true,installation_verified=true,data_ok=true}))
      r=reply(m,'RELEASED','COMPLETE',2);r.outcome='success';assert(m:on_gr(r))
      assert(m:component_complete('CAT1',string.rep('d',64)))
      assert(m:next_command()==nil and #m:status().outbox==2)
    ''')
    # SAM | 2026-10-23 19:26 +08:00 | GR confirms its own signed running version; CAT must persist this result even if the reset lost GRANT.
    check('GR durable completion after lost activation reply and duplicate result', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
      local r=reply(m,'STATUS','COMPLETE');r.outcome='success'
      local bad=clone(r);bad.version='9.9.9';assert(not m:on_gr(bad))
      bad=clone(r);bad.epoch=2;assert(not m:on_gr(bad))
      assert(m:on_gr(r));assert(m:status().phase=='IDLE');assert(activation==0)
      assert(#m:status().outbox==2 and m:status().outbox[2].payload.Status=='success')
      assert(not m:on_gr(r));assert(#newmanager():status().outbox==2)
    ''')
    check('store readback, corruption, no silent reset', '''
      local a=newstore();assert(a:load()==nil);assert(a:save({schema=1,value=12}))
      local b=newstore();assert(b:load().value==12)
      fail_write=true;assert(not b:save({schema=1,value=13}))
      local c=newstore();local state,err=c:load();assert(not state and err)
      assert(not c:save({schema=1,value=0}), 'corrupt store silently reset')
    ''')
    check('persistent grant before reply and no parallel target', '''
      local m=newmanager();assert(m:accept(command));assert(#m:status().outbox==0)
      assert(sent[1].op=='REQUEST');local wrong=reply(m,'GRANT','DOWNLOADING');wrong.hash=string.rep('d',64)
      assert(not m:on_gr(wrong));assert(m:status().phase=='WAIT_GR')
      assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')));assert(m:status().outbox[1].payload.otaReply=='success')
      local n=newmanager();assert(n:status().epoch==1);assert(not n:accept(command))
      assert(activation==0)
    ''')
    check('failed persistence cannot authorize activity', '''
      local m=newmanager();fail_write=true;assert(not m:accept(command));assert(#sent==0 and activation==0)
    ''')
    check('safe prepare, epoch fence, explicit activation and QoS1 outbox', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      port.idle=function()return false end;assert(not m:prepare());assert(activation==0)
      port.idle=function()return true end;assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:status().phase=='PREPARED')
      port.safe=function()return false end;assert(not m:request_activation());assert(activation==0)
      port.safe=function()return true end;assert(m:request_activation())
      assert(not m:on_gr(reply(m,'GRANT','INSTALL_PENDING',2)));assert(activation==0)
      assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING')));assert(activation==1)
      assert(not m:on_gr(reply(m,'GRANT','INSTALL_PENDING')));assert(activation==1)
      local n=newmanager();assert(activation==1);assert(n:status().phase=='INSTALLING')
      assert(not n:finish({version='1.1.0',healthy=true,installation_verified=false,data_ok=true}))
      assert(n:finish({version='1.1.0',healthy=true,installation_verified=true,data_ok=true}))
      assert(n:status().phase=='COMPLETE_PENDING');local q=reply(n,'RELEASED','COMPLETE');q.outcome='success'
      assert(n:on_gr(q));assert(n:status().phase=='IDLE')
      assert(#n:status().outbox==2);local id=n:status().outbox[1].id
      assert(not n:ack(id,false));assert(#n:status().outbox==2)
      assert(n:ack(id,true));assert(#n:status().outbox==1)
      assert(newmanager():status().outbox[1].payload.Status=='success')
    ''')
    check('grant cannot override changed business conditions', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation());port.safe=function()return false end
      assert(not m:on_gr(reply(m,'GRANT','INSTALL_PENDING')));assert(activation==0)
      assert(m:status().phase=='RECOVERY_HOLD')
    ''')
    check('malformed command, unmapped target, data compatibility reject', '''
      local m=newmanager();local c=clone(command);c.Md5='abc';assert(not m:accept(c))
      port.resolve=function()return nil,'RELEASE_MAPPING_UNAVAILABLE'end
      assert(not m:accept(command));assert(#sent==0 and activation==0)
    ''')
    check('malformed persisted fields fail closed without effects', '''
      for _,field in ipairs({'epoch','outbox','failures','next_id'}) do
        fs={};local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
        local s=m:status();s[field]=field=='epoch' and 0 or 'bad'
        local st=newstore();st:load();assert(st:save(s));local n=newmanager()
        assert(n:status().error);assert(not n:prepare());assert(not n:reboot_allowed());assert(activation==0)
      end
    ''')
    check('lost grant reconciles STATUS but never activates on STATUS', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')))
      assert(m:status().phase=='GR_GRANTED');assert(#m:status().outbox==1)
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
      assert(m:on_gr(reply(m,'STATUS','INSTALL_PENDING')));assert(m:status().phase=='RECOVERY_HOLD');assert(activation==0)
    ''')
    check('rollback COMPLETE carries actual source version and outcome', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      assert(m:prepare());assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation());assert(m:on_gr(reply(m,'GRANT','INSTALL_PENDING')))
      assert(m:finish({version='1.0.0',healthy=true,installation_verified=true,data_ok=true}))
      assert(sent[#sent].op=='COMPLETE' and sent[#sent].version=='1.0.0' and sent[#sent].outcome=='fail')
      local r=reply(m,'RELEASED','COMPLETE');r.version='1.0.0';r.outcome='fail';assert(m:on_gr(r));assert(m:status().phase=='IDLE')
    ''')
    check('store rejects non-table before durable mutation', '''
      local a=newstore();assert(a:load()==nil);assert(not a:save('bad'));assert(next(fs)==nil)
    ''')
    check('PREPARED acknowledgement and lost-grant query gate', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'DENY','DOWNLOADING',0)))
      assert(sent[#sent].op=='QUERY');assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')))
      assert(m:prepare());assert(not m:request_activation());assert(activation==0)
      assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')));assert(sent[#sent].op=='PREPARED')
      assert(m:on_gr(reply(m,'STATUS','PREPARED')));assert(m:request_activation())
      assert(m:on_gr(reply(m,'STATUS','INSTALL_PENDING')));assert(activation==0)
    ''')
    check('download checkpoints scoped to job, monotonic, durable and phase fenced', '''
      local base=port.resolve;port.resolve=function(c)local j=base(c);j.size=20000;return j end
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      local d={sha256=string.rep('c',64),md5=string.rep('a',32),size=20000,
        path='/ota_candidate_'..string.rep('c',64)..'.part',offset=10,etag='"etag1"'}
      assert(not m:save_download(d))
      port.prepare=function()
        local bad=clone(d);bad.path='/user_settings';assert(not m:save_download(bad))
        bad=clone(d);bad.offset=20001;assert(not m:save_download(bad))
        bad=clone(d);bad.sha256=string.rep('d',64);assert(not m:save_download(bad))
        assert(m:save_download(d));bad=clone(d);bad.offset=9;assert(not m:save_download(bad))
        bad=clone(d);bad.etag='"other"';assert(not m:save_download(bad))
        bad=clone(d);bad.offset=17000;assert(not m:save_download(bad))
        return false,'DOWNLOAD_PENDING'
      end
      assert(not m:prepare());assert(m:status().phase=='PAUSED')
      local n=newmanager();assert(n:status().download.offset==10);assert(n:status().download.path==d.path)
      assert(n:on_gr(reply(n,'STATUS','DOWNLOADING')))
      port.prepare=function()d.offset=20;assert(n:save_download(d));return false,'DOWNLOAD_PENDING'end
      assert(not n:prepare());assert(newmanager():status().download.offset==20)
    ''')
    check('download failed commit never acknowledges bytes', '''
      local base=port.resolve;port.resolve=function(c)local j=base(c);j.size=100;return j end
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      port.prepare=function()
        fail_write=true;assert(not m:save_download({sha256=string.rep('c',64),md5=string.rep('a',32),size=100,
          path='/ota_candidate_'..string.rep('c',64)..'.part',offset=1,etag='"v1"'}));return false
      end
      assert(not m:prepare());assert(m:status().error);assert(activation==0)
    ''')
    check('file port treats close failure as failed durability', '''
      io.exists=function()return false end
      io.open=function()return {write=function()return true end,close=function()return nil,'disk_full'end}end
      assert(require('ota_store').file_port().write('/yp001_ota_state_0','x')==false)
    ''')
    check('corrupt outbox ids and failure counts never reach ports', '''
      for _,bad in ipairs({{outbox={[2]={id=1,payload={MsgType='otaReplyMsg',otaReply='success',Time=1}}}},
        {failures={[string.rep('c',64)]='3'}},{next_id=0},{outbox={{id=2,payload={MsgType='otaReplyMsg',otaReply='success',Time=1}}}}}) do
        fs={};local m=newmanager();local state=m:status();for k,v in pairs(bad)do state[k]=v end
        local st=newstore();st:load();assert(st:save(state));local n=newmanager();assert(n:status().error);assert(not n:accept(command));assert(activation==0)
      end
    ''')
    check('download retry count and backoff persist across reboots', '''
      local clock=100;port.now=function()return clock end
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      local attempts=0;port.prepare=function()attempts=attempts+1;return false,'network_error'end
      assert(not m:prepare());assert(attempts==1)
      m=newmanager();assert(not m:prepare());assert(attempts==1)
      assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')))
      clock=131;assert(not m:prepare());assert(attempts==2)
      m=newmanager();assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')));clock=192;assert(not m:prepare());assert(attempts==3)
      m=newmanager();assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')));clock=999;assert(not m:prepare());assert(attempts==3)
    ''')
    check('bad package permanent hold survives reboot and unknown clock blocks retry', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      local attempts=0;port.prepare=function()attempts=attempts+1;return false,'entity_changed'end
      assert(not m:prepare());m=newmanager();assert(not m:prepare());assert(attempts==1)
      fs={};m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      port.now=function()return nil end;port.prepare=function()attempts=attempts+1;return false,'network_error'end
      assert(not m:prepare());m=newmanager();assert(not m:prepare());assert(attempts==2)
    ''')
    check('power cut during prepare consumes persisted attempt reservation', '''
      local clock=100;port.now=function()return clock end
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      local saved,attempts;attempts=0
      port.prepare=function()attempts=attempts+1;saved=clone(fs);return false,'network_error'end
      for i=1,3 do
        assert(not m:prepare());fs=clone(saved);m=newmanager();assert(m:status().phase=='PAUSED')
        assert(m:on_gr(reply(m,'STATUS','DOWNLOADING')))
        assert(m:status().retries[string.rep('c',64)].count==i);clock=clock+121
      end
      assert(not m:prepare());assert(attempts==3)
    ''')
    check('ordinary chunk progress and business pauses do not consume retry budget', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      for _,reason in ipairs({'DOWNLOAD_PENDING','paused','BUSINESS_BUSY_OR_UNKNOWN'})do
        port.prepare=function()return false,reason end
        for i=1,5 do assert(not m:prepare());assert(next(m:status().retries)==nil) end
      end
    ''')
    check('yielding prepare cannot overwrite a concurrent recovery hold', '''
      local m=newmanager();assert(m:accept(command));assert(m:on_gr(reply(m,'GRANT','DOWNLOADING')))
      port.prepare=function()assert(m:on_gr(reply(m,'STATUS','INSTALL_PENDING')));return true end
      assert(not m:prepare());assert(m:status().phase=='RECOVERY_HOLD');assert(activation==0)
    ''')
