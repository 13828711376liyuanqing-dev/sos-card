import sys
import zipfile
from xml.etree import ElementTree as ET

ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with zipfile.ZipFile(sys.argv[1]) as z:
    root = ET.fromstring(z.read('word/document.xml'))
for element in root.findall('.//w:body/*', ns):
    if element.tag.endswith('}p'):
        s = ''.join(t.text or '' for t in element.findall('.//w:t', ns)).strip()
        if s:
            print(s)
    elif element.tag.endswith('}tbl'):
        for row in element.findall('./w:tr', ns):
            cells = []
            for cell in row.findall('./w:tc', ns):
                s = ''.join(t.text or '' for t in cell.findall('.//w:t', ns)).strip()
                cells.append(s.replace('\n', ' '))
            print(' | '.join(cells))
