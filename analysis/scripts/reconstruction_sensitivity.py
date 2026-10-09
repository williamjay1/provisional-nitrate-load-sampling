"""Post-result, fixed-calendar online reconstructor sensitivity. No policy retuning."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,time
import numpy as np
import pandas as pd
from paper_context import ROOT,load_context,frame_digest
from paper_metrics import evaluate
from run_value_experiment import additional_metrics

def reconstruct(base,attempts,mode):
    returned=attempts.loc[attempts.label_available_by_horizon.astype(bool)].sort_values('arrival_index')
    result=np.array(base,copy=True)
    if not len(returned):return result
    arrivals=returned.arrival_index.to_numpy(int);samples=returned.sample_index.to_numpy(int)
    values=returned.observed_mg_l.to_numpy(float);timeline=np.arange(len(base))
    which=np.searchsorted(arrivals,timeline,side='right')-1;valid=which>=0;j=which[valid]
    if mode=='online_last_residual_fixed_calendar':
        residual=values-base[samples]
        result[valid]+=residual[j]*np.exp(-(timeline[valid]-arrivals[j])/168.)
    elif mode=='online_sample_hold_fixed_calendar':result[valid]=values[j]
    else:raise ValueError(mode)
    return np.maximum(result,0)

def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);started=datetime.now(timezone.utc).isoformat();tick=time.perf_counter()
    parent=json.loads((a.parent/'run_manifest.json').read_text());data_path=Path(parent['arguments']['data'])
    data=pd.read_parquet(data_path);data['site']=data.site.astype(str);data['time_utc']=pd.to_datetime(data.time_utc,utc=True)
    h=frame_digest(data_path);metrics=pd.read_csv(a.parent/'metrics.csv',dtype={'site':str})
    attempts=pd.read_csv(a.parent/'sampling_attempts.csv',dtype={'site':str});rows=[];events=[]
    source=metrics[(metrics['mode']=='online')&(metrics.budget>0)]
    for (site,year,seed),sub in source.groupby(['site','year','seed']):
        c=load_context(data,site,int(year),int(seed),h)
        for _,r in sub.iterrows():
            taken=attempts[(attempts.site==site)&(attempts.year==year)&(attempts.seed==seed)&(attempts.budget==r.budget)&(attempts.policy==r.policy)]
            keys={k:r[k] for k in ['site','year','seed','stage','config_id','delay_hours','noise_adaptation_rate','budget','policy']}
            for mode in ['online_last_residual_fixed_calendar','online_sample_hold_fixed_calendar']:
                pred=reconstruct(c['target_base'],taken,mode)
                stats,ev=evaluate(c['target'],pred,c['events'],taken,.95)
                rows.append({**keys,'mode':mode,**stats,**additional_metrics(c['target'],pred)})
                events.extend({**keys,'mode':mode,**v} for v in ev)
    pd.DataFrame(rows).to_csv(a.output/'metrics.csv',index=False);pd.DataFrame(events).to_csv(a.output/'events.csv',index=False)
    meta={'arguments':vars(a)|{'parent':str(a.parent),'output':str(a.output)},'started_at_utc':started,
          'completed_at_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-tick,
          'parent_manifest_sha256':frame_digest(a.parent/'run_manifest.json'),'data_sha256':h,
          'code_sha256':{Path(__file__).name:frame_digest(__file__)},'metric_rows':len(rows),
          'status':'post-result descriptive sensitivity; calendars inherited without changing decisions; no new training or parameter search',
          'reason':'Assess dependence on the common online reconstructor after observing temporal/spatial contrast. The 168 h residual decay came from the earlier pilot, not holdout tuning.'}
    (a.output/'run_manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');print(a.output)
if __name__=='__main__':main()
