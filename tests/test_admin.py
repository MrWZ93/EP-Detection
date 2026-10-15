import pathlib,sys,tempfile,unittest,uuid
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'code'))
from server import Desktop
from admin import adjudicate
from test_core import tdms
class Admin(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.t.name);tdms(self.root/'synthetic.tdms');self.d=Desktop(self.root/'state',pathlib.Path(__file__).resolve().parents[1]/'web');self.d.store.set('root',str(self.root));self.d.files={'f':'synthetic.tdms'};self.o=self.d.open('f');self.id=str(uuid.uuid4());self.records=[{'operation_id':self.id,'payload':{'source_id':self.o['source_id'],'submitted':True,'annotation':{'decision':'yes','profile_confirmed':True,'partition':{'cuts':[0,500,1000],'labels':['S1','S4']}}}}];self.body={'file_id':'f','operation_id':str(uuid.uuid4()),'selected_revision_id':self.id,'observed_revision_ids':[self.id],'reason':'Definition verified','thresholds':{'EV':{'status':'include','stage':'S4','edge':'start','definition_confirmed':True,'calibration_confirmed':True,'edge_unobscured':True},'BV':{'status':'definition_unconfirmed'}}}
 def tearDown(self):self.d.pool.shutdown();self.t.cleanup()
 def test_exact_sample_not_mean_and_no_automatic_bv(self):
  r=adjudicate(self.d,self.body,self.records);self.assertEqual(r['thresholds']['EV']['voltage_V'],50);self.assertEqual(r['thresholds']['BV'],{'status':'definition_unconfirmed'})
 def test_unconfirmed_calibration_excluded(self):
  self.body['thresholds']['EV']['calibration_confirmed']=False
  with self.assertRaises(ValueError):adjudicate(self.d,self.body,self.records)
 def test_stale_review_rejected(self):
  self.body['observed_revision_ids']=[]
  with self.assertRaises(ValueError):adjudicate(self.d,self.body,self.records)
if __name__=='__main__':unittest.main()
