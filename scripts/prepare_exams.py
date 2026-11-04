from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'source_extract/tooling'))
import pymupdf as fitz
from PIL import Image,ImageDraw
manifest=json.loads((ROOT/'source_extract/manifest.json').read_text(encoding='utf-8'))
folder=ROOT/'assets/figures';folder.mkdir(exist_ok=True)
def crop(exam,page,rect,name):
    doc=fitz.open(ROOT/f'source_extract/exam-{exam}.pdf');doc[page].get_pixmap(matrix=fitz.Matrix(2,2),clip=fitz.Rect(rect)).save(folder/(name+'.png'));return '/assets/figures/'+name+'.png'
fig={}
for name,e,p,r in [
 ('cinta-ejemplo',1,0,(30,320,485,422)),('cinta-lectura-1',1,0,(30,445,485,546)),('cinta-lectura-2',1,0,(30,567,485,671)),('cinta-lectura-3',1,1,(30,120,485,223)),('cinta-lectura-4',1,1,(30,242,485,339)),('cinta-conversiones',1,1,(30,405,540,780)),
 ('dibujo-vistas',2,0,(56,363,539,691)),('dibujo-parte',2,1,(107,306,394,418)),('dibujo-tolerancias',2,1,(107,451,386,584)),('dibujo-material',2,1,(107,617,366,766)),('dibujo-limites',2,2,(107,172,484,360)),
 ('calidad-directrices',4,0,(76,347,503,445)),('vernier-mediciones',6,0,(95,535,535,640)),('vernier-partes',6,1,(43,157,570,344))]:fig[name]=crop(e,p,r,name)
# Keep each original arrow and ruler, removing adjacent answer/header text.
for name,page,top,bottom,arrow_x in [('cinta-ejemplo',0,354.35,418.7,186),('cinta-lectura-1',0,479.9,544.2,207),('cinta-lectura-2',0,601.55,667.8,119),('cinta-lectura-3',1,153.5,220.45,229),('cinta-lectura-4',1,276.35,336.6,292)]:
    fig[name]=crop(1,page,(30,top-27,485,bottom+2),name)
    target=folder/(name+'.png');img=Image.open(target);drawing=ImageDraw.Draw(img)
    left=int((arrow_x-30-7)*2);right=int((arrow_x-30+7)*2)
    drawing.rectangle((0,0,left,51),fill='white');drawing.rectangle((right,0,img.width,51),fill='white');img.save(target)

def q(qid,prompt,typ='long_text',**kw):return {'id':qid,'prompt':prompt,'type':typ,'required':True,'points':1,'correct':None,**kw}
def exam(idx,title,desc,category,revision,questions):
    return {'id':f'exam-{idx}','title':title,'description':desc,'category':category,'revision':revision,'source_file':manifest[idx-1]['source'],'duration':20,'pass_score':80,'instructions':'Lee cada pregunta y responde de acuerdo con lo aprendido en tu capacitación. Las preguntas y figuras provienen del documento de referencia.','questions':questions}
exams=[]
exams.append(exam(1,'Cinta métrica','Lectura de medidas en pulgadas y conversión a milímetros.','Metrología','Rev. 03 · FO-RH-13',[
 q('c1','¿A cuántos milímetros equivale una pulgada?','number',section='I. Escribe la respuesta correcta'),
 q('c2','¿Cuántos milímetros hay en 1 ¾ pulgadas?','number',section='I. Escribe la respuesta correcta'),
 q('c3','¿Cuántos milímetros hay en 2 ½ pulgadas?','number',section='I. Escribe la respuesta correcta'),
 *[q(f'c{i+4}',f'Realiza la lectura de la marca indicada en la regla {i+1}, en pulgadas y su conversión a milímetros.','table',image=fig[f'cinta-lectura-{i+1}'],rows=['Marca indicada'],columns=['Pulgadas (fracción)','Milímetros (mm)'],section='II. Lectura de reglas',help='Ejemplo del documento: 28/32 = 14/16 = 7/8 de pulgada = 22.225 mm.' if i==0 else '') for i in range(4)],
 q('c8','Realiza las conversiones de pulgadas a milímetros de las dimensiones del dibujo.','table',image=fig['cinta-conversiones'],rows=['6.82 pulgadas','5.07 pulgadas','4.82 pulgadas','Ø 0.257 pulgadas','4.44 pulgadas','2.69 pulgadas','0.875 pulgadas (nota del dibujo)'],columns=['Milímetros (mm)'],section='III. Conversiones',help='El original presenta las cotas en el dibujo; aquí se ofrecen campos para registrar cada conversión.')]))
