"""Security regressions use real roles, transactions, and concurrent connections."""
import copy,json,os,time,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
import test_cloud_sql as base
psycopg=base.psycopg
@unittest.skipUnless(psycopg and os.environ.get('EP_DESKTOP_TEST_DB'),'Local disposable PostgreSQL required')
class CloudSecurity(unittest.TestCase):
 setUpClass=classmethod(base.CloudSQL.setUpClass.__func__)
 tearDownClass=classmethod(base.CloudSQL.tearDownClass.__func__)
 payload=base.CloudSQL.payload
 call=base.CloudSQL.call
 def decision(self,p):
  return {'operation_id':str(uuid.uuid4()),'source_id':p['source_id'],'source_sha256':p['source_sha256'],'selected_revision_id':p['operation_id'],'observed_revision_ids':[p['operation_id']],'thresholds':{'EV':{'status':'include','voltage_V':.5,'boundary_idx':40,'sample_idx':40,'stage':'S4','edge':'start','source_sha256':p['source_sha256'],'definition_confirmed':True,'calibration_confirmed':True,'edge_unobscured':True},'BV':{'status':'missing'}},'reason':'Synthetic review','supersedes':None,'conditions':'Synthetic'}
 def unique(self):
  import hashlib
  p=self.payload();p['relative_path']=str(uuid.uuid4())+'.tdms';p['source_id']=hashlib.sha256((p['source_sha256']+'\0'+p['relative_path']).encode()).hexdigest();return p
 def test_rate_requires_finite_positive_json_number(self):
  for value in [None,0,-1,'NaN','Infinity','50000',True,{},[]]:
   with self.subTest(value=value):
    p=self.unique();p['sample_rate']=value
    with self.assertRaises(psycopg.Error):self.call(self.owner,p)
 def test_revoked_member_cannot_read_or_write(self):
  user=str(uuid.uuid4());self.db.execute('INSERT INTO auth.users VALUES(%s)',(user,));self.db.execute("INSERT INTO ep_members VALUES(%s,'reviewer')",(user,));p=self.unique();self.call(user,p);self.db.execute('DELETE FROM ep_members WHERE user_id=%s',(user,))
  with self.db.transaction():
   self.db.execute('SET LOCAL ROLE authenticated');self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(user,))
   for table in ['ep_assessments','ep_revisions']:self.assertEqual(self.db.execute('SELECT count(*) FROM '+table+' WHERE owner=%s',(user,)).fetchone()[0],0)
  with self.assertRaises(psycopg.Error):self.call(user,p)
 def test_decision_required_hash_and_evidence_types(self):
  p=self.unique();self.call(self.owner,p)
  for path,value in [('source_sha256',None),('source_sha256',''),('EV.source_sha256',None),('EV.edge',None),('EV.stage',None),('EV.definition_confirmed','true'),('EV.boundary_idx','40')]:
   with self.subTest(path=path,value=value):
    d=self.decision(p)
    if path.startswith('EV.'):d['thresholds']['EV'][path[3:]]=value
    else:d[path]=value
    with self.assertRaises(psycopg.Error):self.call(self.admin,d,'ep_save_decision')
 def test_anon_cannot_execute_any_application_function(self):
  rows=self.db.execute("SELECT n.nspname,p.proname,has_function_privilege('anon',p.oid,'EXECUTE') FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='ep_private' OR (n.nspname='public' AND p.proname LIKE 'ep_%')").fetchall()
  self.assertTrue(rows)
  self.assertEqual([(n,p) for n,p,allowed in rows if allowed],[])
 def test_no_public_security_definer_or_role_creation_privilege(self):
  self.assertEqual(self.db.execute("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'ep_%' AND p.prosecdef").fetchone()[0],0)
  for role in ['anon','authenticated']:
   self.assertFalse(self.db.execute("SELECT has_schema_privilege(%s,'ep_private','CREATE')",(role,)).fetchone()[0])
 def test_history_immutable_and_admin_can_compare(self):
  p=self.unique();self.call(self.owner,p)
  for sql in ['UPDATE ep_revisions SET revision=9 WHERE operation_id=%s','DELETE FROM ep_revisions WHERE operation_id=%s']:
   with self.assertRaises(psycopg.Error):
    with self.db.transaction():self.db.execute(sql,(p['operation_id'],))
  with self.db.transaction():
   self.db.execute('SET LOCAL ROLE authenticated');self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.admin,));self.assertEqual(self.db.execute('SELECT payload FROM ep_revisions WHERE operation_id=%s',(p['operation_id'],)).fetchone()[0],p)
  for role in ['anon','authenticated']:
   for table in ['ep_members','ep_assessments','ep_revisions','ep_decisions']:
    for privilege in ['INSERT','UPDATE','DELETE','TRUNCATE']:
     self.assertFalse(self.db.execute('SELECT has_table_privilege(%s,%s,%s)',(role,table,privilege)).fetchone()[0])
 def test_concurrent_revision_blocks_stale_adjudication(self):
  p=self.unique();self.call(self.owner,p);d=self.decision(p);new=copy.deepcopy(p);new.update(operation_id=str(uuid.uuid4()),base_revision=1,revision=2)
  with psycopg.connect(os.environ['EP_DESKTOP_TEST_DB'],autocommit=True) as writer, psycopg.connect(os.environ['EP_DESKTOP_TEST_DB'],autocommit=True) as reader:
   pool=ThreadPoolExecutor(max_workers=1)
   def adjudicate():
    with reader.transaction():
     reader.execute("SET LOCAL statement_timeout='5000ms'");reader.execute('SET LOCAL ROLE authenticated');reader.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.admin,));return reader.execute('SELECT ep_save_decision(%s::jsonb)',(json.dumps(d),)).fetchone()
   try:
    with writer.transaction():
     writer.execute('SET LOCAL ROLE authenticated');writer.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.owner,));writer.execute('SELECT ep_save_revision(%s::jsonb)',(json.dumps(new),))
     future=pool.submit(adjudicate);deadline=time.monotonic()+3;waiting=False
     while time.monotonic()<deadline and not future.done():
      waiting=self.db.execute("SELECT wait_event='advisory' FROM pg_stat_activity WHERE pid=%s",(reader.info.backend_pid,)).fetchone()[0]
      if waiting:break
      time.sleep(.01)
     self.assertTrue(waiting,'Adjudication must wait for the uncommitted same-source revision')
    with self.assertRaises(psycopg.Error):future.result(timeout=6)
   finally:pool.shutdown(wait=True)
  self.assertEqual(self.db.execute('SELECT count(*) FROM ep_decisions WHERE source_id=%s',(p['source_id'],)).fetchone()[0],0)
 def test_current_desktop_adjudication_payload(self):
  from test_admin import Admin
  from admin import adjudicate
  fixture=Admin();fixture.setUp()
  try:
   p=self.payload();p.update(operation_id=fixture.id,source_id=fixture.o['source_id'],source_sha256=fixture.o['sha256'],relative_path='synthetic.tdms',sample_count=1000,annotation=fixture.records[0]['payload']['annotation']);self.call(self.owner,p)
   decision=adjudicate(fixture.d,fixture.body,fixture.records)
   self.assertEqual(self.call(self.admin,decision,'ep_save_decision')['operation_id'],decision['operation_id'])
  finally:fixture.tearDown()
 def test_required_revision_fields_reject_null_or_wrong_types(self):
  for field in ['operation_id','assessment_id','revision','base_revision','source_id','source_sha256','relative_path','sample_count','annotation','submitted','reviewer_name','client_version']:
   with self.subTest(field=field):
    p=self.unique();p[field]=None
    with self.assertRaises(psycopg.Error):self.call(self.owner,p)
 def test_decision_immutable_and_revoked_admin_denied(self):
  p=self.unique();self.call(self.owner,p);d=self.decision(p);self.call(self.admin,d,'ep_save_decision')
  for sql in ['UPDATE ep_decisions SET payload=payload WHERE operation_id=%s','DELETE FROM ep_decisions WHERE operation_id=%s']:
   with self.assertRaises(psycopg.Error):
    with self.db.transaction():self.db.execute(sql,(d['operation_id'],))
  try:
   self.db.execute('DELETE FROM ep_members WHERE user_id=%s',(self.admin,))
   with self.assertRaises(psycopg.Error):self.call(self.admin,d,'ep_save_decision')
   with self.db.transaction():
    self.db.execute('SET LOCAL ROLE authenticated');self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.admin,));self.assertEqual(self.db.execute('SELECT count(*) FROM ep_decisions').fetchone()[0],0)
  finally:self.db.execute("INSERT INTO ep_members VALUES(%s,'admin')",(self.admin,))
 def test_concurrent_same_operation_is_once_and_base_conflict_is_atomic(self):
  p=self.unique()
  def submit(body):
   with psycopg.connect(os.environ['EP_DESKTOP_TEST_DB']) as db:
    db.execute('SET LOCAL ROLE authenticated');db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.owner,));return db.execute('SELECT ep_save_revision(%s::jsonb)',(json.dumps(body),)).fetchone()[0]
  with ThreadPoolExecutor(max_workers=2) as pool:
   a=pool.submit(submit,p);b=pool.submit(submit,p);self.assertEqual(a.result(timeout=5),b.result(timeout=5))
  self.assertEqual(self.db.execute('SELECT count(*) FROM ep_revisions WHERE assessment_id=%s',(p['assessment_id'],)).fetchone()[0],1)
  a=copy.deepcopy(p);a.update(operation_id=str(uuid.uuid4()),base_revision=1,revision=2);b=copy.deepcopy(a);b['operation_id']=str(uuid.uuid4())
  with ThreadPoolExecutor(max_workers=2) as pool:
   futures=[pool.submit(submit,x) for x in [a,b]];success=conflict=0
   for f in futures:
    try:f.result(timeout=5);success+=1
    except psycopg.errors.UniqueViolation:conflict+=1
  self.assertEqual((success,conflict),(1,1));self.assertEqual(self.db.execute('SELECT count(*) FROM ep_revisions WHERE assessment_id=%s',(p['assessment_id'],)).fetchone()[0],2)
 def test_decision_transaction_blocks_new_revision_until_commit(self):
  p=self.unique();self.call(self.owner,p);d=self.decision(p);new=copy.deepcopy(p);new.update(operation_id=str(uuid.uuid4()),base_revision=1,revision=2)
  with psycopg.connect(os.environ['EP_DESKTOP_TEST_DB'],autocommit=True) as adjudicator, psycopg.connect(os.environ['EP_DESKTOP_TEST_DB'],autocommit=True) as writer:
   pool=ThreadPoolExecutor(max_workers=1)
   def submit():
    with writer.transaction():
     writer.execute("SET LOCAL statement_timeout='5000ms'");writer.execute('SET LOCAL ROLE authenticated');writer.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.owner,));return writer.execute('SELECT ep_save_revision(%s::jsonb)',(json.dumps(new),)).fetchone()[0]
   try:
    with adjudicator.transaction():
     adjudicator.execute('SET LOCAL ROLE authenticated');adjudicator.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.admin,));adjudicator.execute('SELECT ep_save_decision(%s::jsonb)',(json.dumps(d),));future=pool.submit(submit);deadline=time.monotonic()+3;waiting=False
     while time.monotonic()<deadline and not future.done():
      waiting=self.db.execute("SELECT wait_event='advisory' FROM pg_stat_activity WHERE pid=%s",(writer.info.backend_pid,)).fetchone()[0]
      if waiting:break
      time.sleep(.01)
     self.assertTrue(waiting,'Same-source revision must wait for adjudication commit')
    self.assertEqual(future.result(timeout=6)['revision'],2)
   finally:pool.shutdown(wait=True)
 def test_later_serialized_decision_wins_even_if_transaction_started_earlier(self):
  p=self.unique();self.call(self.owner,p);first=self.decision(p);second=self.decision(p);second['supersedes']=first['operation_id']
  with psycopg.connect(os.environ['EP_DESKTOP_TEST_DB']) as earlier:
   earlier.execute('SELECT transaction_timestamp()')
   self.call(self.admin,first,'ep_save_decision')
   earlier.execute('SET LOCAL ROLE authenticated');earlier.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.admin,));earlier.execute('SELECT ep_save_decision(%s::jsonb)',(json.dumps(second),))
  latest=self.db.execute('SELECT operation_id::text FROM ep_decisions WHERE source_id=%s ORDER BY created_at DESC,operation_id DESC LIMIT 1',(p['source_id'],)).fetchone()[0]
  self.assertEqual(latest,second['operation_id'])
