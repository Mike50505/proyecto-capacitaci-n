// DOM-free renderer checks. These exercise templates, not browser layout.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path'),root=path.resolve(__dirname,'..');
const exams=JSON.parse(fs.readFileSync(path.join(root,'data/exams.json'),'utf8'));
const elements=new Map();const element=()=>({innerHTML:'',textContent:'',style:{},classList:{add(){},remove(){}},scrollIntoView(){}});
const document={querySelector(key){if(!elements.has(key))elements.set(key,element());return elements.get(key)},querySelectorAll(){return[]},addEventListener(){}};
const context=vm.createContext({console,document,window:{addEventListener(){},scrollTo(){}},location:{hash:'#inicio',origin:'http://localhost'},history:{replaceState(){}},sessionStorage:{getItem(){return null},setItem(){},removeItem(){}},setTimeout,clearTimeout,URLSearchParams,crypto:require('node:crypto').webcrypto,fetch:async()=>({ok:true,json:async()=>exams.map(e=>({...e,questions:e.questions.length}))})});
let source=fs.readFileSync(path.join(root,'static/app.js'),'utf8').replace('window.addEventListener(\'hashchange\',route);route();','window.addEventListener(\'hashchange\',route);globalThis.ready=route();');
vm.runInContext(source,context);
(async()=>{
 await context.ready;
 assert.match(elements.get('#app').innerHTML,/Elige tu evaluación/);
 context.seed=exams;
 vm.runInContext('current={exam:seed[1],answers:{},token:"synthetic"};renderAttempt()',context);
 assert.match(elements.get('#app').innerHTML,/data-mark="d5"/);
 assert.match(elements.get('#app').innerHTML,/Tolerancia máxima/);
 vm.runInContext('session={authenticated:true,username:"synthetic"};editorId=null;editorVersion=null;editor={title:"Editor de prueba",description:"",category:"Prueba",duration:20,pass_score:80,instructions:"",questions:Object.keys(typeNames).map(type=>newQuestion(type))};paintEditor()',context);
 assert.match(elements.get('#app').innerHTML,/Tabla de respuestas/);
 assert.match(elements.get('#app').innerHTML,/Calificar automáticamente/);
 for(const exam of exams){context.sample=exam;const html=vm.runInContext('sample.questions.map(q=>answerControl(q,undefined)).join("")',context);assert.equal(typeof html,'string');assert.ok(html.length>200)}
 vm.runInContext('current={exam_title:"Examen",exam_id:"exam-1",participant:{name:"Persona sintética"},summary:{score:null},status:"pending_review",id:1,submitted_at:new Date().toISOString()};renderDone()',context);
 assert.match(elements.get('#app').innerHTML,/pendiente de revisión/);
 console.log('PASS: public catalog, all source question renderers, all nine editor types, image annotations, pending result.');
})().catch(e=>{console.error(e);process.exitCode=1});
