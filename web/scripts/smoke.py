"""Synthetic-only HTTP integration through Next BFF. Requires isolated fake backend.
Never points at the owner's dev DB. No model calls; fake chat must return 503.
"""
import json,sys,time,uuid
from datetime import datetime,timezone,date,timedelta
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[2]
base='http://127.0.0.1:3012'
health=httpx.get('http://127.0.0.1:8012/v1/health').json()
assert health['test_mode'] is True
out=root/'evidence/runs'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-web-bff-smoke');out.mkdir()
steps=[]
def check(name,ok):
 steps.append({'name':name,'passed':bool(ok)})
 assert ok,name
c=httpx.Client(base_url=base,headers={'Origin':base},timeout=130)
def req(method,path,**kw):
 r=c.request(method,'/api/backend'+path,**kw)
 if r.status_code>=400:raise AssertionError(f'{method} {path}: {r.status_code} {r.text[:300]}')
 return r.json() if r.status_code!=204 else None
try:
 check('unauthenticated proxy rejected',c.get('/api/backend/transactions').status_code==401)
 check('cross-origin sign-in rejected',c.post('/api/session',headers={'Origin':'https://example.invalid'},json={'action':'login'}).status_code==403)
 email=f'web-{uuid.uuid4().hex[:10]}@example.test'
 r=c.post('/api/session',json={'action':'signup','email':email,'password':'synthetic-test-password'})
 check('signup via BFF',r.status_code==200)
 check('token absent from JSON; HttpOnly cookie', 'token' not in r.json() and 'httponly' in r.headers.get('set-cookie','').lower())
 me=c.get('/api/session').json();check('identity confirmed and fake mode visible',bool(me.get('user_id')) and me.get('test_mode') is True)
 today=date.today();next_pay=today+timedelta(days=21)
 req('PUT','/me/profile',json={'income_satang':2000000,'income_frequency':'monthly','next_income_date':str(next_pay),'essentials':[]})
 acc=req('GET','/accounts')[0]
 req('POST',f"/accounts/{acc['id']}/balance-observations",json={'amount_satang':1000000,'as_of_date':str(today-timedelta(days=30))})
 for scope in ('photo_processing','auto_import'):
  req('POST','/consents',json={'scope':scope,'version':'synthetic-smoke','params':{'scan_from':'2026-07-01'} if scope=='photo_processing' else {}})
 check('plan and pockets load',bool(req('GET','/plan')['cashflow']) and isinstance(req('GET','/pockets'),list))
 def upload(name):
  p=root/'backend/fixtures/synthetic'/name
  with p.open('rb') as f:r=req('POST','/uploads',files={'image':('upload.png',f,'image/png')},data={'expected_owner_id':me['user_id'],'confirmed_undated':'true'})
  for _ in range(50):
   u=req('GET','/uploads/'+r['upload_id'])
   if u['status'] not in ('received','extracting'):return r['upload_id'],u
   time.sleep(.3)
  raise AssertionError('worker timeout')
 uid,u=upload('slips/slip_003_transfer_out.png');check('upload imported through proxy',u['status']=='imported')
 before=len(req('GET','/transactions'));uid2,u2=upload('slips/slip_003_transfer_out.png')
 check('exact upload counts once',uid==uid2 and len(req('GET','/transactions'))==before)
 uid,u=upload('review_variants/var_bill_no_due_date.png');check('bill enters review',u['status']=='needs_review')
 item=next(x for x in req('GET','/review-items')['items'] if x['upload_id']==uid)
 before=len(req('GET','/transactions'))
 r=req('POST',f"/review-items/{item['id']}/resolve",json={'decision':'accept','fields':{'due_date_text':str(next_pay)}})
 check('bill resolved without expense',bool(r.get('bill_id')) and len(req('GET','/transactions'))==before)
 check('stale resolve not success',c.post('/api/backend/review-items/'+item['id']+'/resolve',json={'decision':'accept'}).status_code==404)
 req('POST','/pockets',json={'name':'Food','categories':['food']})
 proposal=req('POST','/plan/suggest')
 check('proposal has bound approval card',bool(proposal.get('card_hash')) and bool(proposal.get('card')))
 r=req('POST',f"/proposals/{proposal['proposal_id']}/approve",headers={'Idempotency-Key':str(uuid.uuid4())},json={'payload_hash':proposal['payload_hash'],'card_hash':proposal['card_hash']})
 check('explicit approve applies server plan',r.get('status')=='applied' and req('GET','/plan')['plan'] is not None)
 check('fake chat fails honestly rather than fabricating',c.post('/api/backend/chat/messages',json={'text':'What can I spend?'}).status_code==503)
 # Browser fixture uses synthetic account only; never token/key written to evidence.
 private=Path('/private/tmp/pocket-pal-web-browser-fixture.json');private.write_text(json.dumps({'email':email,'password':'synthetic-test-password'}));private.chmod(0o600)
 c.post('/api/session',json={'action':'logout'})
 check('logout removes session',c.get('/api/backend/transactions').status_code==401)
except Exception as e:
 steps.append({'name':'exception','passed':False,'reason':str(e)})
finally:
 manifest={'kind':'Next BFF + real isolated FastAPI/PG synthetic smoke','steps':steps,'passed':sum(x['passed'] for x in steps),'failed':sum(not x['passed'] for x in steps),'uses_mocks':['fake extraction from synthetic fixtures','chat unavailable, expected 503'],'not_tested':['paid Anthropic chat','physical S22 browser','all prototype features']}
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print(json.dumps({'evidence':str(out),'passed':manifest['passed'],'failed':manifest['failed'],'last':steps[-1]},indent=2))
 sys.exit(bool(manifest['failed']))
