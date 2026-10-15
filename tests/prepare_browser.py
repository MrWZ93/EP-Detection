"""Synthetic acceptance state; never points at actual annotation state."""
import pathlib,sys,json,hashlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'code'))
from store import Store
from nptdms import TdmsWriter,ChannelObject
import numpy as np
root=pathlib.Path(sys.argv[1]);data=root/'data';data.mkdir(parents=True,exist_ok=True);hashes=[]
for name in ['01 synthetic EP.tdms','02 synthetic nonEP.tdms']:
 p=data/name
 with TdmsWriter(p) as w:w.write_segment([ChannelObject('synthetic','command',np.linspace(0,10,10000),properties={'NI_ArrayColumn':0}),ChannelObject('synthetic','current',np.repeat([0.,1.,2.,5.],2500),properties={'NI_ArrayColumn':1})])
 hashes.append(hashlib.sha256(p.read_bytes()).hexdigest())
(data/'ep-dataset-profile.json').write_text(json.dumps({'schema':'ep-dataset-profile-v1','sample_rate':50000,'basis':'Synthetic coordinator fixture: confirmed 50 kHz','source_sha256':hashes}))
s=Store(root/'state'/'annotations.sqlite3');s.set('root',str(data));s.set('name:local:'+s.get('device'),'Synthetic browser reviewer')
print('Synthetic browser fixture ready')
