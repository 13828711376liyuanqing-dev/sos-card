"""SAM | 2026-10-29 08:06 +08:00 | Host-test the CAT1 receiver root listing against the device V2052 lsdir pagination bug (offset skip counts
'.'/'..', so page 2 overlaps page 1; device locator o=16,i=1,d=true). The single bounded listing must complete a full read-only audit
of 21 root files on that model, fail closed with FILE_LIMIT on a possibly truncated full page, keep FILE_LIST_FAILED for a failed list or an
over-long name, and its locator carries no names, sizes or contents. No device access.
Usage: python test_file_list_diag.py <receiver source dir>"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua54 import LuaRuntime

# V2052-like root: 21 entries; skipping `o` entries also consumes '.' and '..', so the returned window starts 2 early.
V2052 = '''local names={};for i=1,21 do names[i]='f'..i end
api.lsdir=function(p,n,o)local t={};local s=o==0 and 0 or o-2;for i=s+1,math.min(#names,s+math.min(n,100)) do t[#t+1]={name=names[i],type=0,size=1} end;return true,t end'''
FULL = '''api.lsdir=function(p,n,o)local t={};for i=1,math.min(n,100) do t[i]={name='f'..i,type=0,size=1} end;return true,t end'''
FAIL_CASES = {
    'full_page': (FULL, 'FILE_LIMIT', "d.n==100"),
    'long_name': ('''api.lsdir=function(p,n,o)return true,{{name=string.rep('x',200),type=0,size=1}}end''', 'FILE_LIST_FAILED', "d.i==1 and d.l==200 and d.d==false"),
    'list_failed': ('''api.lsdir=function(p,n,o)return false,'ERR'end''', 'FILE_LIST_FAILED', "d.n==-1 and d.k==false and d.i==nil"),
}
PORT = '''api.open=function(path,mode)local pos=0;return {seek=function(_,how,n)if how=='end' then return 1 end;pos=n;return n end,
 read=function(_,n)return ('x'):rep(n)end,close=function()return true end}end
kv={status=function()return 0,1024,0 end,iter=function()return {} end,next=function()return nil end,get=function()return nil end}
hash={hash_begin=function()return {s=''}end,hash_update=function(c,s)c.s=c.s..s;return true end,hash_finish=function(c)return string.rep('a',64)end}
port={io=api,kv=kv,hash=hash,can_read=function()return true end}'''


def run(source, body):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(f"package.path='{source}/?.lua;'..package.path;mod=require('ota_data_inventory');api={{}}")
    lua.execute(body)


def main():
    source = Path(sys.argv[1]).resolve().as_posix()
    run(source, V2052 + '\n' + PORT + '''
local r=mod.capture(port);assert(r.complete==true and #r.files==21,'V2052_ROOT_NOT_AUDITED '..tostring(r.error)..' '..tostring(r.stage))
local seen={};for _,f in ipairs(r.files) do assert(not seen[f.path],'DUP');seen[f.path]=true end
''')
    for name, (lsdir, error, expect) in FAIL_CASES.items():
        run(source, lsdir + '\n' + PORT + f'''
local r=mod.capture(port);assert(r.complete==false and r.stage=='FILE_LIST' and r.error=='{error}','NOT_FAIL_CLOSED_{name} '..tostring(r.error))
d=mod.ld;assert(d and ({expect}),'LOCATOR_{name}');for k,v in pairs(d) do assert(type(v)~='string','LOCATOR_EXPORTS_TEXT '..k) end
''')
    print('PASS root listing: V2052 overlapping-pagination model audited completely (21 files, no duplicates); full page FILE_LIMIT; '
          'failed list / over-long name FILE_LIST_FAILED; locator has no names/sizes/contents')


if __name__ == '__main__':
    main()
