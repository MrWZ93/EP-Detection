"""Crash-safe local revisions and durable, account-scoped outbox."""
import contextlib,hashlib,json,pathlib,sqlite3,time,uuid,math

class Conflict(ValueError): pass

def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def uid():return str(uuid.uuid4())
def validate(payload,n,final=False):
 if not isinstance(payload,dict):raise ValueError('Annotation must be an object')
 if set(payload)-{'decision','note','partition','conditions','profile_confirmed','qc_note','thresholds','sample_rate','sampling_basis','conditions_confirmed'}:raise ValueError('Unknown annotation fields')
 if payload.get('decision') not in [None,'yes','no','uncertain']:raise ValueError('Invalid decision')
 if not isinstance(payload.get('note',''),str) or len(payload.get('note',''))>10000:raise ValueError('Review note too long')
 if final and payload.get('decision') not in ['yes','no','uncertain']:raise ValueError('Choose Yes, No, or Uncertain')
 rate=payload.get('sample_rate')
 if rate is not None and (type(rate) not in [int,float] or not math.isfinite(rate) or rate<=0 or not payload.get('sampling_basis','').strip()):raise ValueError('Manual sampling rate needs a positive value and verification basis')
 if payload.get('decision')=='no':return
 p=payload.get('partition',{'cuts':[0,n],'labels':[None]});cuts=p.get('cuts');labels=p.get('labels')
 if not isinstance(cuts,list) or not isinstance(labels,list) or len(cuts)!=len(labels)+1 or cuts[0]!=0 or cuts[-1]!=n:raise ValueError('Invalid partition')
 if any(type(x)is not int or x<0 or x>n or (j and x<=cuts[j-1]) for j,x in enumerate(cuts)):raise ValueError('Invalid boundaries')
 last=0;seen=set();previous=None
 for label in labels:
  if label not in [None,'outside','S1','S2','S3','S4']:raise ValueError('Invalid stage')
  if final and payload.get('decision')=='yes' and label is None:raise ValueError('Label every region, or mark Outside stages')
  if label in ['S1','S2','S3','S4']:
   order=int(label[-1])
   if order<last or (label in seen and previous!=label):raise ValueError('Stages cannot return to an earlier state; S4 cannot be followed by S3')
   last=order;seen.add(label)
  previous=label

