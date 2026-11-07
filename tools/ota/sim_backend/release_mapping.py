"""SAM | 2026-10-21 +08:00 | Internal simulation mapping only; no new customer wire fields or trust approval."""
import re

def checked(release):
    r=dict(release)
    if r.get('target') not in ('GR5526','CAT1'):
        raise ValueError('unknown component')
    for name,size in [('id',64),('hash',64),('md5',32)]:
        if not isinstance(r.get(name),str) or not re.fullmatch('[0-9a-f]{'+str(size)+'}',r[name]):
            raise ValueError('invalid identity')
    if any(not isinstance(r.get(k),str) or not r[k] for k in ('source','version','url')):
        raise ValueError('incomplete release')
    if r['source']==r['version'] or not r['url'].startswith(('http://','https://')):
        raise ValueError('invalid release')
    return r

def command(release, timestamp):
    r=checked(release)
    if type(timestamp) is not int or not 0<=timestamp<=0xffffffff:
        raise ValueError('invalid time')
    return dict(MsgType='otaMsg',CurrentVersion=r['source'],TargetVersion=r['version'],
                Address=r['url'],Md5=r['md5'],Time=timestamp)

def resolve(releases, message):
    if not isinstance(message,dict) or set(message)!={'MsgType','CurrentVersion','TargetVersion','Address','Md5','Time'}:
        raise ValueError('unexpected customer fields')
    matches=[]
    for release in releases:
        r=checked(release)
        if command(r,message['Time'])==message:
            matches.append(r)
    if len(matches)!=1:
        raise ValueError('missing or ambiguous release mapping')
    return matches[0]
