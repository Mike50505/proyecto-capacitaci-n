"""Paginated evaluation PDFs generated from saved exam snapshots."""
import io
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg
from exam_document import document_settings
from answer_review import answer_review
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable

FONT_DIR = Path(reportlab.__file__).parent / 'fonts'
pdfmetrics.registerFont(TTFont('Training', str(FONT_DIR / 'Vera.ttf')))
pdfmetrics.registerFont(TTFont('TrainingBold', str(FONT_DIR / 'VeraBd.ttf')))
pdfmetrics.registerFontFamily('Training', normal='Training', bold='TrainingBold', italic='Training', boldItalic='TrainingBold')
INK = colors.HexColor('#183746')
TEAL = colors.HexColor('#147e83')
WIDTH = A4[0] - 88
CONTENT = WIDTH - 36
BACK = colors.HexColor('#f0f5f8')
LINE = colors.HexColor('#dce7ed')
STATES = {'correct':('#edf8f1','#207044','Correcta'),'incorrect':('#fff0f1','#ad2d3d','Incorrecta'),'partial':('#fff5df','#95630c','Parcialmente correcta'),'pending':('#eef2f7','#5c7185','Pendiente de revisión')}


class ScreenCard(Table):
    whole_height=0

    def split(self,availWidth,availHeight):
        if self.whole_height and self._height<=self.whole_height and self._height>availHeight:
            return []
        return super().split(availWidth,availHeight)


class SelectionMark(Flowable):
    def __init__(self,selected,multiple,color):
        super().__init__();self.width=14;self.height=14
        self.selected,self.multiple,self.color=selected,multiple,color

    def draw(self):
        c=self.canv;c.setStrokeColor(self.color);c.setFillColor(self.color if self.selected else colors.white);c.setLineWidth(1)
        if self.multiple:
            c.roundRect(1,1,12,12,3,fill=1,stroke=1)
            if self.selected:
                c.setStrokeColor(colors.white);c.setLineWidth(1.4);c.lines([(3,7,6,4),(6,4,11,10)])
        else:
            c.circle(7,7,6,fill=1,stroke=1)
            if self.selected:c.setFillColor(colors.white);c.circle(7,7,2,fill=1,stroke=0)


def card(items, width=WIDTH, background=colors.white, border=LINE, padding=18):
    panel=ScreenCard([[items]],colWidths=[width],splitInRow=1,cornerRadii=[11,11,11,11],hAlign='LEFT')
    panel.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),background),('BOX',(0,0),(-1,-1),.6,border),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),padding),('RIGHTPADDING',(0,0),(-1,-1),padding),('TOPPADDING',(0,0),(-1,-1),padding),('BOTTOMPADDING',(0,0),(-1,-1),padding)]))
    return panel


@lru_cache(maxsize=4)
def mesa_logo(root):
    return svg2rlg(str(Path(root) / 'static/branding/mesa.svg'))


class Figure(Flowable):
    def __init__(self, path, marks=()):
        super().__init__()
        self.picture = ImageReader(str(path))
        w, h = self.picture.getSize()
        scale = min(CONTENT / w, 245 / h, 1)
        self.width, self.height = w * scale, h * scale
        self.marks = marks
        self.hAlign='CENTER'

    def draw(self):
        c = self.canv
        c.drawImage(self.picture, 0, 0, self.width, self.height, mask='auto')
        for index, mark in enumerate(self.marks, 1):
            x, y = mark['x'] * self.width, (1 - mark['y']) * self.height
            c.setFillColor(TEAL); c.setStrokeColor(colors.white)
            c.circle(x, y, 8, fill=1, stroke=1)
            c.setFillColor(colors.white); c.setFont('TrainingBold', 8)
            c.drawCentredString(x, y - 3, str(index))


