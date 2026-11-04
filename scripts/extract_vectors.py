from pathlib import Path
import contextlib,io
with contextlib.redirect_stdout(io.StringIO()):
    from extract_sources import streams
import struct,zlib,json
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'source_extract/manifest.json').read_text(encoding='utf-8'))
for m in manifest:
    p=ROOT/m['source']
    if p.suffix!='.doc':continue
    d=b''.join(streams(p.read_bytes()).values())
    for pos in range(len(d)-8):
        ver,typ,size=struct.unpack_from('<HHI',d,pos)
        if typ not in (0xf01a,0xf01b,0xf01f) or size<50 or pos+8+size>len(d):continue
        if typ==0xf01f:
            for offset in [25,41]:
                dib=d[pos+offset:pos+8+size]
                if dib[:4]!=b'\x28\0\0\0':continue
                depth=struct.unpack_from('<H',dib,14)[0];colors=struct.unpack_from('<I',dib,32)[0] or (1<<depth if depth<=8 else 0)
                bmp=b'BM'+struct.pack('<IHHI',len(dib)+14,0,0,14+40+colors*4)+dib
                target=ROOT/'assets'/m['id']/f'bitmap-{pos}.bmp';target.write_bytes(bmp);print(target.name,len(bmp))
            continue
        uid=32 if (ver>>4) in (0x3d5,0x217) else 16
        h=pos+8+uid
        try:
            saved=struct.unpack_from('<I',d,h+28)[0];comp=d[h+32]
            blob=d[h+34:h+34+saved];blob=zlib.decompress(blob) if comp==0 else blob
            target=ROOT/'assets'/m['id']/f'vector-{pos}.{"emf" if typ==0xf01a else "wmf"}'
            target.write_bytes(blob);print(target.name,len(blob))
        except Exception:pass
