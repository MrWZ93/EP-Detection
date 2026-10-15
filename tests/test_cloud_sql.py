"""Local PostgreSQL integration tests; never connect to the real project."""
import json,os,pathlib,sys,unittest,uuid,hashlib
try:import psycopg
except ImportError:psycopg=None
ROOT=pathlib.Path(__file__).resolve().parents[1]
@unittest.skipUnless(psycopg and os.environ.get('EP_DESKTOP_TEST_DB'),'Local disposable PostgreSQL required')
class CloudSQL(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.db=psycopg.connect(os.environ['EP_DESKTOP_TEST_DB'],autocommit=True);cls.owner=str(uuid.uuid4());cls.other=str(uuid.uuid4());cls.admin=str(uuid.uuid4());cls.stranger=str(uuid.uuid4())
  for id in [cls.owner,cls.other,cls.admin,cls.stranger]:cls.db.execute('INSERT INTO auth.users VALUES(%s)',(id,))
  for id,role in [(cls.owner,'reviewer'),(cls.other,'reviewer'),(cls.admin,'admin')]:cls.db.execute('INSERT INTO ep_members VALUES(%s,%s)',(id,role))
 @classmethod
 def tearDownClass(cls):cls.db.close()
 def payload(self):return {'operation_id':str(uuid.uuid4()),'assessment_id':str(uuid.uuid4()),'base_revision':0,'revision':1,'source_id':hashlib.sha256(('b'*64+'\0synthetic.tdms').encode()).hexdigest(),'source_sha256':'b'*64,'relative_path':'synthetic.tdms','sample_count':100,'sample_rate':50000,'annotation':{'decision':'yes','profile_confirmed':True,'partition':{'cuts':[0,40,100],'labels':['S1','S4']}},'submitted':True,'reviewer_name':'Synthetic','client_version':'1.0.0-preview.1'}
 def call(self,actor,p,fn='ep_save_revision'):
  with self.db.transaction():
   self.db.execute('SET LOCAL ROLE authenticated');self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(actor,));return self.db.execute('SELECT public.'+fn+'(%s::jsonb)',(json.dumps(p),)).fetchone()[0]
 def test_owner_retry_cas_and_isolation(self):
  p=self.payload();self.assertEqual(self.call(self.owner,p),self.call(self.owner,p))
  with self.assertRaises(psycopg.Error):self.call(self.other,p)
  p['operation_id']=str(uuid.uuid4())
  with self.assertRaises(psycopg.Error):self.call(self.owner,p)
  with self.db.transaction():
   self.db.execute('SET LOCAL ROLE authenticated');self.db.execute("SELECT set_config('request.jwt.claim.sub',%s,true)",(self.other,));self.assertEqual(self.db.execute('SELECT count(*) FROM ep_revisions WHERE owner=%s',(self.owner,)).fetchone()[0],0)
   with self.assertRaises(psycopg.Error):self.db.execute("UPDATE ep_members SET role='admin' WHERE user_id=%s",(self.other,))
 def test_nonmember_and_bad_order(self):
  p=self.payload()
  with self.assertRaises(psycopg.Error):self.call(self.stranger,p)
  p['annotation']['partition']['labels']=['S4','S3']
  with self.assertRaises(psycopg.Error):self.call(self.owner,p)
 def test_missing_partition_rejected(self):
  p=self.payload();p['annotation'].pop('partition')
  with self.assertRaises(psycopg.Error):self.call(self.owner,p)
 def test_admin_attested_boundary(self):
  p=self.payload();p['relative_path']=str(uuid.uuid4())+'.tdms';p['source_id']=hashlib.sha256((p['source_sha256']+'\0'+p['relative_path']).encode()).hexdigest();self.call(self.owner,p)
  choice={'status':'include','voltage_V':.5,'boundary_idx':40,'sample_idx':40,'stage':'S4','edge':'start','source_sha256':p['source_sha256'],'definition_confirmed':True,'calibration_confirmed':True,'edge_unobscured':True}
  d={'operation_id':str(uuid.uuid4()),'source_id':p['source_id'],'source_sha256':p['source_sha256'],'selected_revision_id':p['operation_id'],'observed_revision_ids':[p['operation_id']],'thresholds':{'EV':choice,'BV':{'status':'definition_unconfirmed'}},'reason':'Synthetic verified boundary','supersedes':None,'conditions':'Synthetic'}
  with self.assertRaises(psycopg.Error):self.call(self.owner,d,'ep_save_decision')
  self.assertEqual(self.call(self.admin,d,'ep_save_decision')['operation_id'],d['operation_id']);self.assertEqual(self.call(self.admin,d,'ep_save_decision')['operation_id'],d['operation_id'])
  d['operation_id']=str(uuid.uuid4())
  with self.assertRaises(psycopg.Error):self.call(self.admin,d,'ep_save_decision')
if __name__=='__main__':unittest.main()
