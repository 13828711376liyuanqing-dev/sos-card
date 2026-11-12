"""SAM | 2026-10-09 15:15 +08:00 | Nominal NTC comparison, not validation.
Source: ETA69XX workbook inputs; YP001 20260911 schematic p1;
temporary battery B3435. Do not change source workbook or hardware.
"""
from pathlib import Path
from math import exp, log
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]
def resistance(t,b=3435):
    return 10000*exp(b*(1/(t+273.15)-1/298.15))
def ratio(t,r62=None,extra_ntc=False):
    conductance=1/resistance(t)
    if r62: conductance+=1/r62
    if extra_ntc: conductance+=1/resistance(t)
    down=1/conductance
    return down/(10000+down)

ts=list(range(-20,71))
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="720" viewBox="0 0 1100 720"><rect width="1100" height="720" fill="white"/><g font-family="Microsoft YaHei, sans-serif" fill="#172b45">']
def label(x,y,s,size=16):
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}">{escape(s)}</text>')
def px(t): return 85+(t+20)*10
def py(q): return 540-q*4.2
label(70,40,'YP001 NTC：R62 / R63 对温度检测的影响',25)
label(70,72,'R61=10kΩ；电池 NTC=10kΩ / B3435；典型值计算',16)
for t in range(-20,71,10):
    svg.append(f'<path d="M{px(t)},120V540" stroke="#e0e5eb"/>')
    label(px(t)-10,568,str(t),14)
for q in range(0,101,10):
    svg.append(f'<path d="M85,{py(q)}H985" stroke="#e0e5eb"/>')
    label(42,py(q)+5,str(q),14)
label(470,598,'温度（℃）')
label(85,108,'TS / LDO（%）')
cases=[('R62/R63不贴，电池NTC',None,False),
       ('R62=10k，R63不贴，电池NTC',10000,False),
       ('R62不贴，R63再贴相同NTC',None,True)]
for i,(name,r,extra) in enumerate(cases):
    color=['#1768ac','#ce4037','#7a4eab'][i]
    points=' '.join(f'{px(t):.1f},{py(100*ratio(t,r,extra)):.1f}' for t in ts)
    svg.append(f'<polyline points="{points}" stroke="{color}" fill="none" stroke-width="3"/>')
    svg.append(f'<path d="M85,{628+i*25}h35" stroke="{color}" stroke-width="3"/>')
    label(133,633+i*25,name,15)
    found=[]
    for q in [.733,.683,.448,.344]:
        lo,hi=-100,150
        if ratio(lo,r,extra)<q:
            found.append('无交点'); continue
        for _ in range(60):
            mid=(lo+hi)/2
            if ratio(mid,r,extra)>q: lo=mid
            else: hi=mid
        found.append(round((lo+hi)/2,2))
    print(name,found,'25C=',round(ratio(25,r,extra)*100,2))
for q,name in [(.733,'冷停'),(.683,'偏冷'),(.448,'偏热'),(.344,'热停')]:
    svg.append(f'<path d="M85,{py(q*100)}H985" stroke="#707070" stroke-dasharray="5,4"/>')
    label(845,py(q*100)-6,name+' '+f'{q*100:.1f}'+'%',14)
label(555,630,'未计公差和迟滞；两只 NTC 假定同温。',14)
label(555,657,'电池允许温区 0～45℃；软件仅放行正常 NTC。',14)
svg.append('</g></svg>')
(ROOT/'doc/2026-10-09_NTC_R62_R63曲线.svg').write_text('\n'.join(svg),encoding='utf-8')
# SAM | 2026-10-09 15:45 +08:00 | Raster preview of this simple SVG plot
# because the local runtime has Pillow but no matplotlib/SVG renderer.
import xml.etree.ElementTree as ET
import re
from PIL import Image, ImageDraw, ImageFont
preview=Image.new('RGB',(1100,720),'white')
draw=ImageDraw.Draw(preview)
for element in ET.fromstring('\n'.join(svg)).iter():
    tag=element.tag.split('}')[-1]
    a=element.attrib
    if tag=='text':
        size=int(a.get('font-size','16'))
        font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
        draw.text((float(a['x']),float(a['y'])),element.text or '',font=font,
                  fill='#172b45',anchor='ls')
    elif tag=='polyline':
        pts=[tuple(map(float,p.split(','))) for p in a['points'].split()]
        draw.line(pts,fill=a['stroke'],width=int(a.get('stroke-width','1')))
    elif tag=='path':
        nums=list(map(float,re.findall(r'-?\d+(?:\.\d+)?',a['d'])))
        x,y,last=nums
        end=(last,y) if 'H' in a['d'] else ((x,y+last) if 'v' in a['d'] else (x,last))
        if 'h' in a['d']: end=(x+last,y)
        draw.line([(x,y),end],fill=a['stroke'],width=int(a.get('stroke-width','1')))
preview.save(ROOT/'doc/2026-10-09_NTC_R62_R63曲线.png')
print('workbook Rt1=',3000*27800*(.733-.344)/.733/.344/(27800-3000))
print('workbook Rt2=',(.733-.344)*27800*3000/((1-.733)*.344*27800-(1-.344)*.733*3000))
for t in [0,25,45,60]:print('Rntc',t,round(resistance(t),1))
