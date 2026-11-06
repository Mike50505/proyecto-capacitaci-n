// Browser integration check against a disposable local database, never the live service.
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),net=require('node:net');
const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const root=path.resolve(__dirname,'..');
async function main(){
 const data=fs.mkdtempSync(path.join(fs.mkdirSync(path.join(root,'tmp'),{recursive:true})||path.join(root,'tmp'),'branding-'));
 const port=await new Promise(resolve=>{const socket=net.createServer();socket.listen(0,'127.0.0.1',()=>{const port=socket.address().port;socket.close(()=>resolve(port))})});
 const base=`http://127.0.0.1:${port}`;
 const python=process.env.TEST_PYTHON||path.join(root,'.venv','Scripts','python.exe');
 const child=spawn(python,['-u','server.py','--port',String(port)],{cwd:root,env:{...process.env,TRAINING_DATA_DIR:data},windowsHide:true,stdio:'ignore'});
 let browser;
 try{
  let ready=false;
  for(let i=0;i<60;i++){try{if((await fetch(base+'/api/session')).ok){ready=true;break}}catch{}await new Promise(resolve=>setTimeout(resolve,200))}
  assert.ok(ready,'Temporary server did not start');
  const password=fs.readFileSync(path.join(data,'primer_acceso.txt'),'utf8').split('Contraseña: ')[1].split('\n')[0].trim();
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const context=await browser.newContext({viewport:{width:1400,height:1000}}),page=await context.newPage();
  page.setDefaultTimeout(15000);
  const login=await context.request.post(base+'/api/login',{data:{username:'admin',password}});assert.equal(login.status(),200);
  const session=await login.json();
  await page.goto(base+'/#edit/exam-2',{waitUntil:'networkidle'});
  await page.locator('[name=document_top_text]').fill('ENCABEZADO DE PRUEBA');
  await page.locator('[name=document_revision_text]').fill('Revision 09');
  await page.locator('[name=document_footer_left]').fill('Fecha de prueba 06/11/2026');
  await page.locator('[name=document_footer_right]').fill('FO-PRUEBA');
  assert.ok((await page.locator('#document-preview').innerText()).includes('ENCABEZADO DE PRUEBA'));
  await page.locator('.document-editor').screenshot({path:path.join(root,'tmp','branding-editor.png')});
  await Promise.all([page.waitForResponse(response=>response.url().endsWith('/publish')&&response.status()===200),page.locator('button[value=publish]').click()]);
  await page.goto(base+'/#exam/exam-2',{waitUntil:'networkidle'});
  assert.ok((await page.locator('.exam-document-header').innerText()).includes('ENCABEZADO DE PRUEBA'));
  await page.locator('#identity [name=name]').fill('Participante de prueba');
  await page.locator('#identity [name=payroll]').fill('TEST-ONLY');
  await page.locator('#identity input[type=checkbox]').check();
  await page.locator('#identity button.primary').click();
  await page.locator('#attempt-form').waitFor();
  assert.ok((await page.locator('.exam-document-footer').innerText()).includes('FO-PRUEBA'));
  assert.equal(await page.locator('.exam-document-header img').evaluate(img=>img.complete&&img.naturalWidth>0),true);
  await page.locator('.exam-document-header').screenshot({path:path.join(root,'tmp','branding-header.png')});
  const pdf=await context.request.get(base+'/api/admin/exams/exam-2/pdf');assert.equal(pdf.status(),200);assert.ok((await pdf.body()).subarray(0,5).equals(Buffer.from('%PDF-')));
  const authHeaders={'X-CSRF-Token':session.csrf};
  const fixture={title:'Desglose de respuestas',pass_score:80,questions:[
   {id:'choice',type:'single',prompt:'Selecciona la opción correcta',points:1,required:true,options:['Respuesta equivocada','Respuesta esperada'],correct:'Respuesta esperada'},
   {id:'matching',type:'matching',prompt:'Relaciona cada número',points:1,required:true,rows:['Uno','Dos','Tres','Cuatro'],options:['1','2','3','4'],correct:{Uno:'1',Dos:'2',Tres:'3',Cuatro:'4'}}
  ]};
  const created=await context.request.post(base+'/api/admin/exams',{headers:authHeaders,data:fixture});assert.equal(created.status(),201);
  const eid=(await created.json()).id;
  assert.equal((await context.request.post(base+`/api/admin/exams/${eid}/publish`,{headers:authHeaders,data:{}})).status(),200);
  const attempt=await (await context.request.post(base+'/api/attempts',{data:{exam_id:eid,participant:{name:'Participante de prueba',type:'employee',payroll:'TEST-REVIEW'}}})).json();
  assert.equal((await context.request.post(base+`/api/attempts/${attempt.token}/submit`,{data:{answers:{choice:'Respuesta equivocada',matching:{Uno:'1',Dos:'2',Tres:'3',Cuatro:'1'}}}})).status(),200);
  await page.goto(base+`/#review/${attempt.id}`,{waitUntil:'networkidle'});
  const wrong=page.locator('.review-question.review-incorrect');
  await page.locator('#review-form').waitFor();
  if(!await wrong.count())console.log(await page.locator('#app').innerText());
  assert.equal(await wrong.count(),1);
  assert.ok((await wrong.locator('.review-option.incorrect').innerText()).includes('Tu respuesta'));
  assert.ok((await wrong.locator('.review-option.correct').innerText()).includes('Respuesta esperada'));
  const partial=page.locator('.review-question.review-partial');
  assert.ok((await partial.locator('.review-breakdown').innerText()).includes('3 de 4'));
  assert.equal(await partial.locator('tr.answer-correct').count(),3);assert.equal(await partial.locator('tr.answer-incorrect').count(),1);
  assert.equal(await partial.locator('tr.answer-incorrect td').last().innerText(),'4');
  await partial.screenshot({path:path.join(root,'tmp','review-partial.png')});
  await wrong.screenshot({path:path.join(root,'tmp','review-wrong.png')});
  await page.goto(base+'/#results',{waitUntil:'networkidle'});
  await page.locator('.result-actions').first().waitFor();
  const group=page.locator('.result-actions').first();
  const boxes=await group.locator('.result-action').evaluateAll(items=>items.map(item=>{const r=item.getBoundingClientRect();return {left:r.left,width:r.width,top:r.top,bottom:r.bottom}}));
  assert.equal(boxes.length,3);assert.ok(boxes.every(box=>Math.abs(box.left-boxes[0].left)<1&&Math.abs(box.width-boxes[0].width)<1));
  assert.ok(boxes[1].top>=boxes[0].bottom+6);assert.ok(boxes[2].top>=boxes[1].bottom+6);
  await group.screenshot({path:path.join(root,'tmp','result-actions.png')});
  await page.setViewportSize({width:390,height:844});
  if(!await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth))console.log(await page.evaluate(()=>[...document.querySelectorAll('body *')].map(e=>({tag:e.tagName,cls:e.className,parent:e.parentElement.className,text:e.tagName==='A'?e.textContent:'',right:Math.round(e.getBoundingClientRect().right),width:Math.round(e.getBoundingClientRect().width)})).filter(e=>e.right>window.innerWidth+1).slice(0,25)));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
  console.log('PASS: branding, publishing, PDF, wrong answer in red, correct solution, 3/4 matching breakdown and mobile layout.');
 }finally{if(browser)await browser.close();child.kill();}
}
main().catch(error=>{console.error(error);process.exitCode=1});
