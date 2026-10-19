// UI-only fixtures: no backend, personal data, or model calls. Real API accounting has separate integration tests.
const {chromium}=require('/Users/POOH/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
(async()=>{
 const out=path.resolve(__dirname,'../../evidence/runs',new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d+Z$/,'Z')+'-phase1-browser');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const page=await browser.newPage({viewport:{width:393,height:852}});const steps=[],errors=[];let approved=false,requested;
 page.on('pageerror',e=>errors.push(e.message));
 const pocket=(id,name,amount)=>({pocket_id:id,name,allocation_satang:amount,spent_confirmed_satang:12000,spent_predicted_satang:0});
 await page.route('**/api/**',async route=>{
  const p=new URL(route.request().url()).pathname;let body;
  if(p==='/api/session')body={user_id:'synthetic',test_mode:true};
  else if(p.endsWith('/me/profile'))body={income:{next_income_date:'2026-11-01'}};
  else if(p.endsWith('/me'))body={user_id:'synthetic'};
  else if(p.endsWith('/insights'))body={recommendations:[]};
  else if(p.endsWith('/spending'))body={total_satang:12000,excluded_unresolved_count:0,unlinked_refunds_satang:0};
  else if(p.endsWith('/pockets'))body=[{pocket_id:'food',name:'Food',categories:['food']},{pocket_id:'other',name:'Other',categories:['other']}];
  else if(p.endsWith('/plan'))body={today:'2026-10-17',cashflow:{available_balance_satang:1000000,discretionary_satang:500000,daily_allowance_satang:33333,shortage_satang:0},plan:{id:'plan',period_start:'2026-10-17',period_end:'2026-11-01'},pockets:[pocket('food','Food',approved?310000:300000),pocket('other','Other',approved?190000:200000)]};
  else if(p.endsWith('/chat/messages'))body={reply:'## สรุปงบของคุณ\n\nเหลือ **฿5,000.00**\n\n- Food: ฿3,000\n- Other: ฿2,000\n\n| Pocket | Remaining |\n| --- | --- |\n| Food | ฿3,000 |\n| Other | ฿2,000 |\n\n<script>window.pwned=true</script>\n\n![tracker](https://example.invalid/tracker.png)\n\n[unsafe](javascript:alert(1))\n\n[Reference](https://example.com)',cards:[]};
  else if(p.endsWith('/plan/tradeoff')){requested=route.request().postDataJSON();body={proposal_id:'preview',status:'pending',kind:'budget_plan',payload:{},payload_hash:'hash',card_hash:'card',actions:[{action:'approve'}],card:{summary:{text:'Increase Food by ฿100.00'},changes:[{name:'Food',allocation_before_satang:300000,allocation_after_satang:310000},{name:'Other',allocation_before_satang:200000,allocation_after_satang:190000}],warnings:[],uncertainty:[],assumptions:[],not_computed:[]}};}
  else if(p.endsWith('/proposals/preview/approve')){approved=true;body={status:'approved'};}
  else {errors.push('Unexpected API '+p);body={};}
  await route.fulfill({json:body});
 });
 try{
  await page.goto('http://127.0.0.1:3013/');await page.getByLabel('Message',{exact:true}).fill('สรุปงบให้หน่อย');await page.getByRole('button',{name:'Send',exact:true}).click();
  const reply=page.getByTestId('chat-reply');await reply.locator('table').waitFor();
  assert.equal(await reply.locator('strong').innerText(),'฿5,000.00');assert.equal(await reply.locator('li').count(),2);assert.equal(await reply.locator('h2').innerText(),'สรุปงบของคุณ');
  steps.push('Thai Markdown heading, bold, bullets and GFM table render as elements');
  assert.equal(await reply.locator('script,img').count(),0);assert.equal(await page.evaluate(()=>window.pwned),undefined);assert.equal(await reply.locator('a[href^="javascript:"]').count(),0);
  assert.equal(await reply.getByRole('link',{name:'Reference'}).getAttribute('rel'),'noopener noreferrer');steps.push('Raw HTML, remote images and javascript links disabled; external link isolated');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await page.screenshot({path:path.join(out,'chat.png'),fullPage:true});steps.push('393px mobile chat has no page overflow');
  await page.goto('http://127.0.0.1:3013/pockets');await page.getByTestId('pocket-period').waitFor();await page.getByLabel('Pocket to increase').selectOption('food');await page.getByLabel('Increase by (THB)').fill('100.00');await page.getByRole('button',{name:'Preview changes'}).click();await page.getByRole('button',{name:'Approve change',exact:true}).waitFor();
  assert.deepEqual(requested,{pocket_id:'food',increase_satang:10000});assert.equal(approved,false);steps.push('Pocket preview sends integer satang and does not approve automatically');await page.screenshot({path:path.join(out,'pocket-preview.png'),fullPage:true});
  await page.getByRole('button',{name:'Approve change',exact:true}).click();await page.waitForFunction(()=>document.body.innerText.includes('3,100'));assert.equal(approved,true);steps.push('Explicit approval refreshes pocket values');
 }catch(e){errors.push(e.stack);}finally{
 fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({passed:!errors.length,steps,errors,data:'synthetic HTTP fixtures only',paid_calls:0,limitations:['UI test with mocked API, not real model or real backend','not physical S22']},null,2));console.log(out,JSON.stringify({steps,errors}));await browser.close();process.exitCode=errors.length?1:0;
 }
})();
