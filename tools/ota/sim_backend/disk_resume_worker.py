"""SAM | 2026-10-21 +08:00 | Test-only fresh process disk recovery; public key only, never device access."""
import json
from pathlib import Path
import sys
import os
from types import SimpleNamespace
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/ota'))
import test_disk_download

if __name__=='__main__':
    config_path=Path(sys.argv[1]).resolve()
    allowed=(ROOT/'logs/ota_disk_tests').resolve()
    if not config_path.is_relative_to(allowed):raise ValueError('test workspace only')
    config=json.loads(config_path.read_text(encoding='utf-8'))
    obj=test_disk_download.Tests(methodName='test_binary_resume_new_runtime')
    obj.folder=Path(config['folder']).resolve()
    if not obj.folder.is_relative_to(allowed):raise ValueError('test workspace only')
    obj.image=bytes(range(256))*100
    obj.url=config['url']
    if not obj.url.startswith('http://127.0.0.1:'):raise ValueError('loopback only')
    obj.manifest=config['manifest']
    public=Ed25519PublicKey.from_public_bytes(bytes.fromhex(config['public']))
    obj.key=SimpleNamespace(public_key=lambda:public)
    obj.checkpoint=obj.folder/'checkpoint.json'
    obj.fail_checkpoint=obj.disconnect=obj.wrong_entity=False
    lua=obj.runtime()
    if config.get('exit_before_checkpoint') is True:
        # SAM | 2026-10-21 +08:00 | Exit without cleanup after fsynced candidate append and a rejected checkpoint.
        obj.fail_checkpoint=True
        lua.execute('assert(not d:step())')
        os._exit(73)
    lua.execute("assert(d:status().offset==4096);while d:status().state=='DOWNLOADING' do assert(d:step()) end;assert(d:verify())")
    print('PASS independent process disk resume and public-key signature validation')
