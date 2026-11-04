"""Read source exams without modifying the originals (OOXML and legacy Word)."""
from pathlib import Path
import struct, zipfile, xml.etree.ElementTree as ET, re, json

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'source_extract'; OUT.mkdir(exist_ok=True)
ASSETS=ROOT/'assets'; ASSETS.mkdir(exist_ok=True)
u16=lambda b,p:struct.unpack_from('<H',b,p)[0]
u32=lambda b,p:struct.unpack_from('<I',b,p)[0]

def streams(data):
    sector=1<<u16(data,30); mini=1<<u16(data,32)
    read=lambda sid:data[(sid+1)*sector:(sid+2)*sector]
    difat=list(struct.unpack_from('<109I',data,76)); fat=[]
    for sid in difat:
        if sid<0xfffffffa: fat.extend(struct.unpack('<'+'I'*(sector//4),read(sid)))
    def chain(start,table,reader):
        out=b'';seen=set()
        while start<0xfffffffa and start not in seen:
            seen.add(start);out+=reader(start);start=table[start]
        return out
    directory=chain(u32(data,48),fat,read); entries=[]
    for p in range(0,len(directory),128):
        e=directory[p:p+128]
        if len(e)<128:break
        name=e[:max(0,u16(e,64)-2)].decode('utf-16le',errors='ignore')
        entries.append((name,e[66],u32(e,116),struct.unpack_from('<Q',e,120)[0]))
    root=next(e for e in entries if e[1]==5)
    ministream=chain(root[2],fat,read)
    mf=chain(u32(data,60),fat,read)
    minifat=list(struct.unpack('<'+'I'*(len(mf)//4),mf)) if mf else []
    result={}
    for name,kind,start,size in entries:
        if kind!=2:continue
        if size<4096: result[name]=chain(start,minifat,lambda sid:ministream[sid*mini:(sid+1)*mini])[:size]
        else: result[name]=chain(start,fat,read)[:size]
    return result

def legacy_text(data):
    ss=streams(data); word=ss['WordDocument'];table=ss['1Table' if u16(word,10)&0x200 else '0Table']
    p=32;p+=2+u16(word,p)*2;p+=2+u16(word,p)*4;p+=2
    fc,lcb=struct.unpack_from('<II',word,p+33*8);clx=table[fc:fc+lcb];p=0
    while clx[p]==1:p+=3+u16(clx,p+1)
    size=u32(clx,p+1);plc=clx[p+5:p+5+size];n=(size-4)//12;text=''
    for i in range(n):
        count=u32(plc,(i+1)*4)-u32(plc,i*4)
        raw=u32(plc,4*(n+1)+i*8+2);compressed=bool(raw&0x40000000);pos=raw&0x3fffffff
        if compressed: text+=word[pos//2:pos//2+count].decode('cp1252',errors='replace')
        else:text+=word[pos:pos+count*2].decode('utf-16le',errors='replace')
    return text

manifest=[]
for i,path in enumerate(sorted([*ROOT.glob('*.doc'),*ROOT.glob('*.docx')]),1):
    slug=f'exam-{i}';folder=ASSETS/slug;folder.mkdir(exist_ok=True);images=[]
    if path.suffix=='.docx':
        with zipfile.ZipFile(path) as z:
            xml=ET.fromstring(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text='\n'.join(''.join(p.itertext()) if False else ''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in xml.findall('.//w:p',ns))
            for name in z.namelist():
                if name.startswith('word/media/'):
                    target=folder/Path(name).name;target.write_bytes(z.read(name));images.append(str(target.relative_to(ROOT)).replace('\\','/'))
    else:
        data=path.read_bytes();text=legacy_text(data)
        for start in [m.start() for m in re.finditer(b'\x89PNG\r\n\x1a\n',data)]:
            end=data.find(b'IEND',start)
            if end!=-1:
                target=folder/f'image-{len(images)+1}.png';target.write_bytes(data[start:end+8]);images.append(str(target.relative_to(ROOT)).replace('\\','/'))
        for start in [m.start() for m in re.finditer(b'\xff\xd8\xff',data)]:
            end=data.find(b'\xff\xd9',start)
            if end!=-1:
                target=folder/f'image-{len(images)+1}.jpg';target.write_bytes(data[start:end+2]);images.append(str(target.relative_to(ROOT)).replace('\\','/'))
    text=text.replace('\r','\n').replace('\x07',' | ').replace('\x01','[IMAGEN]')
    (OUT/(slug+'.txt')).write_text(text,encoding='utf-8')
    manifest.append({'id':slug,'source':path.name,'images':images,'text':text})
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
for m in manifest:print(m['id'],m['source'],len(m['images']),'images\n',m['text'],'\n')
