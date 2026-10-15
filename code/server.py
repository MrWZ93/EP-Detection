import concurrent.futures,hashlib,json,os,pathlib,secrets,threading,time,uuid
import httpx
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from store import Store,Conflict
import source
VERSION='1.0.0-preview.2'
PROJECT_URL='https://zaxptwjwbwossbueqqwt.supabase.co'

class Desktop:
 def __init__(self,state,assets,picker=None,port=8780):
  self.store=Store(pathlib.Path(state)/'annotations.sqlite3');self.assets=pathlib.Path(assets);self.picker=picker;self.port=port;self.secret=secrets.token_urlsafe(32);self.files={};self.opened={};self.inventory={'running':False,'files':[],'errors':[]};self.token=None;self.account=None;self.lock=threading.Lock();self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=2);self.jobs={}
  configfile=self.assets.parent/'cloud_config.json';self.cloud=json.loads(configfile.read_text()) if configfile.exists() else {'publishable_key':'','provider':'email'}
  if self.cloud.get('url',PROJECT_URL)!=PROJECT_URL:raise ValueError('Unexpected cloud project')
 def owner(self):return self.account['id'] if self.account else (self.store.get('last_account') or 'local:'+self.store.get('device'))
 def root(self):
  p=self.store.get('root')
  if not p:raise ValueError('Choose a local data folder first')
  return pathlib.Path(p)
 def scan(self):
  root=self.root();profile_errors=[]
  try:self.discover_profile(root)
  except (ValueError,OSError) as e:
   self.store.set('dataset_profile',{});profile_errors=[{'path':'ep-dataset-profile.json','reason':'Profile not applied: '+str(e)}]
  self.inventory={'running':True,'files':[],'errors':[]};self.files={};self.opened={}
  def work():
   found=[];errors=profile_errors.copy()
   def walk_error(e):errors.append({'path':str(e.filename),'reason':type(e).__name__})
   for directory,dirs,files in os.walk(root,followlinks=False,onerror=walk_error):
    dirs[:]=sorted(x for x in dirs if not (pathlib.Path(directory)/x).is_symlink())
    for name in sorted(files):
     p=pathlib.Path(directory)/name
     if p.suffix.lower()!='.tdms':continue
     rel=p.relative_to(root).as_posix();id=hashlib.sha256(rel.encode()).hexdigest()
     try:
      if p.is_symlink():raise ValueError('Symbolic links are excluded')
      entry={'id':id,'path':rel,'name':name,'size':p.stat().st_size,'status':'unopened'};self.files[id]=rel;found.append(entry)
     except Exception as e:errors.append({'path':rel,'reason':str(e)})
    self.inventory={'running':True,'files':found.copy(),'errors':errors.copy()}
   self.inventory={'running':False,'files':found,'errors':errors}
  self.pool.submit(work)
 def discover_profile(self,root):
  path=pathlib.Path(root)/'ep-dataset-profile.json'
  if not path.is_file():return
  if path.is_symlink() or path.stat().st_size>2000000:raise ValueError('Dataset sidecar is invalid or too large')
  p=json.loads(path.read_text());validate_profile(p)
  # Coordinator-provided sidecar is data only; application requires content-hash match.
  self.store.set('dataset_profile',p)
 def path(self,id):
  if id not in self.files:raise ValueError('File is not in this folder inventory')
  return source.resolve(self.root(),self.files[id])
 def open(self,id):
  p=self.path(id);sha,fp=source.sha256(p);meta=source.metadata(p)
  if source.fingerprint(p)!=fp:raise source.SourceChanged('Source changed while opening')
  sid=self.store.source(sha,self.files[id],meta)
  profile=self.store.get('dataset_profile',{})
  if sha in profile.get('source_sha256',[]):
   meta['dataset_sample_rate']=profile['sample_rate'];meta['sampling_basis']=profile['basis'];meta['sampling_source']='user-confirmed dataset profile'
   if meta['fs'] and abs(meta['fs']-profile['sample_rate'])>1e-6:meta['sampling_conflict']=True
  obj={'id':id,'source_id':sid,'sha256':sha,'fingerprint':fp,'metadata':meta,'path':self.files[id],'hints':source.hints(self.files[id])};self.opened[id]=obj
  return obj
 def opened_file(self,id):
  o=self.opened.get(id)
  if not o:raise ValueError('Open the source first')
  if source.fingerprint(self.path(id))!=o['fingerprint']:raise source.SourceChanged('Source changed; reopen as a new version')
  return o
 def verify(self,token):
  if not self.cloud.get('publishable_key'):raise ValueError('Cloud deployment is not configured in this preview')
  r=httpx.get(PROJECT_URL+'/auth/v1/user',headers={'apikey':self.cloud['publishable_key'],'Authorization':'Bearer '+token},timeout=20);r.raise_for_status();u=r.json();uuid.UUID(u['id']);return {'id':u['id'],'email':u.get('email','')}
 def sync(self):
  if not self.token or not self.account:raise ValueError('Sign in before cloud sync; local changes remain safe')
  user=self.verify(self.token)
  if user['id']!=self.account['id']:raise ValueError('Account changed; sign in again')
  owner=user['id'];synced=0
  for item in self.store.pending(owner):
   if item['status']=='conflict':break
   try:
    r=httpx.post(PROJECT_URL+'/rest/v1/rpc/ep_save_revision',headers={'apikey':self.cloud['publishable_key'],'Authorization':'Bearer '+self.token},json={'p':json.loads(item['body'])},timeout=30)
    if r.status_code in [409,400]:
     self.store.sync_result(owner,item['id'],'conflict','Server rejected this revision. Export and resolve with an administrator; local revisions are retained.');break
    r.raise_for_status();ack=r.json()
    if ack.get('operation_id')!=item['id'] or ack.get('revision')!=json.loads(item['body'])['revision']:raise ValueError('Unexpected acknowledgement')
    self.store.sync_result(owner,item['id'],'synced');synced+=1
   except Exception as e:
    self.store.sync_result(owner,item['id'],'pending',type(e).__name__+': retry when connected');break
  return {'synced':synced,'remaining':len(self.store.pending(owner))}

