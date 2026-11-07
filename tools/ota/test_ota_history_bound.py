"""SAM | 2026-11-04 +08:00 | Multi-OTA journal growth (1.5.11 fix in ota_manager.lua): a completed release clears its own
retries/failures and every non-permanent retry; both maps stay capped at 8; 50 consecutive whole-device releases keep the
journal size flat (the pre-fix manager grows it every release). Host only, manager-level states; not board evidence.
Usage: python test_ota_history_bound.py [--old <manager source dir before the fix>]"""
import sys
from pathlib import Path
from test_cat_manager import runtime

HELPERS = r'''
local function h(c,i) return (string.rep(c,62)..string.format('%02x',i % 256)) end
function make_release(k, extra_retries, extra_failures, cat_phase)
  local M,G,C,J=h('a',k),h('b',k),h('c',k),h('d',k)
  local MD5=string.rep('e',30)..string.format('%02x',k % 256)
  local src,dst='1.5.'..(k+9),'1.5.'..(k+10)
  local url='http://example.invalid/r'..k..'.zip'
  local s={schema=1,phase='COMPLETE_PENDING',outbox={},next_id=1,failures=extra_failures or {},retries=extra_retries or {},epoch=5,
    release={manifest=M,command={MsgType='otaMsg',CurrentVersion=src,TargetVersion=dst,Address=url,Md5=MD5,Time=1},
      gr_hash=G,cat_hash=C,gr_finished=true,gr_done=true,gr_cleaned=true,cat_finished=false,cat_done=false,cat_cleaned=false},
    job={id=J,hash=C,target='CAT1',version=dst,source=src,url=url,md5=string.rep('f',32),size=1000,bundle={md5=MD5,manifest_sha256=M}},
    result={version=dst,success=true}}
  -- what a release leaves behind on the device: the manifest-level retry made at accept
  s.retries[M]={count=1,next_retry=1000+k,permanent=false}
  return s
end
function complete(s)
  assert(newstore():save(s))
  local m=newmanager();assert(not m:status().error,'state rejected '..tostring(m:status().error))
  local j=s.job
  local ok,why=m:on_gr({op='STATUS',phase='COMPLETE',outcome='success',version=j.version,job=j.id,hash=j.hash,target=j.target,epoch=s.epoch})
  assert(ok,'complete refused '..tostring(why))
  local st=m:status();assert(st.phase=='IDLE' and st.release.cat_done==true,'not complete')
  return st
end
function count(t) local n=0;for _ in pairs(t) do n=n+1 end;return n end
function journal_bytes() local n=0;for _,p in ipairs({'/yp001_ota_state_0','/yp001_ota_state_1'}) do n=math.max(n,#(fs[p] or '')) end;return n end
'''


def check(name, body, src=None):
    if src:
        import os
        os.environ['OTA_SOURCE_DIR'] = str(src)
    lua = runtime()
    lua.execute(HELPERS + body)
    print('PASS', name)


def main():
    old = None
    if len(sys.argv) > 2 and sys.argv[1] == '--old':
        old = Path(sys.argv[2]).resolve()
    if old is None:
        check('completed release clears its own entries and every non-permanent retry; permanent ones stay', r'''
local old={}
for i=1,9 do old[string.rep('9',62)..string.format('%02x',i)]={count=2,next_retry=500+i,permanent=false} end
for i=1,3 do old[string.rep('8',62)..string.format('%02x',i)]={count=3,next_retry=400+i,permanent=true} end
local s=make_release(1,old,{[string.rep('b',62)..'01']=1})
local st=complete(s)
assert(count(st.retries)==3,'retries '..count(st.retries))
for k,v in pairs(st.retries) do assert(v.permanent and k:sub(1,1)=='8') end
assert(st.retries[s.release.manifest]==nil and st.failures[s.release.gr_hash]==nil)
''')
        check('failure counts stay capped at 8 and keep the job in hand', r'''
local f={}
for i=1,12 do f[string.rep('7',62)..string.format('%02x',i)]=1 end
local s=make_release(2,{},f)
s.result={version=s.job.source,success=false}
assert(newstore():save(s));local m=newmanager();assert(not m:status().error)
-- a failed CAT1 result goes through finish() in the device; here: the failure branch of finish via INSTALLING
s.phase='INSTALLING';s.result=nil;assert(newstore():save(s));m=newmanager();assert(not m:status().error,tostring(m:status().error))
local ok=m:finish({healthy=true,installation_verified=true,data_ok=true,version=s.job.source})
assert(ok)
local st=m:status();assert(count(st.failures)==8,'failures '..count(st.failures));assert(st.failures[s.job.hash]==1)
''')
    body = r'''
local carry_r,carry_f,sizes={}, {}, {}
for k=1,50 do
  local s=make_release(k,carry_r,carry_f)
  local st=complete(s)
  carry_r,carry_f=st.retries,st.failures
  sizes[k]=journal_bytes()
end
GROW=sizes[50]-sizes[2]
print('journal bytes after release 2/10/50:',sizes[2],sizes[10],sizes[50])
'''
    if old is None:
        check('50 consecutive whole-device releases: journal size stays flat', body + "assert(GROW<=4,'journal grew '..GROW)")
    else:
        check('pre-fix manager: the same 50 releases grow the journal (proves the test sees the bug)', body + "assert(GROW>3000,'expected growth, got '..GROW)", old)


if __name__ == '__main__':
    main()
