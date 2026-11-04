import sys,tempfile,threading,unittest,json,urllib.request,urllib.error,http.cookiejar
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server

class PortalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();server.PRIVATE=Path(cls.tmp.name);server.DB=server.PRIVATE/'test.sqlite3';server.initialize()
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start();cls.base='http://127.0.0.1:'+str(cls.http.server_port)
        cls.password=(server.PRIVATE/'primer_acceso.txt').read_text(encoding='utf-8').split('Contraseña: ')[1].splitlines()[0]
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
    def setUp(self):
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf=''
    def request(self,path,method='GET',data=None,csrf=True):
        headers={'Content-Type':'application/json','Origin':self.base}
        if self.csrf and csrf:headers['X-CSRF-Token']=self.csrf
        request=urllib.request.Request(self.base+'/api'+path,data=json.dumps(data).encode() if data is not None else None,method=method,headers=headers)
        try:
            with self.client.open(request) as response:
                content=response.read().decode('utf-8-sig')
                return response.status,json.loads(content) if response.headers.get('Content-Type','').startswith('application/json') else content
        except urllib.error.HTTPError as exc:return exc.code,json.loads(exc.read())
    def login(self):
        code,data=self.request('/login','POST',{'username':'admin','password':self.password});self.assertEqual(code,200);self.csrf=data['csrf']
    def new_exam(self,title='Test',questions=None):
        e={'title':title,'category':'Prueba','description':'Prueba temporal','instructions':'Responde','pass_score':80,'questions':questions or [{'id':'q1','prompt':'Elige una','type':'single','points':2,'required':True,'options':['A','B'],'correct':'B'},{'id':'q2','prompt':'Explica','type':'long_text','points':3,'required':True,'correct':None}]}
        code,data=self.request('/admin/exams','POST',e);self.assertEqual(code,201,data);eid=data['id'];self.assertEqual(self.request('/admin/exams/'+eid+'/publish','POST',{})[0],200);return eid,e
    def start(self,eid,name='Participante sintético'):
        code,data=self.request('/attempts','POST',{'exam_id':eid,'participant':{'name':name,'type':'employee','payroll':'TEST-001','department':'Pruebas'}});self.assertEqual(code,201,data);return data
    def test_01_seed_and_no_public_keys(self):
        code,exams=self.request('/exams');self.assertEqual(code,200);self.assertEqual(len([x for x in exams if x['id'] in {f'exam-{i}' for i in range(1,7)}]),6)
        exam=self.request('/exams/exam-5')[1]['exam'];self.assertEqual(len(exam['questions']),10);self.assertTrue(all('correct' not in q and 'rubric' not in q for q in exam['questions']))
    def test_admin_requires_session_and_csrf(self):
        self.assertEqual(self.request('/admin/results')[0],403);self.login();self.assertEqual(self.request('/admin/exams','POST',{},csrf=False)[0],403)
    def test_submit_review_dashboard_and_idempotence(self):
        self.login();eid,e=self.new_exam();attempt=self.start(eid);token=attempt['token'];answers={'q1':'B','q2':'Respuesta de prueba'}
        self.assertEqual(self.request('/attempts/'+token,'PUT',{'answers':answers})[0],200)
        first=self.request('/attempts/'+token+'/submit','POST',{'answers':answers});self.assertEqual(first[1]['status'],'pending_review');self.assertEqual(first[1]['summary']['earned'],2)
        repeat=self.request('/attempts/'+token+'/submit','POST',{'answers':{}});self.assertEqual(repeat[1],first[1])
        self.assertEqual(self.request('/attempts/'+token,'PUT',{'answers':{}})[0],400)
        detail=self.request('/admin/results/'+str(attempt['id']))[1];self.assertEqual(detail['grading']['q1']['points'],2)
        bad=self.request('/admin/results/'+str(attempt['id']),'POST',{'grading':{'q2':{'points':4}}});self.assertEqual(bad[0],400)
        reviewed=self.request('/admin/results/'+str(attempt['id']),'POST',{'grading':{'q2':{'points':3,'feedback':'Correcta'}}});self.assertEqual(reviewed[1]['summary']['score'],100)
        dashboard=self.request('/admin/dashboard?exam='+eid)[1];self.assertEqual(dashboard['total'],1);self.assertEqual(dashboard['pending'],0);self.assertEqual(dashboard['average'],100)
        public=self.request('/attempts/'+token)[1];self.assertNotIn('grading',public);self.assertTrue(all('correct' not in q for q in public['exam']['questions']))
    def test_versions_preserve_attempts(self):
        self.login();eid,e=self.new_exam();attempt=self.start(eid);e['title']='Versión modificada';e['questions'][0]['correct']='A';self.request('/admin/exams/'+eid,'PUT',e);self.request('/admin/exams/'+eid+'/publish','POST',{})
        old=self.request('/attempts/'+attempt['token'])[1];self.assertEqual(old['exam_title'],'Test');self.assertEqual(old['version'],1)
        submitted=self.request('/attempts/'+attempt['token']+'/submit','POST',{'answers':{'q1':'B','q2':'Texto'}})[1];self.assertEqual(submitted['summary']['earned'],2)
    def test_required_and_unrecognized_options(self):
        self.login();eid,e=self.new_exam();attempt=self.start(eid);base='/attempts/'+attempt['token']
        self.assertEqual(self.request(base+'/submit','POST',{'answers':{'q1':'B'}})[0],400)
        self.assertEqual(self.request(base,'PUT',{'answers':{'q1':'NO EXISTE'}})[0],400)
    def test_table_and_marks_validation(self):
        table={'id':'t','type':'table','rows':['A','B'],'columns':['Valor'],'prompt':'Tabla','required':True,'points':1}
        with self.assertRaises(ValueError):server.validate_answers({'questions':[table]},{'t':{'0:0':'1'}},True)
        mark={'id':'m','type':'image_mark','prompt':'Marca','required':True,'points':1,'mark_labels':True}
        with self.assertRaises(ValueError):server.validate_answer(mark,[{'x':1.2,'y':0.2}])
        with self.assertRaises(ValueError):server.validate_answer(mark,[{'x':0.2,'y':0.2}])
        server.validate_answer(mark,[{'x':0.2,'y':0.3,'label':'Mordaza'}])
    def test_csv_formula_protection(self):
        self.login();eid,e=self.new_exam();attempt=self.start(eid,'=SUM(1,2)');self.request('/attempts/'+attempt['token']+'/submit','POST',{'answers':{'q1':'B','q2':'Texto'}})
        code,data=self.request('/admin/export?exam='+eid);self.assertEqual(code,200);self.assertIn("'=SUM",data)
    def test_employee_payroll_required(self):
        self.assertEqual(self.request('/attempts','POST',{'exam_id':'exam-5','participant':{'name':'Test empleado','type':'employee','payroll':''}})[0],400)
    def test_archive_removes_public_entry(self):
        self.login();eid,e=self.new_exam();self.request('/admin/exams/'+eid+'/archive','POST',{});self.assertEqual(self.request('/exams/'+eid)[0],404)
    def test_draft_persists_and_is_not_published(self):
        self.login();e={'title':'Borrador persistente','category':'Prueba','questions':[{'id':'q','type':'text','prompt':'Pregunta','points':1,'correct':None}]};code,data=self.request('/admin/exams','POST',e);self.assertEqual(code,201);self.assertEqual(self.request('/exams/'+data['id'])[0],404)
        with server.connect() as connection:self.assertEqual(json.loads(connection.execute('SELECT draft FROM exams WHERE id=?',(data['id'],)).fetchone()[0])['title'],e['title'])
    def test_automatic_types(self):
        questions=[{'id':'n','type':'number','points':2,'correct':25.4,'tolerance':0.01},{'id':'m','type':'multiple','points':2,'correct':['A','C']},{'id':'r','type':'matching','points':2,'correct':{'uno':'A','dos':'B'}}]
        g=server.autograde({'questions':questions},{'n':'25.405','m':['C','A'],'r':{'uno':'A','dos':'A'}});self.assertEqual([g[x]['points'] for x in ['n','m','r']],[2,2,1])
    def test_origin_rejected(self):
        req=urllib.request.Request(self.base+'/api/login',data=b'{}',headers={'Origin':'https://example.invalid','Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:self.client.open(req)
        self.assertEqual(caught.exception.code,403)

if __name__=='__main__':unittest.main()
