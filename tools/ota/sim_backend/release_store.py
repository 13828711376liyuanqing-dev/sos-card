"""SAM | 2026-10-21 +08:00 | Local versioned upload archive; never claims native installation readiness."""
import json
from pathlib import Path
import re
import uuid
import zipfile
from .prepare_release import prepare
from check_layout import read_hex

ROOT=Path(__file__).resolve().parents[3]
STORE=ROOT/'logs/ota_release_catalog'
LIMIT=16*1024*1024

def upload(data,target,source,version,kind,root=STORE):
    if target not in ('GR5526','CAT1') or kind not in ('HEX','BIN','LUATOS_FOTA','GOODIX_SIGNED','SOC'):
        raise ValueError('未知组件或包型')
    for value in (source,version):
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,62}',value):
            raise ValueError('版本仅允许字母数字及点、横线、下划线')
    if source==version or not isinstance(data,bytes) or not 0<len(data)<=LIMIT:
        raise ValueError('源目标版本相同、文件为空或超过16MiB')
    if kind=='HEX':
        if target!='GR5526' or not data.startswith(b':'):raise ValueError('HEX内容/组件错误')
    identity=uuid.uuid4().hex
    folder=Path(root)/identity
    folder.mkdir(parents=True,exist_ok=False)
    source_path=folder/('uploaded.hex' if kind=='HEX' else 'uploaded.bin')
    source_path.write_bytes(data)
    if kind=='HEX':
        read_hex(source_path)  # Validate records/checksums/EOF before publishing an archive.
    report=prepare(source_path,target,source,version,folder/'archive')
    name=f'YP001_{target}_{source}_to_{version}_{identity[:8]}.ypota.zip'
    with zipfile.ZipFile(folder/name,'x',compression=zipfile.ZIP_STORED) as z:
        for path in (folder/'archive').iterdir():z.write(path,path.name)
    entry=dict(id=identity,target=target,source_version=source,version=version,package_type=kind,
               bytes=len(data),sha256=report['image_sha256'],filename=name,device_installable=False,
               target_version_verified=False,version_evidence='operator_labels_only',
               status='TRANSPORT_TEST_PACKAGE',reason='尚无芯片原生包验证及生产安装适配；包型选择不构成格式认证')
    (folder/'release.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf-8')
    return entry

def releases(root=STORE):
    return [json.loads(p.read_text(encoding='utf-8')) for p in sorted(Path(root).glob('*/release.json'))]

def archive(identity,root=STORE):
    if not re.fullmatch('[0-9a-f]{32}',identity):raise ValueError('invalid release id')
    folder=Path(root)/identity
    entry=json.loads((folder/'release.json').read_text(encoding='utf-8'))
    name=entry['filename']
    if Path(name).name!=name or not name.endswith('.ypota.zip'):raise ValueError('invalid archive')
    return folder/name
