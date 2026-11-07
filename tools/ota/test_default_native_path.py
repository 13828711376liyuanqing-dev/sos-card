"""SAM | 2026-10-23 +08:00 | Host integration of production GR gates/native wiring; simulated vendor responses are not V2052 acceptance."""
from test_runtime import check

SETUP = '''
local clock=1000;local idle=true;mcu={ticks=function()return clock end}
local resolve=port.resolve
port.resolve=function(c)local j=resolve(c);j.target='CAT1';j.size=5000;return j end
port.safe=function()return nil end;port.idle=function()return idle end
local real_platform=require('ota_platform')
package.loaded.ota_platform={default=function()return port end,bundle=real_platform.bundle}
local files={};local native_disk;local initialized=0;local finished=0;local canceled=0;local written=0
local dp={size=function(p)return #(files[p] or '')end,
 truncate=function(p,n)files[p]=(files[p] or ''):sub(1,n);return true end,
 read=function(p,n,k)return files[p]:sub(n+1,n+k)end,
 write=function(p,n,s)files[p]=(files[p] or ''):sub(1,n)..s;return true end,
 http_get=function(url,h)local a,b=h.Range:match('bytes=(%d+)%-(%d+)');a=tonumber(a);b=tonumber(b)
   return {status=206,headers={['Content-Range']='bytes '..a..'-'..b..'/5000',
    ['Content-Length']=tostring(b-a+1),ETag='"v1"'},body=string.rep('x',b-a+1)}end,
 verify_file=function(p,j)return {size=5000,sha256=j.sha256,md5=j.md5,signature_valid=true}end}
local np={load=function()return native_disk,true end,save=function(s)native_disk=clone(s);return true end,
 now=function()return clock/1000 end,native_contract_verified=function()return true end,
 native={init=function()initialized=initialized+1;return true end,wait=function()return true end,
  run=function(data)written=written+#data;return true,written==5000,0 end,
  isDone=function()return true,true end,
  finish=function(ok)if ok then finished=finished+1 else canceled=canceled+1 end;return true end}}
-- No options.port: use the production safety, file binding, owner and reset callbacks.
-- Only vendor IO/contract and file/hash responses are host fixtures, never release evidence.
local function make()return R.new({store=newstore(),codec=json,download_port=dp,native_fota_port=np})end
local r=make();assert(r:accept(command));local j=r:status().job
local function frame(op,phase,safe,ticket)
 return 'OTA_GR='..json.encode({op=op,phase=phase,reason='ok',commit_safe=safe,ticket=ticket,
  job=j.id,hash=j.hash,target=j.target,version=j.version,epoch=1})
end
assert(r:on_gr_line(frame('GRANT','DOWNLOADING',false)));r:tick();assert(r:tick())
assert(r:on_gr_line(frame('STATUS','PREPARED',true)));assert(r:tick())
assert(r:on_gr_line(frame('GRANT','INSTALL_PENDING',true)))
assert(initialized==1 and r:status().phase=='INSTALLING')
'''