exams.append(exam(2,'Interpretación básica de dibujo','Identifica vistas, números de parte, materiales y tolerancias en dibujos de fabricación.','Dibujo técnico','Rev. 01 · FO-RH-14',[
 q('d1','¿Para qué sirve el dibujo de fabricación en el proceso?'),
 q('d2','Selecciona los puntos críticos en los dibujos. Puede ser más de uno.','multiple',options=['Tolerancias','Descripción','Liberación de primera pieza','FCD’s','Número de parte']),
 q('d3','Escribe el nombre de las siguientes vistas.','table',image=fig['dibujo-vistas'],rows=['Vista del lado izquierdo','Vista superior del lado derecho','Vista inferior del lado derecho'],columns=['Nombre de la vista']),
 q('d4','Menciona la diferencia que hay entre cada empresa para buscar el dibujo en Master Web.',help='Ejemplo del documento: con Lennox se busca con el número de parte individual o colocando al final -00.'),
 q('d5','Encierra el número de parte del dibujo.','image_mark',image=fig['dibujo-parte'],help='Marca la ubicación del número de parte en la imagen.'),
 q('d6','Encierra cuáles son las tolerancias en el dibujo.','image_mark',image=fig['dibujo-tolerancias'],help='Puedes colocar varias marcas.'),
 q('d7','Encierra dónde viene ubicado el material en el siguiente dibujo.','image_mark',image=fig['dibujo-material']),
 q('d8','De acuerdo con las tolerancias del dibujo, determina la tolerancia máxima y la tolerancia mínima de las siguientes medidas.','table',image=fig['dibujo-limites'],rows=['23.15','32','6.4','65°'],columns=['Tolerancia máxima','Tolerancia mínima'])]))
exams.append(exam(3,'Liberación de primera pieza','Evalúa el proceso, las responsabilidades y el registro de la liberación de primera pieza.','Calidad','Rev. 02 · FO-RH-14',[
 q('p1','¿Qué es liberación de primera pieza?'),q('p2','¿Cuál es el objetivo de la liberación de primera pieza?'),q('p3','Explica brevemente el proceso general para realizar liberación de primera pieza.'),q('p4','¿Qué se debe hacer si no cumple con las especificaciones y la pieza es rechazada?'),q('p5','¿Quién autoriza la liberación de primera pieza?','text'),q('p6','¿Puedo usar un mismo formato para dos máquinas diferentes?','single',options=['Cierto','Falso']),q('p7','Menciona los puntos más importantes a llenar en el formato de liberación de primera pieza:')]))
exams.append(exam(4,'Política y objetivos de calidad','Conoce la política, las directrices, los objetivos, la visión y la misión de MESA.','Cultura MESA','Rev. 18 · FO-RH-01',[
 q('a1','Selecciona el párrafo correspondiente a nuestra política de calidad MESA.','single',options=[
 'A) Ser reconocidos y respetados como líderes innovadores y excelentes socios comerciales, proporcionando valores únicos y difíciles de igualar en todos nuestros productos.',
 'B) En MESA nos comprometemos con nuestros clientes, colaboradores y otras audiencias clave; estableciendo altos estándares y en cumplimiento de las normas, para ofrecer productos y servicios de alta calidad en la industria, buscando la excelencia para mantenernos como una empresa rentable y socialmente responsable a través de la mejora continua e innovación.',
 'C) En MESA estamos comprometidos en consolidarnos como líderes en la fabricación de partes de cobre y aluminio.']),
 q('a2','Escribe las cuatro directrices de MESA.','table',image=fig['calidad-directrices'],rows=['1','2','3','4'],columns=['Directriz']),
 q('a3','Relaciona cada objetivo de calidad con la meta correspondiente.','matching',rows=['Calidad','OTD (Entregas a tiempo)','Ética empresarial','Satisfacción de clientes','Satisfacción de empleados','Productividad'],options=['A. 99% mínimo','B. 85% mínimo','C. 175 PPM máximo','D. 5% mínimo','E. 86% mínimo','F. 97% mínimo']),
 q('a4','Relaciona el significado con su concepto dentro de MESA.','matching',rows=['Es el modo en que MESA pretende hacer realidad nuestra visión.','Son considerados la guía que como MESA debemos seguir y respetar para cumplir con nuestra política de calidad.','Es el objetivo de MESA.'],options=['Visión','Misión','Valores organizacionales']),
 q('a5','Señala cuál es la visión de MESA.','single',options=['A) Ser líder en soluciones innovadoras con nuestros productos y servicios reconocidos por sumar la cadena de valor de nuestro cliente, sosteniendo relaciones de largo plazo basadas en la confianza.','B) Convertirnos en una empresa reconocida en la región centro del país, por medio de un excepcional servicio a nuestros clientes.','C) Fija el rumbo de la institución, plantea retos, sirve como consenso, estimula la creatividad y coordina esfuerzos.']),
 q('a6','Señala cuál es la misión de MESA.','single',options=['A) Es una herramienta estratégica que sintetiza el propósito de una empresa.','B) Ofrecer valor a nuestros clientes, colaboradores y otras audiencias clave, basados en un negocio exitoso por medio de la innovación, seguridad, calidad y cuidado del medio ambiente, consolidándonos mediante la oferta de productos y servicios imprescindibles en la cadena de suministro.','C) Mejora la calidad mediante la gestión por administración eficiente de los recursos para construir, mantener y rehabilitar la infraestructura.'])]))
