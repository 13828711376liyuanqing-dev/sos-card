"""SAM | 2026-10-21 +08:00 | Disk checkpoints, binary payloads and independent Lua runtime recovery over real HTTP."""
import hashlib
import base64
import json
import os
from pathlib import Path
import sys
import threading
import unittest
import urllib.request
import uuid
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'logs/cat1_antenna_20261010/python_deps'))
from lupa.lua54 import LuaRuntime, LuaError
from sim_backend.package_http import PackageServer
from sim_backend.signed_manifest import create, verify, new_key

class Tests(unittest.TestCase):
    # SAM | 2026-10-21 +08:00 | Persisted corruption must fail closed without silently resetting user or candidate files.
    def test_corrupt_checkpoint_keeps_files(self):
        lua=self.runtime();lua.execute('assert(d:step())')
        before=(self.folder/'candidate.part').read_bytes()
        self.checkpoint.write_bytes(b'{"offset":4096,broken')
        with self.assertRaises(json.JSONDecodeError):self.runtime()
        self.assertEqual((self.folder/'candidate.part').read_bytes(),before)

    def test_short_candidate_cannot_resume(self):
        lua=self.runtime();lua.execute('assert(d:step())')
        candidate=self.folder/'candidate.part';candidate.write_bytes(b'short')
        checkpoint=self.checkpoint.read_bytes()
        with self.assertRaisesRegex(LuaError,'candidate_missing_or_short'):self.runtime()
        self.assertEqual(candidate.read_bytes(),b'short')
        self.assertEqual(self.checkpoint.read_bytes(),checkpoint)

    def test_wrong_checkpoint_identity_keeps_candidate(self):
        lua=self.runtime();lua.execute('assert(d:step())')
        p=self.folder/'candidate.part';before=p.read_bytes()
        saved=json.loads(self.checkpoint.read_text());saved['sha256']='0'*64
        self.checkpoint.write_text(json.dumps(saved),encoding='utf-8')
        with self.assertRaisesRegex(LuaError,'invalid_checkpoint'):self.runtime()
        self.assertEqual(p.read_bytes(),before)

    def test_replaced_trust_key_rejects_complete_file(self):
        lua=self.runtime();lua.execute("while d:status().state=='DOWNLOADING' do assert(d:step())end")
        self.key=new_key()
        lua.execute("assert(not d:verify());assert(d:status().state~='VERIFIED')")

    def test_same_length_corrupt_prefix_rejected_after_resume(self):
        lua=self.runtime();lua.execute('assert(d:step())')
        p=self.folder/'candidate.part';raw=p.read_bytes();p.write_bytes(b'X'+raw[1:])
        lua=self.runtime()
        lua.execute("while d:status().state=='DOWNLOADING' do assert(d:step())end;assert(not d:verify())")

    def test_process_exit_before_checkpoint(self):
        self.test_independent_process_resume()

    def test_independent_process_resume(self):
        # SAM | 2026-10-21 +08:00 | Fresh Python/Lua process must recover using disk state, without transferring private keys.
        from cryptography.hazmat.primitives import serialization
        lua=self.runtime();lua.execute('assert(d:step())');del lua
        public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        config=dict(folder=str(self.folder),url=self.url,manifest=self.manifest,public=public.hex())
        config_path=self.folder/'worker.json';config_path.write_text(json.dumps(config),encoding='utf-8')
        if self._testMethodName=='test_process_exit_before_checkpoint':
            config['exit_before_checkpoint']=True
            config_path.write_text(json.dumps(config),encoding='utf-8')
            crash=subprocess.run([sys.executable,str(ROOT/'tools/ota/sim_backend/disk_resume_worker.py'),str(config_path)],
                cwd=ROOT,capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.assertEqual(crash.returncode,73,crash.stdout+crash.stderr)
            self.assertEqual((self.folder/'candidate.part').stat().st_size,8192)
            self.assertEqual(json.loads(self.checkpoint.read_text())['offset'],4096)
            config.pop('exit_before_checkpoint');config_path.write_text(json.dumps(config),encoding='utf-8')
        result=subprocess.run([sys.executable,str(ROOT/'tools/ota/sim_backend/disk_resume_worker.py'),str(config_path)],
                              cwd=ROOT,capture_output=True,text=True,timeout=30,
                              creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual((self.folder/'candidate.part').read_bytes(),self.image)

    def setUp(self):
        self.folder=ROOT/'logs/ota_disk_tests'/uuid.uuid4().hex
        self.folder.mkdir(parents=True)
        self.user=self.folder/'user.json'
        self.user.write_bytes(b'latest legitimate user data')
        self.image=bytes(range(256))*100
        self.key=new_key()
        self.manifest=create(self.key,self.image,'GR5526','TEST_N','TEST_N_PLUS_1')
        self.server=PackageServer(self.image)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}/packages/{self.server.digest}'
        self.checkpoint=self.folder/'checkpoint.json'
        self.fail_checkpoint=False
        self.disconnect=False
        self.wrong_entity=False

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)
        self.assertEqual(self.user.read_bytes(),b'latest legitimate user data')

    def path(self,name):
        expected='/o'+base64.b32encode(hashlib.sha256(self.image).digest()).decode().lower().rstrip('=')+'.p'
        if name!=expected: raise ValueError('non-candidate path')
        return self.folder/'candidate.part'

    def runtime(self):
        # Latin-1 is a reversible byte bridge, including NUL and 0x80..0xff.
        lua=LuaRuntime(unpack_returned_tuples=True,encoding='latin-1')
        def table(d): return lua.table_from(d)
        def size(n):
            p=self.path(n);return p.stat().st_size if p.exists() else 0
        def truncate(n,k):
            p=self.path(n)
            with p.open('r+b' if p.exists() else 'w+b') as f:
                f.truncate(k);f.flush();os.fsync(f.fileno())
            return True
        def write(n,k,data):
            p=self.path(n)
            with p.open('r+b' if p.exists() else 'w+b') as f:
                f.seek(k);f.write(data.encode('latin-1'));f.flush();os.fsync(f.fileno())
            return True
        def read(n,k,count):
            with self.path(n).open('rb') as f:
                f.seek(k);return f.read(count).decode('latin-1')
        def checkpoint(record):
            if self.fail_checkpoint:return False
            data=json.dumps(dict(record.items())).encode()
            pending=self.folder/'checkpoint.tmp'
            with pending.open('wb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            os.replace(pending,self.checkpoint)
            return json.loads(self.checkpoint.read_text())==dict(record.items())
        def http(url,headers,limit):
            if self.disconnect:raise ConnectionResetError('injected transport interruption')
            hdr=dict(headers.items())
            if self.wrong_entity:hdr['If-Range']='"different"'
            with urllib.request.urlopen(urllib.request.Request(url,headers=hdr),timeout=3) as r:
                body=r.read(limit+1)
                if len(body)>limit:return None
                return table(dict(status=r.status,headers=table(dict(r.headers.items())),body=body.decode('latin-1')))
        def verify_file(n,j):
            raw=self.path(n).read_bytes()
            return table(dict(size=len(raw),md5=hashlib.md5(raw).hexdigest(),sha256=hashlib.sha256(raw).hexdigest(),signature_valid=verify(self.key.public_key(),raw,self.manifest)))
        ports=dict(size=size,truncate=truncate,write=write,read=read,checkpoint=checkpoint,http_get=http,verify_file=verify_file)
        for name,fn in ports.items():lua.globals()['py_'+name]=fn
        lua.globals().root=ROOT.as_posix()
        lua.globals().job=table(dict(url=self.url,size=len(self.image),sha256=hashlib.sha256(self.image).hexdigest(),md5=hashlib.md5(self.image).hexdigest()))
        saved=json.loads(self.checkpoint.read_text()) if self.checkpoint.exists() else None
        lua.globals().saved=table(saved) if saved else None
        lua.execute('''package.path=root..'/Air780EGH/?.lua;'..package.path
        local p={chunk_size=4096}
        for _,name in ipairs({'size','truncate','write','read','checkpoint','http_get','verify_file'})do
          local fn=_G['py_'..name];p[name]=function(...)return fn(...)end
        end
        d=require('ota_download').new(p)
        local ok,why=d:start(job,saved);assert(ok,why)''')
        return lua

    def test_binary_resume_new_runtime(self):
        lua=self.runtime();lua.execute('assert(d:step())')
        self.assertEqual(json.loads(self.checkpoint.read_text())['offset'],4096)
        del lua
        lua=self.runtime()
        lua.execute("assert(d:status().offset==4096);while d:status().state=='DOWNLOADING' do assert(d:step())end;assert(d:verify())")
        self.assertEqual((self.folder/'candidate.part').read_bytes(),self.image)

    def test_failed_checkpoint_truncates_unacknowledged_bytes(self):
        lua=self.runtime();lua.execute('assert(d:step())')
        self.fail_checkpoint=True;lua.execute('assert(not d:step())')
        self.assertEqual((self.folder/'candidate.part').stat().st_size,8192)
        self.fail_checkpoint=False;lua=self.runtime()
        self.assertEqual((self.folder/'candidate.part').stat().st_size,4096)
        lua.execute("while d:status().state=='DOWNLOADING' do assert(d:step())end;assert(d:verify())")

    def test_disconnect_and_changed_entity_do_not_append(self):
        lua=self.runtime();lua.execute('assert(d:step())')
        before=(self.folder/'candidate.part').read_bytes()
        self.disconnect=True;lua.execute('assert(not d:step())')
        self.disconnect=False;self.wrong_entity=True;lua=self.runtime();lua.execute('assert(not d:step())')
        self.assertEqual((self.folder/'candidate.part').read_bytes(),before)
        self.assertEqual(json.loads(self.checkpoint.read_text())['offset'],4096)

    def test_disk_tamper_rejects_signature(self):
        lua=self.runtime();lua.execute("while d:status().state=='DOWNLOADING' do assert(d:step())end")
        p=self.folder/'candidate.part';raw=p.read_bytes();p.write_bytes(b'X'+raw[1:])
        lua.execute("assert(not d:verify());assert(d:status().state~='VERIFIED')")

if __name__=='__main__':unittest.main()