if __name__ == '__main__':
    # SAM | 2026-10-23 +08:00 | Exercise the production offline scanner binding after reset; code match still cannot fabricate business/vendor/data success.
    check('default recovered native path verifies files offline before asking for health', SETUP + '''
      assert(r:tick());assert(r:tick());assert(r:tick());assert(native_disk.phase=='COMMITTED')
      native_disk.job.bundle={manifest_sha256=string.rep('d',64)}
      native_disk.code_identity_required=true
      native_disk.expected_identity={file_count=1,files={['main.luac']=string.rep('e',64)},version=j.version,
        package_sha256=j.hash,manifest_sha256=string.rep('d',64),build_record_sha256=string.rep('f',64)}
      local reads=0;local health_calls=0;local digest=string.rep('e',64)
      local bp={verify_manifest=function()return false end,
        http_get=function()error('recovery must be offline')end,
        hash_begin=function()return {}end,hash_update=function()return true end,hash_finish=function()return digest end}
      io={lsdir=function(path,n,off)
        assert(path=='/luadb/');return true,{{name='main.luac',type=0},{name='.airm2m_all_crc#.bin',type=0}}
      end,open=function(path,mode)
        assert(mode=='rb');reads=reads+1;local size=path=='/luadb/main.luac' and 1 or 16
        return {seek=function(_,how,n)return how=='end' and size or n end,
          read=function(_,n)return string.rep('x',n)end,close=function()return true end}
      end}
      port.health=function()health_calls=health_calls+1;return nil end
      local function recover()return R.new({store=newstore(),codec=json,bundle_port=bp,download_port=dp,native_fota_port=np})end
      r=recover();local ok,why=r:tick();assert(not ok and why=='BOOT_IDENTITY_CHECKING');assert(health_calls==0)
      assert(r:status().native_code_identity=='BOOT_IDENTITY_CHECKING')
      r:tick();assert(reads==2 and health_calls==1 and native_disk.phase=='COMMITTED')
      assert(r:status().native_code_identity=='VERIFIED')
      assert(initialized==1 and finished==1 and reboots==0)
      digest=string.rep('0',64);r=recover();r:tick();ok,why=r:tick()
      assert(not ok and why=='BOOT_CODE_MISMATCH' and health_calls==1)
      assert(r:status().native_code_identity=='BOOT_CODE_MISMATCH')
    ''')
    check('default native path refreshes GR permission, commits and resets exactly once', SETUP + '''
      assert(r:tick());clock=3000
      assert(r:on_gr_line(frame('STATUS','INSTALL_PENDING',true)));assert(r:tick());clock=5000
      assert(r:on_gr_line(frame('STATUS','INSTALL_PENDING',true)));assert(r:tick())
      assert(finished==1 and canceled==0 and native_disk.phase=='COMMITTED' and reboots==0)
      assert(not r:on_gr_line(frame('REBOOT_GRANT','INSTALL_PENDING',true,1)))
      assert(r:tick());local ticket=sent[#sent].ticket;assert(sent[#sent].op=='REBOOT')
      assert(not r:on_gr_line(frame('REBOOT_GRANT','INSTALL_PENDING',true,ticket+1)))
      assert(not r:on_gr_line(frame('REBOOT_GRANT','INSTALL_PENDING',false,ticket)))
      assert(reboots==0);clock=8000
      assert(not r:on_gr_line(frame('REBOOT_GRANT','INSTALL_PENDING',true,ticket)))
      assert(r:tick());ticket=sent[#sent].ticket
      assert(r:on_gr_line(frame('REBOOT_GRANT','INSTALL_PENDING',true,ticket)))
      assert(reboots==1 and native_disk.phase=='REBOOTING')
      assert(not r:on_gr_line(frame('REBOOT_GRANT','INSTALL_PENDING',true,ticket)))
      r=make();r:tick();assert(reboots==1 and initialized==1 and finished==1)
    ''')
    check('lost GR safety aborts native writes without commit or reboot', SETUP + '''
      assert(r:tick());clock=4000
      assert(not r:tick());assert(canceled==1 and finished==0 and reboots==0)
      assert(native_disk.phase=='HOLD');r=make();r:tick();assert(initialized==1)
    ''')
    check('GR unsafe refresh aborts even before lease expires', SETUP + '''
      assert(r:on_gr_line(frame('STATUS','INSTALL_PENDING',false)))
      assert(not r:tick());assert(canceled==1 and finished==0 and reboots==0)
    ''')
    check('late safe status cannot revoke an explicit business pause', SETUP + '''
      r:pause();assert(r:on_gr_line(frame('STATUS','INSTALL_PENDING',true)))
      assert(not r:tick());assert(canceled==1 and finished==0 and reboots==0)
    ''')
