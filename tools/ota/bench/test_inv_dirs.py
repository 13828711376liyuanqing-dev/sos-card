# Host check: ota_data_inventory.capture skips only /log and /ble directories; other directories still fail.
import sys, hashlib
sys.path.insert(0, r'D:/CODEX/sos-card/logs/cat1_antenna_20261010/python_deps')
from lupa import lua54 as lupa

src = sys.argv[1].replace('\\', '/')
L = lupa.LuaRuntime(unpack_returned_tuples=True)
g = L.globals()
g.SRC = src
L.execute("package.path = SRC .. '/?.lua;' .. package.path")
g.py_sha = lambda s: hashlib.sha256(s if isinstance(s, bytes) else s.encode('latin-1')).hexdigest()
M = L.execute(open(src + '/ota_data_inventory.lua', encoding='utf-8').read())
mk = L.eval('''function(entries, files, M)
 local io_={lsdir=function(d,n,o) return true, entries end,
  open=function(p,m) local data=files[p]; if not data then return nil end; local pos=0
   return {seek=function(self,w,o) if w=='end' then pos=#data else pos=o or 0 end; return pos end,
     read=function(self,n) local s=data:sub(pos+1,pos+n); pos=pos+#s; return s end, close=function() return true end} end}
 local kv={status=function() return 0,65536,0 end, iter=function() return {} end, next=function() return nil end}
 local h={hash_begin=function() return {b={}} end, hash_update=function(c,s) c.b[#c.b+1]=s; return true end,
   hash_finish=function(c) return py_sha(table.concat(c.b)) end}
 return M.capture({io=io_,kv=kv,hash=h,can_read=function() return true end})
end''')


def T(rows, files):
    return mk(L.table_from([L.table_from(r) for r in rows]), L.table_from(files), M)


def n(t):
    return len(list(t.values())) if t else 0


ok = T([{'name': 'luadb', 'type': 1, 'size': 0}, {'name': 'log', 'type': 1, 'size': 787},
        {'name': 'ble', 'type': 1, 'size': 202649800}, {'name': 'yp001_business_0', 'type': 0, 'size': 3}],
       {'/yp001_business_0': 'abc'})
assert ok['complete'] is True and n(ok['files']) == 1, ('dirs', ok['error'], ok['stage'])
bad = T([{'name': 'log', 'type': 1, 'size': 0}, {'name': 'user', 'type': 1, 'size': 0}], {})
assert bad['complete'] is False and bad['error'] == 'DIRECTORY_UNVERIFIED', ('unknown dir', bad['error'])
plain = T([{'name': 'log', 'type': 0, 'size': 3}], {'/log': 'xyz'})
assert plain['complete'] is True and n(plain['files']) == 1, ('plain log file', plain['error'])
a = T([{'name': 'hxxt.dat', 'type': 0, 'size': 3}, {'name': 'hxxt_tm', 'type': 0, 'size': 2},
       {'name': 'yp001_business_0', 'type': 0, 'size': 3}], {'/hxxt.dat': 'aaa', '/hxxt_tm': '11', '/yp001_business_0': 'abc'})
b = T([{'name': 'hxxt.dat', 'type': 0, 'size': 4}, {'name': 'hxxt_tm', 'type': 0, 'size': 2},
       {'name': 'yp001_business_0', 'type': 0, 'size': 3}], {'/hxxt.dat': 'bbbb', '/hxxt_tm': '22', '/yp001_business_0': 'abc'})
assert a['complete'] is True and n(a['files']) == 1 and a['digest'] == b['digest'], ('gnss cache', a['error'])
c = T([{'name': 'yp001_business_0', 'type': 0, 'size': 3}], {'/yp001_business_0': 'abd'})
assert c['digest'] != a['digest'], 'user data change must still change the digest'
print('PASS /log and /ble dirs skipped; other dirs -> DIRECTORY_UNVERIFIED; plain files still hashed; GNSS caches ignored, user data still tracked')