class Store:
 def __init__(self,path):
  self.path=pathlib.Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.db() as d:
   d.executescript('''
   CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,sha TEXT NOT NULL,relative TEXT NOT NULL,metadata TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS assessments(id TEXT PRIMARY KEY,owner TEXT NOT NULL,source_id TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
   CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,assessment TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,final INTEGER NOT NULL,created REAL NOT NULL,UNIQUE(assessment,revision));
   CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY,owner TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',error TEXT,attempts INTEGER NOT NULL DEFAULT 0);
   CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'Immutable revision'); END;
   CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'Immutable revision'); END;
   ''')
   if not d.execute("SELECT 1 FROM settings WHERE key='device'").fetchone():d.execute('INSERT INTO settings VALUES(?,?)',('device',encoded(uid())))
 @contextlib.contextmanager
 def db(self):
  d=sqlite3.connect(self.path,timeout=15);d.row_factory=sqlite3.Row
  d.execute('PRAGMA journal_mode=WAL');d.execute('PRAGMA synchronous=FULL');d.execute('PRAGMA foreign_keys=ON')
  try:yield d;d.commit()
  except:d.rollback();raise
  finally:d.close()
 def get(self,key,default=None):
  with self.db() as d:r=d.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone();return json.loads(r[0]) if r else default
 def set(self,key,value):
  with self.db() as d:d.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(key,encoded(value)))
 def source(self,sha,relative,meta):
  id=hashlib.sha256((sha+'\0'+relative).encode()).hexdigest()
  with self.db() as d:
   old=d.execute('SELECT metadata FROM sources WHERE id=?',(id,)).fetchone()
   if old and old[0]!=encoded(meta):raise Conflict('Source parser metadata changed; migration required')
   d.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?)',(id,sha,relative,encoded(meta)))
  return id
 def start(self,owner,source,id=None):
  id=id or uid();uuid.UUID(id)
  with self.db() as d:
   if not d.execute('SELECT 1 FROM sources WHERE id=?',(source,)).fetchone():raise ValueError('Unknown source')
   row=d.execute('SELECT * FROM assessments WHERE id=?',(id,)).fetchone()
   if row:
    if row['owner']!=owner or row['source_id']!=source:raise Conflict('Assessment ID collision')
   else:d.execute('INSERT INTO assessments VALUES(?,?,?,0,?)',(id,owner,source,time.time()))
  return self.assessment(owner,id)
 def assessment(self,owner,id):
  with self.db() as d:
   row=d.execute('SELECT * FROM assessments WHERE id=? AND owner=?',(id,owner)).fetchone()
   if not row:raise ValueError('Assessment unavailable for this account')
   a=dict(row);e=d.execute('SELECT * FROM events WHERE assessment=? ORDER BY revision DESC LIMIT 1',(id,)).fetchone()
   a['payload']=json.loads(e['payload']) if e else None;a['final']=bool(e['final']) if e else False
   a['sync']=dict(d.execute('SELECT status,error FROM outbox WHERE id=?',(e['id'],)).fetchone()) if e else None
   return a
 def list(self,owner,source=None):
  with self.db() as d:ids=[r[0] for r in d.execute('SELECT id FROM assessments WHERE owner=? AND (? IS NULL OR source_id=?) ORDER BY created DESC',(owner,source,source))]
  return [self.assessment(owner,id) for id in ids]
 def save(self,owner,id,op,base,payload,final):
  uuid.UUID(op)
  with self.db() as d:
   d.execute('BEGIN IMMEDIATE');a=d.execute('SELECT * FROM assessments WHERE id=? AND owner=?',(id,owner)).fetchone()
   if not a:raise ValueError('Assessment unavailable for this account')
   f=d.execute('SELECT * FROM sources WHERE id=?',(a['source_id'],)).fetchone();meta=json.loads(f['metadata']);validate(payload,meta['n'],final)
   old=d.execute('SELECT * FROM events WHERE id=?',(op,)).fetchone()
   if old:
    if old['assessment']!=id or old['revision']!=base+1 or old['payload']!=encoded(payload) or old['final']!=bool(final):raise Conflict('Operation ID reused with different contents')
    return {'id':op,'revision':old['revision'],'local_saved':True}
   if type(base)is not int or base!=a['revision']:raise Conflict('A newer revision exists. Keep this draft and reload before resolving.')
   rev=base+1;now=time.time();d.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(op,id,rev,encoded(payload),bool(final),now));d.execute('UPDATE assessments SET revision=? WHERE id=?',(rev,id))
   body={'operation_id':op,'assessment_id':id,'base_revision':base,'revision':rev,'source_id':f['id'],'source_sha256':f['sha'],'relative_path':f['relative'],'sample_count':meta['n'],'sample_rate':payload.get('sample_rate') or meta['fs'],'annotation':payload,'submitted':bool(final),'reviewer_name':self.get('name:'+owner,''),'client_version':'1.0.0-preview.1'}
   d.execute('INSERT INTO outbox(id,owner,body) VALUES(?,?,?)',(op,owner,encoded(body)))
  return {'id':op,'revision':rev,'local_saved':True}
 def pending(self,owner):
  with self.db() as d:return [dict(x) for x in d.execute("SELECT * FROM outbox WHERE owner=? AND status!='synced' ORDER BY rowid",(owner,))]
 def sync_result(self,owner,id,status,error=None):
  if status not in ['synced','pending','conflict']:raise ValueError('Bad sync status')
  with self.db() as d:d.execute('UPDATE outbox SET status=?,error=?,attempts=attempts+1 WHERE id=? AND owner=?',(status,error,id,owner))
 def export(self,owner):return {'schema':'ep-desktop-export-v1','assessments':self.list(owner),'outbox':self.pending(owner)}
