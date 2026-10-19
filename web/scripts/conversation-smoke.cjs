// Synthetic browser routing: tests UI state, not live-model quality or device gallery behavior.
const {chromium}=require('/Users/POOH/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
(async()=>{
 const out=path.resolve(__dirname,'../../evidence/runs',new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d+Z$/,'Z')+'-conversation-browser');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page=await browser.newPage({viewport:{width:393,height:852}});const steps=[],errors=[];let owner='synthetic-A',retention=false,rows=[],release=null;
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),p=url.pathname.replace('/api/backend','');let body={};
  if(url.pathname==='/api/session')body={user_id:owner,test_mode:true};
  else if(p==='/me')body={user_id:owner};
  else if(p==='/chat/messages'){
   if(req.method()==='DELETE'){rows=[];body={deleted:true};}
   else if(req.method()==='POST'){
    const text=req.postDataJSON().text;
    if(text==='Delayed question')await new Promise(r=>{release=r;});
    body={reply:'Synthetic remembered answer',cards:[]};
    if(retention)rows.push({id:crypto.randomUUID(),role:'user',content:{text}},{id:crypto.randomUUID(),role:'assistant',content:{text:body.reply}});
   }else body={retention_enabled:retention,messages:rows};
  }else if(p==='/consents'&&req.method()==='POST'){retention=true;body={};}
  else if(p==='/me/profile')body={income:{next_income_date:'2026-11-01'}};
  else if(p==='/plan')body={today:'2026-10-17',cashflow:{available_balance_satang:100000,discretionary_satang:100000,daily_allowance_satang:10000},plan:null,pockets:[]};
  else if(['/pockets','/transactions','/bills','/audit','/consents'].includes(p))body=[];
  else if(p==='/review-items')body={items:[]};
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)});
 });
 try{
  await page.goto('http://127.0.0.1:3013/');await page.getByText('Tab memory only',{exact:false}).waitFor();
  await page.getByLabel('Message',{exact:true}).fill('First question');await page.getByRole('button',{name:'Send',exact:true}).click();await page.getByText('Synthetic remembered answer',{exact:true}).waitFor();
  await page.getByRole('link',{name:'Pockets',exact:true}).click();await page.waitForURL('**/pockets');await page.getByRole('heading',{name:'Your pockets',exact:true,level:1}).waitFor();await page.getByRole('link',{name:'Chat',exact:true}).click();await page.waitForURL('http://127.0.0.1:3013/');await page.getByText('First question',{exact:true}).waitFor();steps.push('Tab navigation retains unsaved messages for same owner');
  await page.getByRole('button',{name:'New chat',exact:true}).click();await page.getByText('First question',{exact:true}).waitFor({state:'hidden'});steps.push('New chat clears local and server conversation');
  await page.getByLabel('Message',{exact:true}).fill('Delayed question');await page.getByRole('button',{name:'Send',exact:true}).click();await page.getByText('Thinking…').waitFor();await page.getByRole('link',{name:'Pockets',exact:true}).click();await page.waitForURL('**/pockets');await page.getByRole('heading',{name:'Your pockets',exact:true,level:1}).waitFor();release();await page.getByRole('link',{name:'Chat',exact:true}).click();await page.waitForURL('http://127.0.0.1:3013/');await page.getByText('Synthetic remembered answer',{exact:true}).waitFor();steps.push('In-flight reply survives tab navigation');
  owner='synthetic-B';await page.getByRole('link',{name:'Pockets',exact:true}).click();await page.waitForURL('**/pockets');await page.getByRole('heading',{name:'Your pockets',exact:true,level:1}).waitFor();await page.getByRole('link',{name:'Chat',exact:true}).click();await page.waitForURL('http://127.0.0.1:3013/');await page.getByText('Tab memory only',{exact:false}).waitFor();if(await page.getByText('Delayed question',{exact:true}).count())throw Error('cross-account conversation leak');steps.push('Account switch clears prior account memory');
  await page.getByRole('button',{name:'Enable memory',exact:true}).click();await page.getByText('Memory on',{exact:false}).waitFor();await page.getByLabel('Message',{exact:true}).fill('Saved question');await page.getByRole('button',{name:'Send',exact:true}).click();await page.getByText('Synthetic remembered answer',{exact:true}).waitFor();await page.reload();await page.getByText('Saved question',{exact:true}).waitFor();steps.push('Explicit retention restores conversation after reload');
  await page.screenshot({path:path.join(out,'synthetic-conversation.png'),fullPage:true});
 }catch(e){errors.push(e.message);}
 fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({passed:!errors.length,steps,errors,data:'synthetic only',backend:'mocked browser routes; separate DB integration run',paid_calls:0},null,2));console.log(out,JSON.stringify({steps,errors}));await browser.close();process.exitCode=errors.length?1:0;
})();