exams.append(exam(5,'Uso de Master Web','Control de documentos, revisiones vigentes y buenas prácticas en el Sistema de Gestión de Calidad.','Sistema de calidad','Rev. 03 · FO-RH-13',[
 q('m1','¿Cuál es la función principal de Master Web?','single',options=['A) Almacenar archivos personales de los empleados','B) Administrar y controlar la documentación del Sistema de Gestión de Calidad','C) Crear reportes de producción','D) Sustituir los equipos de cómputo de la empresa']),
 q('m2','¿Por qué es importante utilizar Master Web?','single',options=['A) Porque permite tener documentos vigentes, identificados y controlados','B) Porque evita utilizar cualquier tipo de documento','C) Porque solamente Calidad puede consultar documentos','D) Porque permite guardar archivos sin necesidad de revisarlos']),
 q('m3','Tener un archivo guardado en la computadora significa automáticamente que es un documento controlado.','boolean'),
 q('m4','Antes de utilizar un procedimiento, formato o instrucción de trabajo, ¿qué debemos verificar?','single',options=['A) Que el archivo tenga muchas páginas','B) Que esté guardado en nuestra computadora','C) Que sea la versión/revisión vigente y autorizada','D) Que haya sido creado recientemente']),
 q('m5','¿Qué puede suceder si se utiliza una versión obsoleta de un documento?','single',options=['A) No sucede nada','B) Puede provocar que el proceso se realice con información incorrecta y genera un hallazgo durante una auditoría','C) Master Web elimina automáticamente el documento','D) El documento se actualiza solo']),
 q('m6','¿Qué tipo de documentos podemos consultar en Master Web?','single',options=['A) Procedimientos','B) Instrucciones de trabajo','C) Formatos y ayudas visuales','D) Todas las anteriores']),
 q('m7','Los documentos del SGC deben mantenerse controlados para evitar el uso no intencionado de información obsoleta.','boolean'),
 q('m8','Si detectas que un formato o instrucción de trabajo necesita una modificación, ¿qué debes hacer?','single',options=['A) Modificar directamente el archivo que encuentres en la computadora','B) Crear una nueva versión sin avisarle a nadie','C) Seguir el proceso establecido para solicitar, revisar y aprobar la modificación','D) Eliminar el documento anterior']),
 q('m9','Un operador tiene guardada en su computadora una instrucción de trabajo que utiliza desde hace varios meses. Al buscarla en Master Web encuentra una versión diferente y con una revisión más reciente. ¿Cuál debe utilizar? ¿Por qué?',section='Caso práctico'),
 q('m10','Durante una auditoría, el auditor solicita el formato que utiliza tu área para realizar una inspección. ¿Qué debes hacer para asegurarte de mostrarle la documentación correcta?',section='Caso práctico')]))
exams.append(exam(6,'Vernier','Tipos de medición, componentes, manejo y cuidado del vernier.','Metrología','Rev. 00',[
 q('v1','¿Qué es el vernier?'),q('v2','Menciona tres tipos de vernier.','table',rows=['1','2','3'],columns=['Tipo de vernier']),
 q('v3','Coloca la letra correspondiente a cada tipo de medición.','matching',rows=['La profundidad de un orificio o ranura.','El diámetro interno de un tubo o agujero.','El diámetro de un cilindro o el ancho de una pieza.','Diferencias de altura o niveles en piezas mecánicas.'],options=['A. Medidas externas','B. Medidas internas','C. Medida de profundidad','D. Escalonamientos']),
 q('v4','Relaciona cada imagen con lo que mide.','matching',image=fig['vernier-mediciones'],rows=['Imagen izquierda','Imagen central','Imagen derecha'],options=['Medidas internas','Medidas de pared','Exterior']),
 q('v5','Coloca en la imagen las partes del vernier.','image_mark',image=fig['vernier-partes'],mark_labels=True,help='Escribe el nombre de cada parte en la etiqueta y haz clic en su ubicación. Repite para las demás partes.'),
 q('v6','¿Cuántas escalas tiene un vernier? Menciónalas.'),q('v7','Menciona los pasos para el uso correcto del vernier.'),
 q('v8','Escribe V (verdadero) o F (falso) para cada afirmación.','matching',rows=['Se debe guardar el vernier en un estuche seco.','No se le debe aplicar aceites al vernier.','Si el vernier se guarda mojado o sucio, puede oxidarse.','El vernier se puede usar como compás.','No se debe forzar el deslizamiento.','Si se golpea o se deja caer, puede desajustarse o romperse.'],options=['Verdadero','Falso'])]))
(ROOT/'data').mkdir(exist_ok=True)
(ROOT/'data/exams.json').write_text(json.dumps(exams,ensure_ascii=False,indent=2),encoding='utf-8')
print('Recreated',len(exams),'exams;',sum(len(e['questions']) for e in exams),'questions')
