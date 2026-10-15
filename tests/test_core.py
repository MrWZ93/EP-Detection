import concurrent.futures,json,pathlib,sys,tempfile,unittest,uuid
import numpy as np
from nptdms import TdmsWriter,ChannelObject
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'code'))
from store import Store,Conflict,validate
import source

def tdms(path,n=1000,dt=.00002):
 with TdmsWriter(path) as w:w.write_segment([ChannelObject('g','command',np.arange(n,dtype=float),properties={'NI_ArrayColumn':0,**({'wf_increment':dt} if dt else {})}),ChannelObject('g','current',np.sin(np.arange(n)),properties={'NI_ArrayColumn':1,**({'wf_increment':dt} if dt else {})})])
class Core(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);self.p=self.root/'sample.tdms';tdms(self.p);self.s=Store(self.root/'state.db');self.sha,self.fp=source.sha256(self.p);self.meta=source.metadata(self.p);self.f=self.s.source(self.sha,'folder/sample.tdms',self.meta);self.owner=str(uuid.uuid4());self.s.set('name:'+self.owner,'Test reviewer');self.a=self.s.start(self.owner,self.f);self.payload={'decision':'yes','note':'evidence','partition':{'cuts':[0,500,1000],'labels':['S1','S4']},'profile_confirmed':True}
 def tearDown(self):self.tmp.cleanup()
 def save(self,op=None,base=0):return self.s.save(self.owner,self.a['id'],op or str(uuid.uuid4()),base,self.payload,True)
 def test_metadata_and_minmax(self):
  self.assertAlmostEqual(self.meta['fs'],50000);w=source.waveform(self.p,self.fp,bins=10,divisor=10);self.assertEqual(w['vmax'][0],9.9);self.assertEqual(source.exact(self.p,self.fp,[501],10)['501'],50.1);self.assertEqual(w['end_idx'][-1],1000)
 def test_unknown_interval(self):
  tdms(self.root/'bad.tdms',dt=None)
  self.assertIsNone(source.metadata(self.root/'bad.tdms')['fs']);self.assertIsNone(source.waveform(self.root/'bad.tdms',source.fingerprint(self.root/'bad.tdms'))['fs'])
 def test_source_change_blocks(self):
  self.p.touch()
  with self.assertRaises(source.SourceChanged):source.waveform(self.p,self.fp)
 def test_containment(self):
  with self.assertRaises(ValueError):source.resolve(self.root,'../escape.tdms')
 def test_content_identity(self):
  self.assertEqual(self.f,self.s.source(self.sha,'folder/sample.tdms',self.meta));self.assertNotEqual(self.f,self.s.source(self.sha,'other/sample.tdms',self.meta))
 def test_save_retry_restart_and_immutable(self):
  op=str(uuid.uuid4());r=self.save(op);self.assertEqual(self.save(op),r);s=Store(self.root/'state.db');self.assertEqual(s.assessment(self.owner,self.a['id'])['revision'],1);self.assertEqual(len(s.pending(self.owner)),1)
  with self.assertRaises(Exception):
   with s.db() as d:d.execute('DELETE FROM events')
 def test_collision_and_cas(self):
  self.save()
  with self.assertRaises(Conflict):self.save()
 def test_concurrent_cas_one_winner(self):
  def one(_):
   try:self.save();return True
   except Conflict:return False
  with concurrent.futures.ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(one,range(2))),1)
 def test_independent_repeats(self):
  self.save();b=self.s.start(self.owner,self.f);self.assertNotEqual(b['id'],self.a['id']);self.assertEqual(b['revision'],0)
 def test_owner_isolation(self):
  self.save();other=str(uuid.uuid4());self.assertEqual(self.s.pending(other),[])
  with self.assertRaises(ValueError):self.s.assessment(other,self.a['id'])
 def test_stage_order(self):
  self.payload['partition']['labels']=['S4','S3']
  with self.assertRaisesRegex(ValueError,'earlier'):self.save()
 def test_qc_does_not_allow_regression(self):
  self.payload['partition']={'cuts':[0,300,600,1000],'labels':['S4','outside','S3']}
  with self.assertRaises(ValueError):self.save()
 def test_partial_allowed_final_requires_labels(self):
  self.payload['partition']['labels']=['S1',None];validate(self.payload,1000)
  with self.assertRaises(ValueError):validate(self.payload,1000,True)
 def test_no_and_uncertain_preserved(self):
  self.payload={'decision':'no','note':'IV protocol; not EP'};self.save();self.assertEqual(self.s.assessment(self.owner,self.a['id'])['payload']['note'],'IV protocol; not EP')
 def test_sync_ack_persistence(self):
  r=self.save();self.s.sync_result(self.owner,r['id'],'synced');self.assertEqual(self.s.pending(self.owner),[]);self.assertEqual(self.s.assessment(self.owner,self.a['id'])['sync']['status'],'synced')
if __name__=='__main__':unittest.main()
