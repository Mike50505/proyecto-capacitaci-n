"""MESA Formación. Python 3.11+, SQLite and ReportLab for PDF exports."""
import argparse, base64, csv, hashlib, hmac, io, json, math, mimetypes, os, re, secrets, sqlite3, time, unicodedata
from datetime import datetime, timezone
from contextlib import contextmanager
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from evaluation_pdf import evaluation_pdf
from exam_document import document_settings
from answer_review import answer_review, normalize

ROOT=Path(__file__).resolve().parent
PRIVATE=Path(os.environ.get('TRAINING_DATA_DIR',ROOT/'private'))
DB=PRIVATE/'capacitacion.sqlite3'
TYPES={'single','multiple','boolean','text','long_text','number','matching','table','image_mark'}
LOGIN_FAILURES={}
START_LIMITS={}

def now():return datetime.now(timezone.utc).isoformat()
def dump(v):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
@contextmanager
def connect():
    c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        with c:yield c
    finally:c.close()
def password_hash(password,salt):return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def initialize():
    PRIVATE.mkdir(parents=True,exist_ok=True)
    with connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,salt TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS exams(id TEXT PRIMARY KEY,draft TEXT NOT NULL,published_version INTEGER,archived INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS versions(exam_id TEXT NOT NULL REFERENCES exams(id),version INTEGER NOT NULL,content TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(exam_id,version));
        CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,exam_id TEXT NOT NULL REFERENCES exams(id),version INTEGER NOT NULL,snapshot TEXT NOT NULL,participant TEXT NOT NULL,answers TEXT NOT NULL DEFAULT '{}',grading TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL,started_at TEXT NOT NULL,submitted_at TEXT,reviewed_at TEXT,reviewed_by INTEGER REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor INTEGER REFERENCES users(id),action TEXT NOT NULL,object_id TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS attempts_exam_date ON attempts(exam_id,submitted_at);
        ''')
        columns={row['name'] for row in c.execute('PRAGMA table_info(users)')}
        if 'role' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'trainer'")
            owner=c.execute("SELECT id FROM users ORDER BY CASE WHEN username IN ('administrator','admin') THEN 0 ELSE 1 END,id LIMIT 1").fetchone()
            if owner:c.execute("UPDATE users SET role='administrator' WHERE id=?",(owner['id'],))
        if 'active' not in columns:c.execute('ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
        if 'full_name' not in columns:c.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
        attempt_columns={row['name'] for row in c.execute('PRAGMA table_info(attempts)')}
        if 'payroll' not in attempt_columns:
            c.execute("ALTER TABLE attempts ADD COLUMN payroll TEXT NOT NULL DEFAULT ''")
            for r in c.execute('SELECT id,participant FROM attempts').fetchall():
                c.execute('UPDATE attempts SET payroll=? WHERE id=?',(json.loads(r['participant']).get('payroll','').strip(),r['id']))
        if 'archived' not in attempt_columns:c.execute('ALTER TABLE attempts ADD COLUMN archived INTEGER NOT NULL DEFAULT 0')
        c.execute('CREATE INDEX IF NOT EXISTS attempts_payroll ON attempts(payroll,exam_id,submitted_at)')
        if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            password=secrets.token_urlsafe(15);salt=secrets.token_hex(16)
            c.execute('INSERT INTO users(username,password_hash,salt,role) VALUES(?,?,?,?)',('admin',password_hash(password,salt),salt,'administrator'))
            (PRIVATE/'primer_acceso.txt').write_text('MESA Formación\nUsuario: admin\nContraseña: '+password+'\nCambia la contraseña desde el panel de administración.\n',encoding='utf-8')
        seed=ROOT/'data/exams.json'
        if seed.exists():
            for content in json.loads(seed.read_text(encoding='utf-8')):
                if c.execute('SELECT 1 FROM exams WHERE id=?',(content['id'],)).fetchone():continue
                validate_exam(content)
                c.execute('INSERT INTO exams VALUES(?,?,1,0,?)',(content['id'],dump(content),now()))
                c.execute('INSERT INTO versions VALUES(?,1,?,?)',(content['id'],dump(content),now()))

def audit(c,user,action,oid,details):c.execute('INSERT INTO audit(actor,action,object_id,details,created_at) VALUES(?,?,?,?,?)',(user,action,str(oid),dump(details),now()))
def clean_text(v,limit=10000):
    if not isinstance(v,str) or len(v)>limit:raise ValueError('Texto inválido o demasiado largo.')
    return v.strip()
def validate_exam(e):
    e['document']=document_settings(e)
    e['title']=clean_text(e.get('title',''),180)
    for key,limit in [('description',3000),('category',100),('instructions',5000)]:e[key]=clean_text(e.get(key,''),limit)
    if not e['title']:raise ValueError('El examen necesita un título.')
    if not isinstance(e.get('questions'),list) or not 1<=len(e['questions'])<=100:raise ValueError('Agrega entre 1 y 100 preguntas.')
    threshold=float(e.get('pass_score',80))
    if not math.isfinite(threshold) or not 0<=threshold<=100:raise ValueError('El mínimo aprobatorio debe estar entre 0 y 100.')
    e['pass_score']=threshold
    seen=set()
    for q in e['questions']:
        qid=q.get('id','')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',qid) or qid in seen:raise ValueError('Identificadores de pregunta inválidos o repetidos.')
        seen.add(qid)
        if q.get('type') not in TYPES:raise ValueError('Tipo de pregunta no válido.')
        q['prompt']=clean_text(q.get('prompt',''),5000)
        if not q['prompt']:raise ValueError('Escribe el enunciado de cada pregunta.')
        p=float(q.get('points',1))
        if not math.isfinite(p) or p<=0 or p>1000:raise ValueError('Los puntos deben ser mayores que cero y hasta 1000.')
        q['points']=p
        for key in ['options','rows','columns']:
            if key in q:
                if not isinstance(q[key],list) or len(q[key])>60:raise ValueError('Lista de opciones inválida.')
                q[key]=[clean_text(v,1000) for v in q[key]]
                if any(not v for v in q[key]) or len(set(q[key]))!=len(q[key]):raise ValueError('Las opciones deben ser únicas y tener texto.')
        if q['type'] in ('single','multiple','matching') and len(q.get('options',[]))<2:raise ValueError('Agrega al menos dos opciones.')
        if q['type'] in ('matching','table') and not q.get('rows'):raise ValueError('Agrega las filas de la pregunta.')
        if q['type']=='table' and not q.get('columns'):raise ValueError('Agrega las columnas de respuesta.')
        if q.get('image') and not re.fullmatch(r'/assets/[a-zA-Z0-9_./-]+',q['image']):raise ValueError('La imagen debe pertenecer al proyecto.')
        if q['type']=='image_mark' and not q.get('image'):raise ValueError('La pregunta de imagen necesita una imagen.')
        if q.get('correct') is not None:
            if empty(q['correct']):raise ValueError('Completa la clave de respuesta o desactiva la calificación automática.')
            validate_answer(q,q['correct'])
            if q['type'] in ['matching','table']:
                expected=set(q['rows']) if q['type']=='matching' else {f'{i}:{j}' for i in range(len(q['rows'])) for j in range(len(q['columns']))}
                if set(q['correct'])!=expected or any(empty(x) for x in q['correct'].values()):raise ValueError('Completa toda la clave de la tabla o relación.')
        if 'tolerance' in q and (not math.isfinite(float(q['tolerance'])) or float(q['tolerance'])<0):raise ValueError('Tolerancia inválida.')
    return e

def public_exam(e):
    result=json.loads(dump(e))
    result['document']=document_settings(result)
    for q in result['questions']:
        for key in ['correct','rubric','tolerance']:q.pop(key,None)
    return result

def empty(v):return v is None or v=='' or v==[] or v=={} or (isinstance(v,dict) and all(empty(x) for x in v.values()))
def validate_answer(q,v):
    if empty(v):return
    typ=q['type']
    if typ in ['text','long_text']:clean_text(v,20000)
    elif typ=='number':
        if isinstance(v,bool) or not math.isfinite(float(v)):raise ValueError('Escribe una cantidad numérica válida.')
    elif typ in ['single','boolean']:
        if v not in (q.get('options') if typ=='single' else ['Verdadero','Falso']):raise ValueError('Selecciona una opción válida.')
    elif typ=='multiple':
        if not isinstance(v,list) or len(v)!=len(set(v)) or any(x not in q['options'] for x in v):raise ValueError('Selección múltiple inválida.')
    elif typ in ['matching','table']:
        if not isinstance(v,dict):raise ValueError('Respuesta de tabla inválida.')
        keys=q['rows'] if typ=='matching' else [f'{i}:{j}' for i in range(len(q['rows'])) for j in range(len(q['columns']))]
        if any(k not in keys for k in v):raise ValueError('La tabla contiene una fila desconocida.')
        for x in v.values():
            clean_text(x,2000)
            if typ=='matching' and x and x not in q['options']:raise ValueError('Relación inválida.')
    elif typ=='image_mark':
        if not isinstance(v,list) or len(v)>20:raise ValueError('Marca hasta 20 puntos en la imagen.')
        for point in v:
            if not isinstance(point,dict) or any(not isinstance(point.get(k),(int,float)) or isinstance(point[k],bool) or not math.isfinite(point[k]) or not 0<=point[k]<=1 for k in ['x','y']):raise ValueError('Marca inválida.')
            label=clean_text(point.get('label',''),200)
            if q.get('mark_labels') and not label:raise ValueError('Escribe una etiqueta para cada marca de la imagen.')

def validate_answers(exam,answers,submit=False):
    if not isinstance(answers,dict):raise ValueError('Respuestas inválidas.')
    known={q['id'] for q in exam['questions']}
    if set(answers)-known:raise ValueError('Hay preguntas desconocidas.')
    missing=[]
    for q in exam['questions']:
        v=answers.get(q['id']);validate_answer(q,v)
        if submit and q.get('required',True):
            incomplete=empty(v)
            if q['type'] in ['matching','table']:
                expected=len(q['rows'])*(len(q['columns']) if q['type']=='table' else 1)
                incomplete=not isinstance(v,dict) or len(v)!=expected or any(empty(x) for x in v.values())
            if incomplete:missing.append(q['id'])
    if missing:raise ValueError('Faltan respuestas obligatorias. Revisa las preguntas marcadas.')

def autograde(exam,answers):
    result={}
    for q in exam['questions']:
        v=answers.get(q['id']);key=q.get('correct');points=q['points']
        if empty(v):result[q['id']]={'points':0,'mode':'auto','feedback':''};continue
        if key is None or q['type']=='image_mark':result[q['id']]={'points':None,'mode':'manual','feedback':''};continue
        typ=q['type']
        if typ=='multiple':ratio=float(set(v)==set(key))
        elif typ=='number':ratio=float(abs(float(v)-float(key))<=float(q.get('tolerance',0)))
        elif typ in ['matching','table']:
            ratio=sum(normalize(v.get(k,''))==normalize(value) for k,value in key.items())/max(len(key),1)
        else:ratio=float(normalize(v)==normalize(key))
        result[q['id']]={'points':round(points*ratio,4),'mode':'auto','feedback':''}
    return result
def summary(exam,grading):
    maximum=sum(q['points'] for q in exam['questions']);pending=sum(grading.get(q['id'],{}).get('points') is None for q in exam['questions'])
    earned=sum(g.get('points') or 0 for g in grading.values());score=round(earned/maximum*100,2) if not pending else None
    return {'earned':round(earned,2),'maximum':maximum,'pending':pending,'score':score,'passed':score>=exam.get('pass_score',80) if score is not None else None}
def attempt_row(r,detail=False):
    exam=json.loads(r['snapshot']);grading=json.loads(r['grading']);p=json.loads(r['participant'])
    result={'id':r['id'],'exam_id':r['exam_id'],'exam_title':exam['title'],'version':r['version'],'participant':p,'archived':bool(r['archived']),'status':r['status'],'started_at':r['started_at'],'submitted_at':r['submitted_at'],'reviewed_at':r['reviewed_at'],'summary':summary(exam,grading) if r['status']!='started' else None}
    if detail:result.update(exam={**exam,'document':document_settings(exam)},answers=json.loads(r['answers']),grading=grading)
    return result

class Handler(BaseHTTPRequestHandler):
    server_version='MesaTraining/1.0'
    def send_pdf(self, data, filename):
        self.send_response(200)
        self.send_header('Content-Type','application/pdf')
        self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.security_headers();self.end_headers();self.wfile.write(data)
    def log_message(self,fmt,*args):print('%s %s'%(self.log_date_time_string(),fmt%args))
    def send_json(self,value,status=200,cookie=None):
        data=dump(value).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.security_headers()
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(data)
    def security_headers(self):
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','same-origin');self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
    def body(self):
        size=int(self.headers.get('Content-Length','0'))
        if size>8_000_000:raise ValueError('El archivo excede el límite permitido.')
        try:return json.loads(self.rfile.read(size) or '{}')
        except (ValueError,UnicodeDecodeError):raise ValueError('Solicitud inválida.')
    def session(self,c):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:return None
        token=cookie.get('mesa_training')
        if not token:return None
        return c.execute('SELECT sessions.*,users.username,users.role,users.full_name FROM sessions JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires>? AND users.active=1',(digest(token.value),time.time())).fetchone()
    def require_admin(self,c,write=False):
        s=self.session(c)
        if not s:raise PermissionError('Inicia sesión para continuar.')
        if write and not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):raise PermissionError('La sesión cambió. Recarga e inténtalo de nuevo.')
        return s
    def check_origin(self):
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'):raise PermissionError('Origen no autorizado.')
    def do_GET(self):self.dispatch('GET')
    def do_POST(self):self.dispatch('POST')
    def do_PUT(self):self.dispatch('PUT')
    def dispatch(self,method):
        try:
            if method!='GET':self.check_origin()
            path=urlparse(self.path).path
            if not path.startswith('/api/'):
                if method!='GET':self.send_error(405);return
                return self.static(path)
            with connect() as c:
                if method!='GET':c.execute('BEGIN IMMEDIATE')
                return self.api(c,method,path,parse_qs(urlparse(self.path).query))
        except PermissionError as e:self.send_json({'error':str(e)},403)
        except (ValueError,KeyError,TypeError) as e:self.send_json({'error':str(e) or 'Datos inválidos.'},400)
        except sqlite3.IntegrityError:self.send_json({'error':'El registro ya existe o la información cambió.'},409)
        except BrokenPipeError:pass
        except Exception as e:
            import traceback;traceback.print_exc();self.send_json({'error':'Ocurrió un problema al procesar la solicitud.'},500)
    def static(self,path):
        if path=='/':target=ROOT/'static/index.html'
        elif path.startswith('/assets/'):target=ROOT/path.lstrip('/')
        elif path.startswith('/static/'):target=ROOT/path.lstrip('/')
        else:target=ROOT/'static/index.html'
        target=target.resolve()
        if not any(target.is_relative_to(ROOT/folder) for folder in ['static','assets/figures','assets/uploads']) or not target.is_file():self.send_error(404);return
        data=target.read_bytes();self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-cache');self.security_headers();self.end_headers();self.wfile.write(data)
    def api(self,c,method,path,params):
        if path=='/api/session' and method=='GET':
            s=self.session(c);return self.send_json({'authenticated':bool(s),'username':s['username'] if s else None,'csrf':s['csrf'] if s else None,'manage_users':bool(s and s['role']=='administrator')})
        if path=='/api/login' and method=='POST':
            data=self.body();ip=self.client_address[0];failures=[x for x in LOGIN_FAILURES.get(ip,[]) if x>time.time()-300]
            if len(failures)>=10:return self.send_json({'error':'Espera unos minutos antes de volver a intentar.'},429)
            u=c.execute('SELECT * FROM users WHERE username=?',(data.get('username',''),)).fetchone()
            if not u or not u['active'] or not hmac.compare_digest(password_hash(str(data.get('password','')),u['salt']),u['password_hash']):
                LOGIN_FAILURES[ip]=failures+[time.time()];return self.send_json({'error':'Usuario o contraseña incorrectos.'},400)
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(digest(token),u['id'],csrf,time.time()+28800));LOGIN_FAILURES.pop(ip,None)
            return self.send_json({'authenticated':True,'username':u['username'],'csrf':csrf,'manage_users':u['role']=='administrator'},cookie=f'mesa_training={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if os.environ.get('TRAINING_SECURE_COOKIE')=='1' else ''))
        if path=='/api/logout' and method=='POST':
            s=self.require_admin(c,True);c.execute('DELETE FROM sessions WHERE token_hash=?',(s['token_hash'],));return self.send_json({'ok':True},cookie='mesa_training=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/')
        if path=='/api/exams' and method=='GET':
            rows=c.execute('SELECT exams.id,versions.content FROM exams JOIN versions ON versions.exam_id=exams.id AND versions.version=exams.published_version WHERE archived=0').fetchall()
            return self.send_json([dict(id=r['id'],**{k:v for k,v in json.loads(r['content']).items() if k in ['title','description','category','duration','source_file','revision']},questions=len(json.loads(r['content'])['questions'])) for r in rows])
        m=re.fullmatch(r'/api/exams/([a-z0-9-]+)',path)
        if m and method=='GET':
            r=c.execute('SELECT versions.* FROM exams JOIN versions ON versions.exam_id=exams.id AND versions.version=exams.published_version WHERE exams.id=? AND archived=0',(m[1],)).fetchone()
            if not r:return self.send_json({'error':'Examen no disponible.'},404)
            return self.send_json(dict(exam=public_exam(json.loads(r['content'])),version=r['version']))
        if path=='/api/attempts' and method=='POST':
            data=self.body();ip=self.client_address[0];starts=[t for t in START_LIMITS.get(ip,[]) if t>time.time()-60]
            if len(starts)>=30:return self.send_json({'error':'Demasiados inicios. Intenta en un minuto.'},429)
            r=c.execute('SELECT versions.* FROM exams JOIN versions ON versions.exam_id=exams.id AND versions.version=exams.published_version WHERE exams.id=? AND archived=0',(data.get('exam_id'),)).fetchone()
            if not r:raise ValueError('Examen no disponible.')
            p=data.get('participant',{});name=clean_text(p.get('name',''),150);kind=p.get('type');payroll=clean_text(p.get('payroll',''),50)
            if len(name)<3 or kind not in ['employee','applicant']:raise ValueError('Completa tu nombre y tipo de participante.')
            if kind=='employee' and not payroll:raise ValueError('Indica tu número de nómina.')
            participant={'name':name,'type':kind,'payroll':payroll,'department':clean_text(p.get('department',''),150)}
            token=secrets.token_urlsafe(32);cur=c.execute('INSERT INTO attempts(token_hash,exam_id,version,snapshot,participant,status,started_at,payroll) VALUES(?,?,?,?,?,?,?,?)',(digest(token),r['exam_id'],r['version'],r['content'],dump(participant),'started',now(),payroll));START_LIMITS[ip]=starts+[time.time()]
            return self.send_json({'token':token,'id':cur.lastrowid},201)
        m=re.fullmatch(r'/api/attempts/([A-Za-z0-9_-]{30,80})(?:/(submit))?',path)
        if m:
            r=c.execute('SELECT * FROM attempts WHERE token_hash=?',(digest(m[1]),)).fetchone()
            if not r or r['archived']:return self.send_json({'error':'Evaluación no encontrada.'},404)
            if method=='GET':
                result=attempt_row(r,True);result['exam']=public_exam(result['exam']);result.pop('grading',None);return self.send_json(result)
            if method in ['PUT','POST']:
                data=self.body()
                if r['status']!='started':
                    if m[2]=='submit':return self.send_json({'status':r['status'],'summary':attempt_row(r)['summary']})
                    raise ValueError('La evaluación ya fue enviada.')
                answers=data.get('answers',{});exam=json.loads(r['snapshot']);validate_answers(exam,answers,m[2]=='submit')
                if m[2]=='submit':
                    grading=autograde(exam,answers);status='pending_review' if summary(exam,grading)['pending'] else 'graded'
                    c.execute('UPDATE attempts SET answers=?,grading=?,status=?,submitted_at=? WHERE id=?',(dump(answers),dump(grading),status,now(),r['id']))
                    return self.send_json({'status':status,'summary':summary(exam,grading)})
                c.execute('UPDATE attempts SET answers=? WHERE id=?',(dump(answers),r['id']));return self.send_json({'saved':True})
        if path.startswith('/api/admin/'):
            s=self.require_admin(c,method!='GET');uid=s['user_id']
            pdf_match=re.fullmatch(r'/api/admin/(results|exams)/([a-z0-9-]+)/pdf',path)
            if pdf_match and method=='GET':
                kind,ident=pdf_match.groups()
                if kind=='results':
                    row=c.execute("SELECT * FROM attempts WHERE id=? AND status<>'started'",(ident,)).fetchone()
                    if not row:return self.send_json({'error':'Resultado no encontrado.'},404)
                    result=attempt_row(row,True)
                    return self.send_pdf(evaluation_pdf(result['exam'],ROOT,result),f'evaluacion-MESA-{result["id"]:05d}.pdf')
                row=c.execute('SELECT draft FROM exams WHERE id=?',(ident,)).fetchone()
                if not row:return self.send_json({'error':'Examen no encontrado.'},404)
                return self.send_pdf(evaluation_pdf(json.loads(row['draft']),ROOT),f'evaluacion-{ident}.pdf')
            if path=='/api/admin/users' or re.fullmatch(r'/api/admin/users/\d+',path):
                if s['role']!='administrator':raise PermissionError('Solo el administrador puede gestionar usuarios.')
                if path=='/api/admin/users' and method=='GET':
                    return self.send_json([dict(r) for r in c.execute('SELECT id,username,full_name,role,active FROM users ORDER BY id')])
                data=self.body();name=clean_text(data.get('full_name',''),150)
                if path=='/api/admin/users' and method=='POST':
                    username=clean_text(data.get('username',''),80)
                    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}',username):raise ValueError('El usuario debe tener entre 3 y 80 letras, números, puntos, guiones o guiones bajos.')
                    if c.execute('SELECT 1 FROM users WHERE lower(username)=lower(?)',(username,)).fetchone():raise ValueError('Ese nombre de usuario ya existe.')
                    password=str(data.get('password',''))
                    if len(password)<10:raise ValueError('Usa una contraseña de al menos 10 caracteres.')
                    salt=secrets.token_hex(16)
                    created=c.execute("INSERT INTO users(username,password_hash,salt,role,full_name) VALUES(?,?,?,'trainer',?)",(username,password_hash(password,salt),salt,name))
                    audit(c,uid,'user_created',created.lastrowid,{'username':username,'role':'trainer'})
                    return self.send_json({'id':created.lastrowid},201)
                if method=='PUT' and path!='/api/admin/users':
                    target_id=int(path.rsplit('/',1)[1]);target=c.execute('SELECT * FROM users WHERE id=?',(target_id,)).fetchone()
                    if not target:return self.send_json({'error':'Usuario no encontrado.'},404)
                    active=data.get('active',bool(target['active']))
                    if not isinstance(active,bool):raise ValueError('Estado inválido.')
                    if target['role']=='administrator' and not active:raise ValueError('La cuenta administradora debe permanecer activa.')
                    c.execute('UPDATE users SET full_name=?,active=? WHERE id=?',(name,active,target_id))
                    password=str(data.get('password',''))
                    if password:
                        if len(password)<10:raise ValueError('Usa una contraseña de al menos 10 caracteres.')
                        salt=secrets.token_hex(16);c.execute('UPDATE users SET password_hash=?,salt=? WHERE id=?',(password_hash(password,salt),salt,target_id))
                    if password or not active:c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(target_id,s['token_hash']))
                    audit(c,uid,'user_updated',target_id,{'active':active,'password_reset':bool(password)})
                    return self.send_json({'ok':True})
                return self.send_json({'error':'Acción no disponible.'},405)
            if path=='/api/admin/password' and method=='POST':
                data=self.body();u=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                if not hmac.compare_digest(password_hash(str(data.get('current','')),u['salt']),u['password_hash']):raise ValueError('La contraseña actual es incorrecta.')
                new=str(data.get('password',''))
                if len(new)<10:raise ValueError('Usa al menos 10 caracteres.')
                salt=secrets.token_hex(16);c.execute('UPDATE users SET password_hash=?,salt=? WHERE id=?',(password_hash(new,salt),salt,uid));c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,s['token_hash']));audit(c,uid,'password_changed',uid,{})
                return self.send_json({'ok':True})
            if path=='/api/admin/exams' and method=='GET':
                result=[]
                for r in c.execute('SELECT * FROM exams ORDER BY updated_at DESC'):
                    e=json.loads(r['draft']);result.append({'id':r['id'],'title':e['title'],'category':e.get('category',''),'questions':len(e['questions']),'published_version':r['published_version'],'archived':bool(r['archived']),'updated_at':r['updated_at'],'manual':sum(q.get('correct') is None for q in e['questions'])})
                return self.send_json(result)
            if path=='/api/admin/exams' and method=='POST':
                e=validate_exam(self.body());eid='exam-'+secrets.token_hex(6);e['id']=eid;c.execute('INSERT INTO exams(id,draft,updated_at) VALUES(?,?,?)',(eid,dump(e),now()));audit(c,uid,'exam_created',eid,{'title':e['title']});return self.send_json({'id':eid},201)
            m=re.fullmatch(r'/api/admin/exams/([a-z0-9-]+)(?:/(publish|archive))?',path)
            if m:
                r=c.execute('SELECT * FROM exams WHERE id=?',(m[1],)).fetchone()
                if not r:return self.send_json({'error':'Examen no encontrado.'},404)
                if method=='GET':return self.send_json({'exam':{**json.loads(r['draft']),'document':document_settings(json.loads(r['draft']))},'published_version':r['published_version'],'archived':bool(r['archived'])})
                if m[2]=='publish' and method=='POST':
                    e=validate_exam(json.loads(r['draft']));version=c.execute('SELECT COALESCE(MAX(version),0)+1 FROM versions WHERE exam_id=?',(m[1],)).fetchone()[0]
                    c.execute('INSERT INTO versions VALUES(?,?,?,?)',(m[1],version,dump(e),now()));c.execute('UPDATE exams SET published_version=?,archived=0,updated_at=? WHERE id=?',(version,now(),m[1]));audit(c,uid,'exam_published',m[1],{'version':version});return self.send_json({'version':version})
                if m[2]=='archive' and method=='POST':
                    c.execute('UPDATE exams SET archived=?,updated_at=? WHERE id=?',(not r['archived'],now(),m[1]));audit(c,uid,'exam_visibility',m[1],{'archived':not r['archived']});return self.send_json({'ok':True})
                if method=='PUT' and not m[2]:
                    e=validate_exam(self.body());e['id']=m[1];c.execute('UPDATE exams SET draft=?,updated_at=? WHERE id=?',(dump(e),now(),m[1]));audit(c,uid,'exam_saved',m[1],{});return self.send_json({'ok':True})
            if path=='/api/admin/upload' and method=='POST':
                data=self.body()
                try:blob=base64.b64decode(data.get('data',''),validate=True)
                except Exception:raise ValueError('Imagen inválida.')
                if not 0<len(blob)<=5_000_000:raise ValueError('La imagen debe pesar hasta 5 MB.')
                ext='.png' if blob.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if blob.startswith(b'\xff\xd8\xff') else None
                if not ext:raise ValueError('Usa una imagen PNG o JPEG.')
                folder=ROOT/'assets/uploads';folder.mkdir(exist_ok=True);name=secrets.token_hex(16)+ext;(folder/name).write_bytes(blob);return self.send_json({'url':'/assets/uploads/'+name})
            if path in ['/api/admin/results','/api/admin/dashboard','/api/admin/export'] and method=='GET':
                archived=params.get('history',['active'])[0]=='archived'
                rows=c.execute("SELECT * FROM attempts WHERE status<>'started' AND archived=? ORDER BY submitted_at DESC",(archived,)).fetchall();result=[]
                counts={}
                for row in rows:
                    p=json.loads(row['participant']);key=(p['type'],row['payroll'].casefold(),row['exam_id'])
                    if row['payroll']:counts[key]=counts.get(key,0)+1
                for row in rows:
                    item=attempt_row(row)
                    item['exam_attempts']=counts.get((item['participant']['type'],row['payroll'].casefold(),row['exam_id']),1)
                    if params.get('payroll') and row['payroll'].casefold()!=params['payroll'][0].strip().casefold():continue
                    if params.get('exam') and item['exam_id']!=params['exam'][0]:continue
                    if params.get('type') and item['participant']['type']!=params['type'][0]:continue
                    if params.get('from') and item['submitted_at'][:10]<params['from'][0]:continue
                    if params.get('to') and item['submitted_at'][:10]>params['to'][0]:continue
                    result.append(item)
                result.sort(key=lambda r:(not bool(r['participant']['payroll']),len(r['participant']['payroll']),r['participant']['payroll'].casefold()))
                if path=='/api/admin/results':return self.send_json(result)
                if path=='/api/admin/dashboard':
                    graded=[r for r in result if r['status']=='graded'];passed=sum(r['summary']['passed'] for r in graded);by_exam={};by_day={}
                    for r in result:
                        group=by_exam.setdefault(r['exam_id'],{'title':r['exam_title'],'count':0,'scores':[]});group['count']+=1
                        if r['status']=='graded':group['scores'].append(r['summary']['score'])
                        day=r['submitted_at'][:10];by_day[day]=by_day.get(day,0)+1
                    people={}
                    for item in result:
                        p=item['participant']
                        if p['type']!='employee' or not p['payroll']:continue
                        person=people.setdefault(p['payroll'].casefold(),{'payroll':p['payroll'],'name':p['name'],'attempts':0,'exams':{},'scores':[],'latest':item['submitted_at']})
                        person['attempts']+=1
                        ex=person['exams'].setdefault(item['exam_id'],{'title':item['exam_title'],'attempts':0});ex['attempts']+=1
                        if item['summary']['score'] is not None:person['scores'].append(item['summary']['score'])
                    by_payroll=[{**p,'exams':list(p['exams'].values()),'average':round(sum(p['scores'])/len(p['scores']),1) if p['scores'] else None} for p in people.values()]
                    by_payroll.sort(key=lambda p:(len(p['payroll']),p['payroll']))
                    return self.send_json({'total':len(result),'pending':sum(r['status']=='pending_review' for r in result),'average':round(sum(r['summary']['score'] for r in graded)/len(graded),1) if graded else None,'pass_rate':round(100*passed/len(graded),1) if graded else None,'graded':len(graded),'employees':sum(r['participant']['type']=='employee' for r in result),'applicants':sum(r['participant']['type']=='applicant' for r in result),'by_payroll':by_payroll,'by_exam':[{'id':key,**value,'average':round(sum(value['scores'])/len(value['scores']),1) if value['scores'] else None} for key,value in by_exam.items()],'by_day':by_day,'recent':sorted(result,key=lambda r:r['submitted_at'],reverse=True)[:6]})
                output=io.StringIO();writer=csv.writer(output);writer.writerow(['Folio','Examen','Versión','Nombre','Participante','Nómina','Departamento','Enviado','Estado','Calificación','Aprobado','Intentos del mismo examen','Eliminado del historial'])
                def safe(v):
                    text=str(v if v is not None else '')
                    return "'"+text if text.lstrip().startswith(('=','+','-','@')) else text
                for r in result:writer.writerow([safe(x) for x in [r['id'],r['exam_title'],r['version'],r['participant']['name'],r['participant']['type'],r['participant']['payroll'],r['participant']['department'],r['submitted_at'],r['status'],r['summary']['score'],'Sí' if r['summary']['passed'] else 'No' if r['summary']['passed'] is False else 'Pendiente',r['exam_attempts'],'Sí' if r['archived'] else 'No']])
                data=('\ufeff'+output.getvalue()).encode('utf-8');self.send_response(200);self.send_header('Content-Type','text/csv; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="resultados-capacitacion.csv"');self.send_header('Content-Length',str(len(data)));self.security_headers();self.end_headers();self.wfile.write(data);return
            m=re.fullmatch(r'/api/admin/results/(\d+)/history',path)
            if m and method=='POST':
                body=self.body();reason=clean_text(body.get('reason',''),2000);archived=body.get('archived')
                if not reason or not isinstance(archived,bool):raise ValueError('Indica el motivo y la acción del historial.')
                r=c.execute("SELECT * FROM attempts WHERE id=? AND status<>'started'",(m[1],)).fetchone()
                if not r:return self.send_json({'error':'Resultado no encontrado.'},404)
                if bool(r['archived'])!=archived:
                    c.execute('UPDATE attempts SET archived=? WHERE id=?',(archived,r['id']))
                    audit(c,uid,'attempt_archived' if archived else 'attempt_restored',r['id'],{'reason':reason,'payroll':r['payroll']})
                return self.send_json({'ok':True,'archived':archived})
            m=re.fullmatch(r'/api/admin/results/(\d+)',path)
            if m:
                r=c.execute('SELECT * FROM attempts WHERE id=? AND status<>?',(m[1],'started')).fetchone()
                if not r:return self.send_json({'error':'Resultado no encontrado.'},404)
                if method=='GET':
                    detail=attempt_row(r,True)
                    detail['answer_review']=answer_review(detail['exam'],detail['answers'],detail['grading'])
                    return self.send_json(detail)
                if method=='POST':
                    if r['archived']:raise ValueError('Restaura la evaluación antes de calificarla.')
                    body=self.body();exam=json.loads(r['snapshot']);grading=json.loads(r['grading'])
                    for q in exam['questions']:
                        g=body.get('grading',{}).get(q['id'])
                        if g is None:continue
                        value=float(g.get('points'))
                        if not math.isfinite(value) or not 0<=value<=q['points']:raise ValueError(f'La puntuación debe estar entre 0 y {q["points"]}.')
                        grading[q['id']]={'points':value,'mode':'manual','feedback':clean_text(g.get('feedback',''),3000)}
                    report=summary(exam,grading);status='pending_review' if report['pending'] else 'graded'
                    c.execute('UPDATE attempts SET grading=?,status=?,reviewed_by=?,reviewed_at=? WHERE id=?',(dump(grading),status,uid,now(),r['id']));audit(c,uid,'attempt_reviewed',r['id'],{'summary':report});return self.send_json({'status':status,'summary':report})
        return self.send_json({'error':'Ruta no encontrada.'},404)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=55290);args=parser.parse_args()
    initialize();print(f'MESA Formación: http://{args.host}:{args.port}',flush=True);print('Acceso inicial: private/primer_acceso.txt',flush=True)
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
