import pathlib,sys,tempfile,unittest,uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'code'))
from server import Desktop,create_app
from test_core import tdms
class HTTP(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name);tdms(self.root/'fixture.tdms');self.d=Desktop(self.root/'state',pathlib.Path(__file__).resolve().parents[1]/'web',port=8780);self.d.store.set('root',str(self.root));self.d.files={'f':'fixture.tdms'};self.c=TestClient(create_app(self.d),base_url='http://127.0.0.1:8780');self.headers={'X-EP-Session':self.d.secret};self.d.pool.shutdown(wait=True);self.d.files={'f':'fixture.tdms'}
 def tearDown(self):self.tmp.cleanup()
 def test_dataset_profile_scoped_by_content(self):
  from server import validate_profile
  o=self.d.open('f');p={'schema':'ep-dataset-profile-v1','sample_rate':50000,'basis':'Owner confirmed this batch','source_sha256':[o['sha256']]};validate_profile(p);self.d.store.set('dataset_profile',p);self.assertEqual(self.d.open('f')['metadata']['dataset_sample_rate'],50000);p['source_sha256']=['a'*64];self.d.store.set('dataset_profile',p);self.assertNotIn('dataset_sample_rate',self.d.open('f')['metadata'])
 def test_logout_returns_separate_preview_identity(self):
  self.d.store.set('last_account',None);self.assertTrue(self.d.owner().startswith('local:'))
 def test_guard(self):
  self.assertEqual(self.c.get('/api/status').status_code,403);self.assertEqual(self.c.get('/api/status',headers=self.headers).status_code,200);self.assertEqual(self.c.get('/api/status',headers=self.headers|{'Host':'attacker.example'}).status_code,403);self.assertEqual(self.c.post('/api/rescan',headers=self.headers|{'Origin':'https://attacker.example'}).status_code,403)
 def test_wave_and_atomic_save(self):
  o=self.d.open('f');a=self.d.store.start(self.d.owner(),o['source_id']);self.d.store.set('name:'+self.d.owner(),'Synthetic reviewer');r=self.c.get('/api/wave/f?start=0&end=20&calibrated=true',headers=self.headers);self.assertEqual(r.status_code,200);self.assertEqual(r.json()['vmax'][1],.1)
  body={'file_id':'f','assessment_id':a['id'],'operation_id':str(uuid.uuid4()),'base_revision':0,'payload':{'decision':'no','note':'Not EP'},'final':True};r=self.c.post('/api/save',headers=self.headers,json=body);self.assertEqual(r.status_code,200);self.assertTrue(r.json()['local_saved']);self.assertEqual(self.c.post('/api/save',headers=self.headers,json=body).json(),r.json())
 def test_no_cloud_claim(self):
  r=self.c.post('/api/sync',headers=self.headers,json={});self.assertEqual(r.status_code,422)
 def test_static_no_private_database(self):
  self.assertEqual(self.c.get('/assets/../annotations.sqlite3').status_code,404)
if __name__=='__main__':unittest.main()
