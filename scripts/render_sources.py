from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source_extract/tooling'))
import pymupdf as fitz
from PIL import Image,ImageDraw
panels=[]
for pdf in sorted((ROOT/'source_extract').glob('exam-*.pdf')):
    document=fitz.open(pdf);parts=[]
    for index,page in enumerate(document):
        parts.append(page.get_text())
        png=ROOT/'source_extract'/f'{pdf.stem}-page-{index+1}.png'
        page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(png)
        img=Image.open(png).convert('RGB');img.thumbnail((300,410))
        panel=Image.new('RGB',(320,445),'#e4ebef');panel.paste(img,((320-img.width)//2,25));ImageDraw.Draw(panel).text((12,7),f'{pdf.stem} / {index+1}',fill='black');panels.append(panel)
    (ROOT/'source_extract'/f'{pdf.stem}-pdf.txt').write_text('\n'.join(parts),encoding='utf-8')
    print(pdf.stem,len(document),'pages')
for batch in range(0,len(panels),9):
    group=panels[batch:batch+9];sheet=Image.new('RGB',(960,445*((len(group)+2)//3)),'white')
    for i,panel in enumerate(group):sheet.paste(panel,((i%3)*320,(i//3)*445))
    sheet.save(ROOT/'source_extract'/f'contact-{batch//9+1}.png')
