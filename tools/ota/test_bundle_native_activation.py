"""SAM | 2026-10-23 +08:00 | Production manager/runtime/native transitions with explicit host bundle/vendor fixtures; no device acceptance."""
from test_runtime import check
from test_default_native_path import SETUP

SEED = '''
local original=port.resolve
port.resolve=function(c)local j=original(c);j.bundle={md5=c.Md5,manifest_sha256=string.rep('d',64)};j.md5=c.Md5;j.size=5000;return j end
local seed=newmanager();assert(seed:accept(command));assert(seed:on_gr(reply(seed,'GRANT','DOWNLOADING')))
assert(seed:prepare());assert(seed:on_gr(reply(seed,'STATUS','PREPARED')));assert(seed:request_activation())
local done=reply(seed,'STATUS','COMPLETE');done.outcome='success';assert(seed:on_gr(done))
local cleanup=seed:pending_cleanup();assert(seed:reserve_cleanup(cleanup.target,cleanup.hash));assert(seed:cleanup_done(cleanup.target,cleanup.hash))
'''

FIXTURE = '''
-- Only parsing/crypto/IO are fixtures here; manager phases, proof sender and installer are production code.
package.loaded.ota_platform.bundle=function(_,base)return base end
local manifest=string.rep('d',64);local verification_phases={};local corrupt=false
local rawverify=dp.verify_file
dp.verify_file=function(path,expected)
 verification_phases[#verification_phases+1]=current:status().phase
 local result=rawverify(path,expected);if corrupt then result.sha256=string.rep('0',64) end;return result
end
local bp={verify_manifest=function()return true end}
package.loaded.ota_bundle={open=function()
 local c={sha256=string.rep('c',64),md5=command.Md5,size=5000}
 return {summary=function()return {manifest_sha256=manifest,device_installable=true}end,
 component=function()return c end,preflight_step=function()return true,'VERIFIED'end,
 cat_proof=function()return string.rep('ab',904)end,
 component_port=function(_,target,epoch,base)
  local p={};for k,v in pairs(base)do p[k]=v end
  p.verify_file=function(...)
   local phase=current:status().phase
   assert(phase~='ACTIVATION_ISSUED' and phase~='INSTALLING','download verifier used after activation')
   return base.verify_file(...)
  end
  return p
 end}
end}
local function make()return R.new({store=newstore(),codec=json,download_port=dp,native_fota_port=np,bundle_port=bp})end
current=make();local r=current;assert(r:accept(command));local j=r:status().job
local function frame(op,phase,safe,offset)
 return 'OTA_GR='..json.encode({op=op,phase=phase,reason='ok',commit_safe=safe,offset=offset,
 job=j.id,hash=j.hash,target=j.target,version=j.version,epoch=1})
end
assert(r:on_gr_line(frame('GRANT','DOWNLOADING',false)))
for i=1,8 do
 r:tick();local last=sent[#sent]
 if last.op=='CAT_PROOF' then assert(r:on_gr_line(frame('PROOF_ACK','DOWNLOADING',false,last.offset+#last.data/2))) end
 if r:status().phase=='PREPARED' then break end
end
assert(r:status().phase=='PREPARED')
assert(r:on_gr_line(frame('STATUS','PREPARED',true)));assert(r:tick())
'''

prefix = SETUP.split('local function make()')[0]
check('bundle activation rehashes candidate without download authority', SEED + prefix + FIXTURE + '''
assert(r:on_gr_line(frame('GRANT','INSTALL_PENDING',true)))
assert(initialized==1 and r:status().phase=='INSTALLING')
assert(verification_phases[#verification_phases]=='ACTIVATION_ISSUED')
''')
check('bundle changed candidate refuses native init', SEED + prefix + FIXTURE + '''
corrupt=true;r:on_gr_line(frame('GRANT','INSTALL_PENDING',true))
assert(initialized==0 and finished==0 and reboots==0)
''')

check('GR lost volatile proof resends metadata before activation', SEED + prefix +
      FIXTURE.replace("assert(r:on_gr_line(frame('STATUS','PREPARED',true)));assert(r:tick())", '') + '''
local lost=json.decode(frame('STATUS','PREPARED',true):sub(8));lost.cat_proof_ready=false
assert(r:on_gr_line('OTA_GR='..json.encode(lost)))
local begin=#sent
for i=1,4 do
 r:tick();local last=sent[#sent];assert(last.op=='CAT_PROOF')
 assert(last.offset==(i-1)*256);assert(initialized==0)
 assert(r:on_gr_line(frame('PROOF_ACK','PREPARED',false,last.offset+#last.data/2)))
end
assert(#sent==begin+4 and r:status().phase=='PREPARED')
assert(r:on_gr_line(frame('STATUS','PREPARED',true)));assert(r:tick())
assert(r:on_gr_line(frame('GRANT','INSTALL_PENDING',true)))
assert(initialized==1)
''')
