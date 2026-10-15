"""Explicit boundary adjudication. Never infers BV from S4 or mixes source versions."""
import math,uuid
import source

def adjudicate(desktop,body,records):
 id=body['file_id'];o=desktop.opened_file(id);op=str(uuid.UUID(body['operation_id']))
 peers=[r for r in records if r['payload']['source_id']==o['source_id']]
 observed=sorted(r['operation_id'] for r in peers)
 if sorted(body['observed_revision_ids'])!=observed:raise ValueError('Reviews changed; refresh the comparison')
 selected=next((r for r in peers if r['operation_id']==body['selected_revision_id']),None)
 if not selected:raise ValueError('Choose a version-matched submitted review')
 p=selected['payload'];a=p['annotation']
 if not p.get('submitted') or a.get('decision')!='yes':raise ValueError('Choose a completed usable review')
 if not body.get('reason','').strip():raise ValueError('Adjudication rationale required')
 # Rehash before extracting threshold evidence, even if filesystem timestamps were preserved.
 sha,fp=source.sha256(desktop.path(id))
 if sha!=o['sha256'] or fp!=o['fingerprint']:raise ValueError('Source content changed')
 thresholds={}
 for kind in ['EV','BV']:
  choice=body['thresholds'][kind];status=choice['status'];e={'status':status}
  if status not in ['include','missing','censored','saturated','calibration_unknown','definition_unconfirmed','exclude']:raise ValueError('Invalid qualification')
  if status=='include':
   if not a.get('profile_confirmed') or not all(choice.get(k)is True for k in ['definition_confirmed','calibration_confirmed','edge_unobscured']):raise ValueError('Confirm the operational definition, calibration, and unobscured boundary')
   stage=choice['stage'];edge=choice['edge'];partition=a['partition'];positions=[i for i,x in enumerate(partition['labels']) if x==stage]
   if not positions or edge not in ['start','end']:raise ValueError('Select an annotated stage boundary')
   idx=partition['cuts'][positions[0] if edge=='start' else positions[-1]+1];sample=idx if edge=='start' else idx-1
   voltage=source.exact(desktop.path(id),o['fingerprint'],[sample],10)[str(sample)]
   e.update({'voltage_V':voltage,'boundary_idx':idx,'sample_idx':sample,'stage':stage,'edge':edge,'source_sha256':sha,'definition_confirmed':True,'calibration_confirmed':True,'edge_unobscured':True})
  thresholds[kind]=e
 if all(thresholds[k]['status']=='include' for k in ['EV','BV']) and thresholds['EV']['boundary_idx']>thresholds['BV']['boundary_idx']:raise ValueError('EV cannot follow BV')
 return {'operation_id':op,'source_id':o['source_id'],'source_sha256':sha,'selected_revision_id':selected['operation_id'],'observed_revision_ids':observed,'thresholds':thresholds,'reason':body['reason'],'supersedes':body.get('supersedes'),'conditions':a.get('conditions',''),'conditions_confirmed':a.get('conditions_confirmed')is True}