def evaluation_pdf(exam, root, result=None):
    """Return PDF bytes. No keys, rubric or draft versions replace a submitted snapshot."""
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = 'Training'
    styles.add(ParagraphStyle('ExamTitle', fontName='TrainingBold', fontSize=19, leading=25, textColor=INK, spaceAfter=14))
    styles.add(ParagraphStyle('QuestionTitle', fontName='TrainingBold', fontSize=8.5, leading=13, textColor=TEAL, spaceAfter=10, keepWithNext=True))
    styles.add(ParagraphStyle('Prompt', fontName='TrainingBold', fontSize=12, leading=18, textColor=INK, spaceAfter=12, keepWithNext=True))
    styles.add(ParagraphStyle('HeroTitle', fontName='TrainingBold', fontSize=21, leading=28, textColor=colors.white, spaceAfter=12))
    styles.add(ParagraphStyle('HeroMeta', fontName='Training', fontSize=9, leading=14, textColor=colors.HexColor('#c7e5e8'), spaceAfter=6))
    styles.add(ParagraphStyle('Copy', fontName='Training', fontSize=9.5, leading=15, textColor=INK, spaceAfter=7, wordWrap='LTR'))
    styles.add(ParagraphStyle('Cell', fontName='Training', fontSize=8, leading=12, textColor=INK))
    styles.add(ParagraphStyle('MutedCopy', parent=styles['Copy'], textColor=colors.HexColor('#516575')))
    styles.add(ParagraphStyle('SectionLabel', parent=styles['Copy'], fontName='TrainingBold', textColor=TEAL, spaceBefore=12, keepWithNext=True))

    def p(value, style='Copy'):
        return Paragraph(escape(str(value if value is not None else '')).replace('\n', '<br/>'), styles[style])

    def response_panel(label,value,background):
        style=ParagraphStyle('ResponsePanel',parent=styles['Copy'],backColor=background,borderPadding=11,borderRadius=7)
        text='<b><font color="#147e83">'+escape(label)+'</font></b><br/>'+escape(str(value)).replace('\n','<br/>')
        return [Spacer(1,12),Paragraph(text,style),Spacer(1,12)]

    def table(rows, states=None):
        grid = Table([[p(cell,'Cell') for cell in row] for row in rows], colWidths=[CONTENT / len(rows[0])] * len(rows[0]), repeatRows=1, splitInRow=1, hAlign='LEFT')
        commands=[('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf3f3')), ('LINEBELOW', (0, 0), (-1, -1), .35, LINE), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9), ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10)]
        for i in range(1,len(rows)):
            background=STATES['correct' if states[i-1] else 'incorrect'][0] if states else '#f5f8fa' if i%2 else '#ffffff'
            commands.append(('BACKGROUND',(0,i),(-1,i),colors.HexColor(background)))
        grid.setStyle(TableStyle(commands))
        return grid

    identity = document_settings(exam)
    header_style = ParagraphStyle('DocumentHeader', fontName='Training', fontSize=8, leading=11, alignment=TA_CENTER, textColor=INK)
    revision_style = ParagraphStyle('DocumentRevision', parent=header_style, alignment=TA_RIGHT)
    header = Paragraph(escape(identity['top_text']).replace('\n','<br/>') + '<br/><b>' + escape(exam['title']) + '</b>', header_style)
    revision = Paragraph(escape(identity['revision_text']).replace('\n','<br/>'), revision_style)
    header_height = max(40, header.wrap(WIDTH - 204, 200)[1], revision.wrap(114, 200)[1])
    footer_widths = [WIDTH * .40, WIDTH * .40, WIDTH * .20]
    footers = [Paragraph(escape(identity[key]).replace('\n','<br/>'), ParagraphStyle('DocumentFooter'+str(i), fontName='TrainingBold' if i==2 else 'Training', fontSize=9 if i==2 else 8, leading=12, alignment=[0,TA_CENTER,TA_RIGHT][i], textColor=INK)) for i,key in enumerate(('footer_left','footer_center','footer_right'))]
    footer_heights = [item.wrap(width-8, 200)[1] for item,width in zip(footers,footer_widths)]
    footer_height = max(footer_heights)
    subtitle = 'RESULTADO INDIVIDUAL' if result else 'EVALUACIÓN DIGITAL'
    hero=[p('MESA FORMACIÓN  /  '+subtitle,'HeroMeta'),p(exam['title'],'HeroTitle'),p(f"{exam.get('category') or 'Capacitación'}  ·  {len(exam['questions'])} preguntas  ·  Mínimo aprobatorio: {exam.get('pass_score',80)}%",'HeroMeta')]
    if result:
        report=result['summary']
        hero.append(p(f"Calificación: {report['score'] if report['score'] is not None else 'Pendiente'}{'%' if report['score'] is not None else ''}  ·  {'Pendiente de revisión' if report['pending'] else 'Aprobado' if report['passed'] else 'No aprobado'}",'HeroMeta'))
    elif exam.get('description'):hero.append(p(exam['description'],'HeroMeta'))
    story = [card(hero,background=INK,border=INK,padding=22),Spacer(1,16)]
    info_start=len(story)
    if result:
        participant, report = result['participant'], result['summary']
        state = 'Pendiente de revisión' if report['pending'] else 'Aprobado' if report['passed'] else 'No aprobado'
        story.extend([table([
            ['Participante', 'Identificación'],
            [participant['name'], ('Nómina: ' if participant['type'] == 'employee' else 'Referencia: ') + (participant.get('payroll') or 'Sin registrar')],
            [participant.get('department') or 'Sin departamento', 'Empleado' if participant['type'] == 'employee' else 'Postulante'],
        ]), Spacer(1, 10), p(f"Folio MESA-{result['id']:05d} · Versión {result['version']} · Enviado: {result.get('submitted_at') or 'Sin fecha'}", 'MutedCopy'),
            p(f"Estado: {state} · Calificación: {report['score'] if report['score'] is not None else 'Pendiente'}{'%' if report['score'] is not None else ''} · Puntos: {report['earned']} / {report['maximum']}"),
            p(f"Preguntas pendientes: {report['pending']} · Mínimo aprobatorio: {exam.get('pass_score', 80)}%", 'MutedCopy')])
        if result.get('archived'):
            story.append(p('Evaluación eliminada del historial vigente (registro conservado).', 'MutedCopy'))
    if result:story[info_start:]=[card(story[info_start:]),Spacer(1,16)]
    if exam.get('instructions'):
        story.extend([card([p('ANTES DE COMENZAR', 'SectionLabel'), p(exam['instructions'])],background=colors.HexColor('#e7f3f4'),border=colors.HexColor('#d1e6e8')),Spacer(1,16)])
    answers = result.get('answers', {}) if result else {}
    grading = result.get('grading', {}) if result else {}
    reviews=answer_review(exam,answers,grading) if result else {}
    for index, question in enumerate(exam['questions'], 1):
        group_start = len(story)
        if question.get('section'):
            story.append(p(question['section'], 'SectionLabel'))
        review=reviews.get(question['id']);state=review['status'] if review else None
        story.append(p(f"Pregunta {index:02d} · {question['points']} puntos"+(' · '+STATES[state][2] if state else ''), 'QuestionTitle'))
        story.append(p(question['prompt'],'Prompt'))
        if question.get('help'):
            story.append(p(question['help'], 'MutedCopy'))
        answer = answers.get(question['id'])
        typ = question['type']
        if question.get('image'):
            image_path = (Path(root) / question['image'].lstrip('/')).resolve()
            allowed = [Path(root, 'assets', name).resolve() for name in ('figures', 'uploads')]
            if image_path.is_file() and any(image_path.is_relative_to(folder) for folder in allowed):
                story.extend([Figure(image_path, answer or [] if typ == 'image_mark' else []), Spacer(1, 8)])
            else:
                story.append(p('Figura de referencia no disponible.', 'MutedCopy'))
        if typ in ('single', 'multiple', 'boolean'):
            options = ['Verdadero', 'Falso'] if typ == 'boolean' else question['options']
            for option in options:
                chosen = option in (answer or []) if typ == 'multiple' else answer == option
                option_state=None;label='Respuesta registrada' if chosen else ''
                if review and review['has_key']:
                    expected=option in question['correct'] if typ=='multiple' else option==question['correct']
                    option_state='incorrect' if chosen and not expected else 'correct' if expected else None
                    label=('Tu respuesta · '+('Correcta' if expected else 'Incorrecta')) if chosen else 'Respuesta correcta' if expected else ''
                    if typ=='multiple' and expected and not chosen:label='Faltó seleccionarla · Respuesta correcta'
                background=colors.HexColor(STATES[option_state][0] if option_state else '#f5f8fa')
                values=[p(option)]
                if label:values.append(p(label,'MutedCopy'))
                accent=colors.HexColor(STATES[option_state][1]) if option_state else TEAL
                row=Table([[SelectionMark(chosen,typ=='multiple',accent),values]],colWidths=[29,CONTENT-29],splitInRow=1,cornerRadii=[8,8,8,8],hAlign='LEFT')
                row.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),background),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
                story.extend([row,Spacer(1,7)])
        elif review and review['has_key'] and typ in ('matching','table'):
            story.append(p(f"{review['matched']} de {review['total']} respuestas correctas según la clave.",'SectionLabel'))
            rows=[['Concepto / referencia','Respuesta registrada','Resultado','Respuesta correcta']]+[[item['label'],item['answer'] or 'Sin respuesta','Correcta' if item['correct'] else 'Incorrecta',item['correct_answer']] for item in review['items']]
            story.append(table(rows,[item['correct'] for item in review['items']]))
        elif typ == 'matching':
            story.append(table([['Concepto', 'Respuesta']] + [[row, (answer or {}).get(row, 'Sin respuesta' if result else 'Por responder')] for row in question['rows']]))
        elif typ == 'table':
            story.append(table([['Referencia'] + question['columns']] + [[row] + [(answer or {}).get(f'{i}:{j}', 'Sin respuesta' if result else 'Por responder') for j in range(len(question['columns']))] for i, row in enumerate(question['rows'])]))
        elif typ == 'image_mark':
            for i, mark in enumerate(answer or [], 1):
                story.append(p(f"Marca {i}: {mark.get('label') or 'Sin etiqueta'}"))
            if not answer:
                story.append(p('Sin marcas registradas.' if result else 'Marca la figura e identifica sus partes.'))
        else:
            background=colors.HexColor(STATES[state][0] if state else '#f5f8fa')
            story.extend(response_panel('RESPUESTA',answer if answer is not None and answer!='' else 'Sin respuesta registrada' if result else 'Respuesta abierta' if typ=='long_text' else 'Por responder',background))
            if review and review['has_key'] and state!='correct':
                story.extend(response_panel('RESPUESTA CORRECTA',review['correct_answer'],colors.HexColor('#edf8f1')))
        if result:
            grade = grading.get(question['id'], {})
            story.append(Spacer(1,10))
            story.append(p(f"Puntos obtenidos: {grade.get('points') if grade.get('points') is not None else 'Pendiente'} / {question['points']}", 'MutedCopy'))
            if grade.get('feedback'):
                story.append(p('Observaciones: ' + grade['feedback']))
            if not review['has_key']:story.append(p('Sin clave configurada en esta versión. Revisión manual.','MutedCopy'))
        group = story[group_start:]
        border=colors.HexColor(STATES[state][1]) if state else LINE
        available=A4[1]-header_height-footer_height-136
        height=sum(item.wrap(CONTENT,A4[1])[1]+item.getSpaceBefore()+item.getSpaceAfter() for item in group)+36
        if height<=available:
            panel=card(group,border=border);panel.whole_height=available
            story[group_start:] = [panel,Spacer(1,16)]
        else:
            # Long answers and oversized tables must retain normal paragraph pagination.
            story[group_start:] = group+[Spacer(1,16)]

    def page_frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BACK);canvas.rect(0,0,A4[0],A4[1],fill=1,stroke=0)
        bottom = A4[1] - 24 - header_height
        canvas.setFillColor(colors.white);canvas.roundRect(32,bottom-10,A4[0]-64,header_height+20,11,fill=1,stroke=0)
        drawing = mesa_logo(str(root))
        if drawing:
            scale = min(76/drawing.width,40/drawing.height)
            canvas.saveState();canvas.translate(44,bottom+(header_height-drawing.height*scale)/2);canvas.scale(scale,scale)
            renderPDF.draw(drawing,canvas,0,0);canvas.restoreState()
        header.drawOn(canvas,134,bottom+(header_height-header.height)/2)
        revision.drawOn(canvas,A4[0]-44-114,bottom+(header_height-revision.height)/2)
        canvas.setFillColor(colors.white);canvas.roundRect(32,30,A4[0]-64,footer_height+24,9,fill=1,stroke=0)
        x=44
        for item,width,height in zip(footers,footer_widths,footer_heights):
            item.drawOn(canvas,x,38+footer_height-height);x+=width
        canvas.setFont('Training',7);canvas.setFillColor(colors.HexColor('#516575'))
        canvas.drawRightString(A4[0]-44,20,f'Página {doc.page}')
        canvas.restoreState()

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=44, rightMargin=44, topMargin=header_height+52, bottomMargin=footer_height+66, title=exam['title'], author='MESA Formación')
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    return output.getvalue()
