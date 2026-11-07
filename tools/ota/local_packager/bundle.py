"""SAM | 2026-10-22 +08:00 | One dual-component upload; numeric whole-product versions are independent of mutable names."""
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid
import zipfile
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/ota'))
from sim_backend.signed_manifest import canonical, new_key
from check_layout import read_hex

LIMIT=16*1024*1024
DOMAIN='YP001_DUAL_UPLOAD_TEST_V1'

def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]{0,4})(\.(0|[1-9][0-9]{0,4})){1,3}',value):
        raise ValueError('版本需为2至4段数字，例如1.0、1.3；不允许前导零')
    parts=tuple(map(int,value.split('.')))
    if any(n>65535 for n in parts):raise ValueError('版本段不能大于65535')
    return parts+(0,)*(4-len(parts))

def validate_upgrade(source,target):
    if version_tuple(target)<=version_tuple(source):raise ValueError('目标版本必须大于源版本，禁止同版本或降级')
    return source+'---'+target

def label(value):
    if not isinstance(value,str) or len(value)>48 or '---' in value or re.search(r'[<>:"/\\|?*\x00-\x1f]',value):
        raise ValueError('名称含非法字符、过长或使用了保留分隔符---')
    return value.strip()

def bundle(gr,cat,output,source_version,target_version,prefix='YP001',suffix=''):
    upgrade=validate_upgrade(source_version,target_version)
    prefix,suffix=label(prefix),label(suffix)
    blobs=[];components=[]
    for target,path in [('GR5526',gr),('CAT1',cat)]:
        path=Path(path).resolve()
        with path.open('rb') as stream:data=stream.read(LIMIT+1)
        if not 0<len(data)<=LIMIT:raise ValueError(target+'固件为空或超过16MiB')
        if path.suffix.lower()=='.hex':
            if target!='GR5526':raise ValueError('CAT1不能使用GR HEX')
            read_hex(path)
        member=target+'/payload.bin'
        blobs.append((member,data))
        components.append(dict(target=target,path=member,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
            md5=hashlib.md5(data).hexdigest(),original_filename=path.name,
            embedded_version_verified=False,release_version=target_version))
    if Path(gr).resolve()==Path(cat).resolve():raise ValueError('必须分别选择5526和CAT1固件')
    meta=dict(schema=1,domain=DOMAIN,product='YP001',source_version=source_version,target_version=target_version,
        upgrade=upgrade,display_prefix=prefix,display_suffix=suffix,components=components,
        distribution='SPLIT_THEN_SERIAL',order=['GR5526','CAT1'],preserve_user_data=True,
        device_installable=False,version_evidence='whole_product_release_declared_not_embedded_verified')
    key=new_key();signature=key.sign(canonical(meta))
    pub=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    stem='_'.join(x for x in [prefix,upgrade,suffix,uuid.uuid4().hex[:12]] if x)
    final=output/(stem+'.ypota.zip')
    with final.open('xb') as stream:
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED) as z:
            for member,data in blobs:z.writestr(member,data)
            z.writestr('bundle.json',canonical(meta))
            z.writestr('bundle.sig',signature)
            z.writestr('test_public.pem',pub)
    if not verify_bundle(final):raise ValueError('输出包验证失败，请勿上传')
    return dict(file=str(final),upgrade=upgrade,components=components,device_installable=False,
                sha256=hashlib.sha256(final.read_bytes()).hexdigest())

def verify_bundle(path,trusted_fingerprint=None):
    try:
        with zipfile.ZipFile(path) as z:
            expected={'GR5526/payload.bin','CAT1/payload.bin','bundle.json','bundle.sig','test_public.pem'}
            entries=z.infolist()
            if len(entries)!=5 or {x.filename for x in entries}!=expected:return False
            if any(x.file_size>LIMIT for x in entries):return False
            meta=json.loads(z.read('bundle.json'))
            if meta['domain']!=DOMAIN or meta['distribution']!='SPLIT_THEN_SERIAL' or meta['preserve_user_data'] is not True:return False
            if meta['upgrade']!=validate_upgrade(meta['source_version'],meta['target_version']):return False
            # SAM | 2026-10-22 +08:00 | Names may change, but filename version must agree with the signed manifest.
            filename=Path(path).name
            if filename.count('---')!=1 or not re.search(r'(?<![0-9.])'+re.escape(meta['upgrade'])+r'(?=_|\.ypota\.zip$)',filename):return False
            if meta['order']!=['GR5526','CAT1'] or meta['device_installable'] is not False:return False
            public=z.read('test_public.pem')
            if trusted_fingerprint and hashlib.sha256(public).hexdigest()!=trusted_fingerprint:return False
            serialization.load_pem_public_key(public).verify(z.read('bundle.sig'),canonical(meta))
            if [x['target'] for x in meta['components']]!=['GR5526','CAT1']:return False
            for item in meta['components']:
                if item['path']!=item['target']+'/payload.bin':return False
                raw=z.read(item['path'])
                if not raw or len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256'] or hashlib.md5(raw).hexdigest()!=item['md5']:return False
        return True
    except (OSError,ValueError,TypeError,KeyError,InvalidSignature,zipfile.BadZipFile,AttributeError):
        return False
