const {chromium}=require('/Users/POOH/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');const path=require('path');
(async()=>{
const out=path.resolve(__dirname,'../../evidence/runs',new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d+Z$/,'Z')+'-web-browser-smoke');fs.mkdirSync(out,{recursive:true});
const account=JSON.parse(fs.readFileSync('/private/tmp/pocket-pal-web-browser-fixture.json','utf8'));
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const page=await browser.newPage({viewport:{width:393,height:852}});const errors=[];const steps=[];page.on('pageerror',e=>errors.push(e.message));
try{
await page.goto('http://127.0.0.1:3012/connect');await page.getByLabel('Email',{exact:true}).fill(account.email);await page.getByLabel('Password',{exact:true}).fill(account.password);await page.getByRole('button',{name:'Sign in',exact:true}).click();await page.getByText('Choose how your photos are processed').waitFor();steps.push('sign in');
for(const [route,title] of [['/','Pocket Pal'],['/pockets','Your pockets'],['/activity','Activity'],['/settings','Settings'],['/goal','']]){
await page.goto('http://127.0.0.1:3012'+route);await page.waitForTimeout(1500);
const text=await page.locator('body').innerText();if(!text.includes('TEST MODE'))throw Error('missing test banner '+route);
if(text.includes('Application error'))throw Error('render error '+route);
const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth+1);if(overflow)throw Error('horizontal overflow '+route);
await page.screenshot({path:path.join(out,(route.slice(1)||'chat')+'.png'),fullPage:true});steps.push('render '+route);
}
await page.goto('http://127.0.0.1:3012/');
await page.getByRole('button',{name:'Attach a slip or receipt'}).waitFor();
await page.locator('input[type=file]').setInputFiles(path.resolve(__dirname,'../../backend/fixtures/synthetic/slips/slip_024_transfer_out.png'));
await page.getByLabel('I confirm sending this undated photo').check();
await page.getByRole('button',{name:'Upload photo',exact:true}).click();
await page.getByRole('heading',{name:'Check this photo'}).waitFor({timeout:30000});
await page.screenshot({path:path.join(out,'review.png'),fullPage:true});steps.push('upload and review sheet');
await page.getByPlaceholder('0.00',{exact:true}).fill('120.00');
await page.locator('select').last().selectOption('success');
await page.getByRole('button',{name:'Save record',exact:true}).click();
await page.getByText('Photo reviewed and recorded',{exact:true}).waitFor();steps.push('review confirmation');
await page.goto('http://127.0.0.1:3012/welcome');
await page.getByRole('button',{name:'Set up with my numbers'}).click();
await page.getByLabel('Balance',{exact:true}).fill('10000');
await page.getByRole('button',{name:'Continue',exact:true}).click();
await page.getByLabel('Amount each time',{exact:true}).fill('20000');
await page.getByLabel('Next payday',{exact:true}).fill('2026-11-17');
await page.getByRole('button',{name:'Continue',exact:true}).click();
await page.getByRole('button',{name:'Continue',exact:true}).click();
await page.getByLabel('Safety buffer',{exact:true}).fill('500');
await page.getByRole('button',{name:'Make my plan',exact:true}).click();
await page.getByRole('button',{name:'Approve change',exact:true}).waitFor();
await page.screenshot({path:path.join(out,'setup-proposal.png'),fullPage:true});
await page.getByRole('button',{name:'Approve change',exact:true}).click();
await page.waitForURL('**/pockets');
const plan=await page.evaluate(async()=> (await fetch('/api/backend/plan')).json());
if(plan.plan.buffer_satang!==50000)throw Error('buffer was not applied');
steps.push('setup to approved plan with 500 THB buffer');
if(errors.length)throw Error(errors.join(';'));
}catch(e){errors.push(e.message);}finally{fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({steps,errors,passed:errors.length===0,viewport:'393x852',data:'synthetic only',limitations:['not a physical S22 run','no paid model call','not all interactions tested']},null,2));console.log(out,JSON.stringify({steps,errors}));await browser.close();process.exitCode=errors.length?1:0;}
})();