def validate_profile(p):
 import math,re
 if set(p)!={'schema','sample_rate','basis','source_sha256'} or p['schema']!='ep-dataset-profile-v1':raise ValueError('Invalid dataset profile schema')
 if type(p['sample_rate']) not in [int,float] or not math.isfinite(p['sample_rate']) or p['sample_rate']<=0 or not isinstance(p['basis'],str) or not p['basis'].strip():raise ValueError('Sampling rate and evidence basis required')
 if not isinstance(p['source_sha256'],list) or not p['source_sha256'] or any(not isinstance(x,str) or not re.fullmatch('[a-f0-9]{64}',x) for x in p['source_sha256']):raise ValueError('Profile must identify confirmed source contents')

def cloud_admin(d):
 if not d.token or not d.account:raise ValueError('Administrator sign-in required')
 user=d.verify(d.token)
 headers={'apikey':d.cloud['publishable_key'],'Authorization':'Bearer '+d.token}
 r=httpx.get(PROJECT_URL+'/rest/v1/ep_members',headers=headers,params={'user_id':'eq.'+user['id'],'select':'role'},timeout=20);r.raise_for_status()
 if not any(x['role']=='admin' for x in r.json()):raise ValueError('This account is not a study administrator')
 return headers

def cloud_rows(d,table,headers):
 rows=[]
 while True:
  r=httpx.get(PROJECT_URL+'/rest/v1/'+table,headers=headers,params={'select':'*','order':'created_at.asc','offset':len(rows),'limit':1000},timeout=30);r.raise_for_status();page=r.json();rows.extend(page)
  if len(page)<1000:return rows

