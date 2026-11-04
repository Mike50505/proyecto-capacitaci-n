// DOM-free renderer checks. These exercise templates, not browser layout.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const path=require('node:path'),root=path.resolve(__dirname,'..');
const exams=JSON.parse(fs.readFileSync(path.join(root,'data/exams.json'),'utf8'));
const listeners={};const elements=new Map();const element=()=>({innerHTML:'',textContent:'',style:{},classList:{add(){},remove(){}},scrollIntoView(){},close(){},showModal(){}});
const document={querySelector(key){if(!elements.has(key))elements.set(key,element());return elements.get(key)},querySelectorAll(){return[]},addEventListener(name,callback){listeners[name]=callback}};
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
 assert.doesNotMatch(vm.runInContext('adminLayout("", "dashboard")',context),/href="#users"/);
 vm.runInContext('session.manage_users=true',context);
 assert.match(vm.runInContext('adminLayout("", "dashboard")',context),/href="#users"/);
 for(const exam of exams){context.sample=exam;const html=vm.runInContext('sample.questions.map(q=>answerControl(q,undefined)).join("")',context);assert.equal(typeof html,'string');assert.ok(html.length>200)}
 vm.runInContext('current={exam_title:"Examen",exam_id:"exam-1",participant:{name:"Persona sintética"},summary:{score:null},status:"pending_review",id:1,submitted_at:new Date().toISOString()};renderDone()',context);
 assert.match(elements.get('#app').innerHTML,/pendiente de revisión/);
 // HTML forms expose named controls as properties: input[name=id] shadows form.id.
 const calls=[];
 context.FormData=class{constructor(form){this.form=form}*[Symbol.iterator](){yield* Object.entries(this.form.values)}};
 context.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>options.method==='POST'?{id:42}:[{id:42,username:'capacitacion.ramos',full_name:'Alicia Reyes',role:'trainer',active:1}]}};
 vm.runInContext('session={authenticated:true,username:"administrator",manage_users:true,csrf:"test"}',context);
 const form={id:{value:''},getAttribute:name=>name==='id'?'user-form':null,values:{id:'',username:'capacitacion.ramos',full_name:'Alicia Reyes',password:'SyntheticPassword2026'}};
 let prevented=false;
 await listeners.submit({target:form,preventDefault(){prevented=true},submitter:{disabled:false}});
 assert.ok(prevented);assert.equal(calls[0]?.url,'/api/admin/users');assert.equal(calls[0]?.options.method,'POST');
 assert.equal(JSON.parse(calls[0].options.body).username,'capacitacion.ramos');
 assert.match(elements.get('#app').innerHTML,/Alicia Reyes/);
 console.log('PASS: public catalog, all source question renderers, all nine editor types, image annotations, pending result.');
})().catch(e=>{console.error(e);process.exitCode=1});
