"""Read-only local TDMS. Raw data never leaves this process via cloud sync."""
import hashlib, math, pathlib, re
import numpy as np
from nptdms import TdmsFile

class SourceChanged(ValueError): pass

def fingerprint(path):
 s=path.stat(); return [s.st_size,s.st_mtime_ns,s.st_ino]

def resolve(root,relative):
 root=pathlib.Path(root).resolve(); p=(root/relative).resolve()
 if not p.is_relative_to(root) or p.suffix.lower()!='.tdms' or not p.is_file():raise ValueError('Source is unavailable or outside the selected folder')
 return p

def sha256(path):
 before=fingerprint(path); h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 if fingerprint(path)!=before:raise SourceChanged('Source changed during hashing; reopen it')
 return h.hexdigest(),before

def channels(td):
 cs=[c for g in td.groups() for c in g.channels()]
 v=[c for c in cs if c.properties.get('NI_ArrayColumn')==0]
 i=[c for c in cs if c.properties.get('NI_ArrayColumn')==1]
 if len(v)!=1 or len(i)!=1:raise ValueError('Channel mapping is ambiguous: expected one NI_ArrayColumn 0 and one 1; manual acquisition-profile verification required')
 v,i=v[0],i[0]
 if len(v)!=len(i) or not len(i):raise ValueError('Empty or unequal channel lengths')
 intervals=[c.properties.get('wf_increment') for c in [v,i]]
 if all(x is None for x in intervals):return v,i,None
 if any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in intervals):raise ValueError('Sampling interval invalid or missing on only one channel')
 if not math.isclose(*intervals,rel_tol=1e-9):raise ValueError('Channels have different sampling intervals')
 return v,i,1/intervals[0]

def metadata(path):
 with TdmsFile.open(path) as td:
  cs=[{'group':g.name,'name':c.name,'n':len(c),'properties':{k:str(v) for k,v in c.properties.items()}} for g in td.groups() for c in g.channels()]
  v,i,fs=channels(td)
  return {'n':len(v),'fs':fs,'channels':cs,'current_unit':'raw','voltage_unit':'raw command (profile unconfirmed)', 'third_channel':'uninterpreted'}

def waveform(path,expected,start=0,end=None,bins=1800,divisor=None):
 if fingerprint(path)!=expected:raise SourceChanged('Source changed since opening; reopen before saving')
 with TdmsFile.open(path) as td:
  v,i,fs=channels(td); n=len(v);end=n if end is None else int(end);start=int(start)
  if not 0<=start<end<=n:raise ValueError('Invalid sample range')
  bins=max(1,min(4000,int(bins))); width=max(1,math.ceil((end-start)/bins)); out={'idx':[],'end_idx':[],'vmin':[],'vmax':[],'imin':[],'imax':[],'fs':fs,'n':n,'start':start,'end':end,'voltage_unit':'V' if divisor==10 else 'raw','current_unit':'raw'}
  # Align reads to bins, bound allocation to roughly 2 MB per channel (unless one bin larger).
  batch=max(width,(250000//width)*width)
  for a in range(start,end,batch):
   b=min(end,a+batch);vv=np.asarray(v[a:b],dtype=float);ii=np.asarray(i[a:b],dtype=float)
   if not np.isfinite(vv).all() or not np.isfinite(ii).all():raise ValueError('Nonfinite waveform samples; no silent interpolation')
   if divisor==10:vv=vv/10
   edges=np.arange(0,len(vv),width)
   out['idx'].extend((edges+a).tolist());out['end_idx'].extend(np.minimum(edges+a+width,b).tolist())
   for key,data,fn in [('vmin',vv,np.minimum),('vmax',vv,np.maximum),('imin',ii,np.minimum),('imax',ii,np.maximum)]:out[key].extend(fn.reduceat(data,edges).tolist())
 if fingerprint(path)!=expected:raise SourceChanged('Source changed while reading')
 return out

def exact(path,expected,samples,divisor):
 if divisor!=10:raise ValueError('Command calibration profile not confirmed')
 if fingerprint(path)!=expected:raise SourceChanged('Source changed')
 with TdmsFile.open(path) as td:
  v,_,_=channels(td);result={}
  for sample in sorted(set(samples)):
   if type(sample) is not int or not 0<=sample<len(v):raise ValueError('Boundary sample outside recording')
   value=float(v[sample])/10
   if not math.isfinite(value):raise ValueError('Nonfinite boundary voltage')
   result[str(sample)]=value
 if fingerprint(path)!=expected:raise SourceChanged('Source changed')
 return result

def hints(relative):
 # Search context only, never scientific classifications or calibration confirmation.
 beta=re.findall(r'(?i)beta[ _=:-]*(0\.1|1)(?![\d.])',relative)
 return {'path_context':relative,'beta_path_hint':sorted(set(beta)),'conditions_confirmed':False,'classification':'unreviewed','calibration':'current raw; beta/alpha not inferred'}
