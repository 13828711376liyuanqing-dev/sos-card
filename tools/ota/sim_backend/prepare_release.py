"""SAM | 2026-10-21 +08:00 | Archive real firmware for TEST_ONLY transport/signature checks, never chip installation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
from cryptography.hazmat.primitives import serialization

if __package__:
    from .signed_manifest import create, verify, new_key
else:
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from sim_backend.signed_manifest import create, verify, new_key

ROOT=Path(__file__).resolve().parents[3]
LIMIT=16*1024*1024

def prepare(source,target,source_version,version,directory):
    source=Path(source).resolve()
    with source.open('rb') as stream:data=stream.read(LIMIT+1)
    if not 0<len(data)<=LIMIT:raise ValueError('empty or oversized firmware')
    key=new_key()
    manifest=create(key,data,target,source_version,version)
    directory=Path(directory).resolve()
    # No reuse/overwrite: an interrupted archive has no READY report and is never silently repaired.
    directory.mkdir(parents=True,exist_ok=False)
    payload=directory/'payload.bin'
    with payload.open('xb') as out:out.write(data)
    public=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    (directory/'test_public.pem').write_bytes(public)
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    disk=payload.read_bytes()
    saved=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    restored=serialization.load_pem_public_key((directory/'test_public.pem').read_bytes())
    if disk!=data or not verify(restored,disk,saved):raise ValueError('archive readback/signature failed')
    report=dict(status='READY_FOR_LOCAL_TRANSPORT_TEST',directory=str(directory),source=str(source),
        image_bytes=len(data),image_sha256=hashlib.sha256(data).hexdigest(),md5=hashlib.md5(data).hexdigest(),
        test_signature_verified=True,device_installable=False,domain=manifest['domain'],
        source_format=source.suffix.lower(),target=target,source_version=source_version,version=version,
        note='Exact source-file bytes only; HEX is not converted, BIN/SOC are not approved installation containers')
    # Written last: READY exists only after archive readback and signature verification.
    (directory/'admission.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file',required=True,type=Path)
    parser.add_argument('--target',required=True,choices=['GR5526','CAT1'])
    parser.add_argument('--source-version',required=True)
    parser.add_argument('--version',required=True)
    args=parser.parse_args()
    directory=ROOT/'logs/ota_test_releases'/uuid.uuid4().hex
    print(json.dumps(prepare(args.file,args.target,args.source_version,args.version,directory),ensure_ascii=False,indent=2))