def create_app(d):
 app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
 @app.middleware('http')
 async def guard(request:Request,call_next):
  if request.headers.get('host')!=f'127.0.0.1:{d.port}':return JSONResponse({'error':'Invalid local host'},403)
  if request.url.path.startswith('/api/'):
   if not secrets.compare_digest(request.headers.get('x-ep-session',''),d.secret):return JSONResponse({'error':'Open the application from its launcher'},403)
   origin=request.headers.get('origin')
   if origin and origin!=f'http://127.0.0.1:{d.port}':return JSONResponse({'error':'Cross-origin request rejected'},403)
   if request.method=='POST':
    body=await request.body()
    if len(body)>1000000:return JSONResponse({'error':'Request too large'},413)
  response=await call_next(request)
  response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer'
  response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' "+PROJECT_URL+"; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
  return response
 @app.exception_handler(ValueError)
 async def invalid(_,e):return JSONResponse({'error':str(e)},409 if isinstance(e,Conflict) else 422)
 @app.exception_handler(httpx.HTTPError)
 async def network(_,e):return JSONResponse({'error':'Cloud request failed; local revisions are retained. '+type(e).__name__},502)
 @app.get('/')
 def home():return FileResponse(d.assets/'index.html')
 app.mount('/assets',StaticFiles(directory=d.assets),name='assets')
 @app.get('/api/status')
 def status():
  owner=d.owner();return {'version':VERSION,'root':d.store.get('root'),'owner':owner,'name':d.store.get('name:'+owner,''),'account':d.account,'offline_identity':d.store.get('last_account'),'pending':len(d.store.pending(owner)),'cloud_enabled':bool(d.cloud.get('publishable_key')),'cloud_config':{'enabled':bool(d.cloud.get('publishable_key')),'url':PROJECT_URL,'project_ref':'zaxptwjwbwossbueqqwt','publishable_key':d.cloud.get('publishable_key',''),'provider':d.cloud.get('provider','email')}}
 @app.post('/api/folder')
 def folder():
  if d.inventory['running']:raise ValueError('Wait for the current scan')
  if not d.picker:raise ValueError('Native folder dialog is unavailable in headless mode')
  path=d.picker('folder')
  if path:d.store.set('root',str(pathlib.Path(path).resolve()));d.scan()
  return {'root':d.store.get('root')}
 @app.post('/api/dataset-profile')
 def dataset_profile():
  if not d.picker:raise ValueError('Native profile picker unavailable in headless mode')
  path=d.picker('profile')
  if not path:return {'cancelled':True}
  p=pathlib.Path(path)
  if p.stat().st_size>2000000:raise ValueError('Profile too large')
  profile=json.loads(p.read_text());validate_profile(profile);d.store.set('dataset_profile',profile)
  return {'matched_hashes':len(profile['source_sha256']),'sample_rate':profile['sample_rate'],'basis':profile['basis']}
 @app.post('/api/rescan')
 def rescan():
  if not d.inventory['running']:d.scan()
  return {'ok':True}
 @app.get('/api/files')
 def files():return d.inventory
 @app.post('/api/profile')
 async def profile(r:Request):
  b=await r.json();name=b.get('name','').strip()
  if not name or len(name)>100:raise ValueError('Enter your name (1–100 characters)')
  d.store.set('name:'+d.owner(),name);return {'name':name}
 @app.post('/api/login')
 async def login(r:Request):
  b=await r.json();u=d.verify(b['token']);d.account=u;d.token=b['token'];d.store.set('last_account',u['id']);return {'account':u}
 @app.post('/api/logout')
 def logout():d.token=None;d.account=None;d.store.set('last_account',None);return {'ok':True}
 @app.post('/api/open')
 async def open_file(r:Request):
  b=await r.json();id=b['id'];job=str(uuid.uuid4());d.jobs[job]=d.pool.submit(d.open,id);return {'job':job}
 @app.get('/api/job/{id}')
 def job(id:str):
  future=d.jobs.get(id)
  if not future:raise ValueError('Unknown loading job')
  if not future.done():return {'done':False}
  try:return {'done':True,'result':future.result()}
  finally:d.jobs.pop(id,None)
 @app.get('/api/wave/{id}')
 def wave(id:str,start:int=0,end:int|None=None,calibrated:bool=False):
  o=d.opened_file(id);return source.waveform(d.path(id),o['fingerprint'],start,end,divisor=10 if calibrated else None)
 @app.get('/api/assessments/{id}')
 def assessments(id:str):return d.store.list(d.owner(),d.opened_file(id)['source_id'])
 @app.post('/api/assessment')
 async def new(r:Request):
  b=await r.json();o=d.opened_file(b['file_id']);return d.store.start(d.owner(),o['source_id'],b['id'])
 @app.post('/api/save')
 async def save(r:Request):
  b=await r.json();o=d.opened_file(b['file_id']);a=d.store.assessment(d.owner(),b['assessment_id'])
  if a['source_id']!=o['source_id']:raise ValueError('Assessment source version mismatch')
  if o['metadata'].get('sampling_conflict') and (not b['payload'].get('sample_rate') or b['payload'].get('sampling_basis')==o['metadata'].get('sampling_basis')):raise ValueError('Resolve the conflicting sampling rates with a new verification basis before saving')
  if not d.store.get('name:'+d.owner()):raise ValueError('Enter your reviewer name first')
  return d.store.save(d.owner(),a['id'],b['operation_id'],b['base_revision'],b['payload'],b.get('final',False))
 @app.post('/api/sync')
 def sync():return d.sync()
 @app.get('/api/admin')
 def admin_snapshot():
  headers=cloud_admin(d);return {'revisions':cloud_rows(d,'ep_revisions',headers),'decisions':cloud_rows(d,'ep_decisions',headers)}
 @app.post('/api/admin/decision')
 async def admin_decision(r:Request):
  from admin import adjudicate
  headers=cloud_admin(d);body=await r.json();records=cloud_rows(d,'ep_revisions',headers);result=adjudicate(d,body,records)
  response=httpx.post(PROJECT_URL+'/rest/v1/rpc/ep_save_decision',headers=headers,json={'p':result},timeout=30);response.raise_for_status()
  return response.json()
 @app.get('/api/export')
 def export():return d.store.export(d.owner())
 if d.store.get('root') and pathlib.Path(d.store.get('root')).is_dir():d.scan()
 return app
