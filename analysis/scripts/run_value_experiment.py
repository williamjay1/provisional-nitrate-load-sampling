"""Development and locked validation of delayed sampling value; all outputs in D."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib,json,os,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('JOBLIB_TEMP_FOLDER',str(ROOT/'temp'))
import numpy as np
import pandas as pd
from replay import planned_calendar_indices
from paper_metrics import evaluate
from paper_context import load_context,frame_digest,ORIGINAL_SITES
from value_sampling import (make_context,RFFFeatureMap,build_reference_library,
                            ValueSamplingConfig,run_value_replay)

CONFIGS={'C0':dict(lookahead_hours=72,half_life_hours=720,threshold_quantile=.85),
         'C1':dict(lookahead_hours=168,half_life_hours=720,threshold_quantile=.85),
         'C2':dict(lookahead_hours=72,half_life_hours=2160,threshold_quantile=.85),
         'C3':dict(lookahead_hours=72,half_life_hours=720,threshold_quantile=.65)}
DEFAULT_POLICIES=['uniform','stratified_random','flow_trigger','q_uncertainty','value','historical_qr','historical_dopt']
CORE_FILES=['run_value_experiment.py','paper_context.py','value_sampling.py','replay.py','paper_metrics.py']

def verify_freeze(args, source_hash):
    frozen=json.loads(args.freeze_manifest.read_text(encoding='utf-8'))
    if frozen['data_sha256']!=source_hash:raise ValueError('Frozen data mismatch')
    for name in CORE_FILES:
        if frozen['code_sha256'][name]!=frame_digest(ROOT/'scripts'/name):raise ValueError('Frozen implementation mismatch: '+name)
    if args.config_id!=frozen['selected_config']:raise ValueError('Frozen configuration mismatch')
    for arg in ['seeds','budgets','policies','reconstruction_modes']:
        if set(getattr(args,arg))-set(frozen['allowed_'+arg]):raise ValueError('Non-prespecified '+arg)
    if args.delay_hours not in frozen['allowed_delays']:raise ValueError('Non-prespecified delay')
    if args.noise_adaptation_rate not in frozen['allowed_adaptation_rates']:raise ValueError('Non-prespecified adaptation rate')
    return frozen

def additional_metrics(target,pred):
    mask=target.valid_hour.fillna(False).to_numpy(bool)
    ref=target.load_kg.to_numpy(float)
    estimated=np.asarray(pred)*target.observed_volume_m3.to_numpy(float)*.001
    denom=np.sum(ref[mask])
    return {'hourly_load_normalized_absolute_error':float(np.sum(np.abs(estimated[mask]-ref[mask]))/denom) if denom>0 else np.nan}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=ROOT/'datasets/extended_hourly_2019_2025_v1.parquet')
    p.add_argument('--stage',choices=['development','external','temporal'],default='development')
    p.add_argument('--years',nargs='+',type=int,default=[2023,2024])
    p.add_argument('--sites',nargs='*')
    p.add_argument('--seeds',nargs='+',type=int,default=[41,73,109])
    p.add_argument('--budgets',nargs='+',type=int,default=[24,48,96])
    p.add_argument('--policies',nargs='+',default=DEFAULT_POLICIES)
    p.add_argument('--reconstruction-modes',nargs='+',choices=['online','retrospective_residual','retrospective_linear'],default=['online'])
    p.add_argument('--config-id',choices=CONFIGS,default='C0')
    p.add_argument('--delay-hours',type=int,default=24)
    p.add_argument('--noise-adaptation-rate',type=float,default=.1)
    p.add_argument('--freeze-manifest',type=Path)
    p.add_argument('--run-name',required=True)
    p.add_argument('--save-predictions',action='store_true')
    args=p.parse_args()
    if args.stage=='development' and set(args.years)-{2023,2024}:p.error('Development years are only 2023 and 2024')
    if args.stage=='external' and set(args.years)-{2023,2024}:p.error('Spatially held-out policy validation: 2023/2024')
    if args.stage=='temporal' and args.years!=[2025]:p.error('Temporal holdout must be 2025 only')
    if args.stage!='development' and not args.freeze_manifest:p.error('A frozen selection manifest is required before holdouts')
    if args.freeze_manifest and not args.freeze_manifest.exists():p.error('Missing freeze manifest')
    tick=time.perf_counter();cpu=time.process_time();started=datetime.now(timezone.utc).isoformat()
    out=ROOT/'results'/'paper_runs'/args.run_name
    out.mkdir(parents=True,exist_ok=False)
    data=pd.read_parquet(args.data)
    data['site']=data.site.astype(str)
    data['time_utc']=pd.to_datetime(data.time_utc,utc=True)
    source_hash=frame_digest(args.data)
    if args.stage!='development':verify_freeze(args,source_hash)
    sites=sorted(set(data.site))
    if args.stage=='development':sites=[s for s in sites if s in ORIGINAL_SITES]
    if args.stage=='external':sites=[s for s in sites if s not in ORIGINAL_SITES]
    if args.sites:
        if set(args.sites)-set(sites):p.error('Requested sites fall outside stage information boundary')
        sites=[s for s in sites if s in args.sites]
    metrics=[];event_rows=[];attempt_rows=[];audit=[];traces=[];predictions=[]
    for site in sites:
        for year in args.years:
            for seed in args.seeds:
                c=load_context(data,site,year,seed,source_hash)
                if c['status']!='ready':audit.append(c);continue
                target=c['target'];hist=c['history'];keys0={'site':site,'year':year,'seed':seed,'stage':args.stage,'config_id':args.config_id,
                                                         'delay_hours':args.delay_hours,'noise_adaptation_rate':args.noise_adaptation_rate}
                coverage=float(target.valid_hour.fillna(False).mean())
                if coverage<.5:
                    audit.append({**keys0,'status':'excluded_target_coverage','coverage':coverage,'history_audit':c['audit']});continue
                ht=pd.DatetimeIndex(hist.time_utc);tt=pd.DatetimeIndex(target.time_utc)
                qh=hist.q_at_time_cms.to_numpy(float);qt=target.q_at_time_cms.to_numpy(float)
                training_contexts=make_context(ht,qh,c['q_scale'])
                fmap=RFFFeatureMap.fit(training_contexts[np.isfinite(qh)&(qh>=0)],n_frequencies=4,length_scale=1.,seed=seed)
                spec=CONFIGS[args.config_id]
                library=build_reference_library(ht,qh,feature_map=fmap,q_scale=c['q_scale'],delay_hours=args.delay_hours,
                                                lookahead_hours=spec['lookahead_hours'],max_contexts=96,seed=seed)
                cfg=ValueSamplingConfig(**spec,noise_variance=c['audit']['noise_variance_forward_mse'],
                                        prior_variance=c['audit']['noise_variance_forward_mse'],delay_hours=args.delay_hours,
                                        min_spacing_hours=24,candidate_interval_hours=6,noise_adaptation_rate=args.noise_adaptation_rate)
                hidden=target.nox_at_time_mg_l.to_numpy(float)
                valid_hidden=target.nox_sample_reference_ok.fillna(False).to_numpy(bool)
                no_attempts=pd.DataFrame({'sample_index':pd.Series(dtype=int),'label_success':pd.Series(dtype=bool),
                                          'label_available_by_horizon':pd.Series(dtype=bool)})
                no_stats,no_events=evaluate(target,c['target_base'],c['events'],no_attempts,.95)
                no_key={**keys0,'budget':0,'policy':'no_new_labels','mode':'online'}
                metrics.append({**no_key,**no_stats,**additional_metrics(target,c['target_base'])})
                event_rows.extend({**no_key,**r} for r in no_events)
                for budget in args.budgets:
                    for policy in args.policies:
                        plan=None;method=policy
                        if policy in c['design_order']:
                            plan=planned_calendar_indices(tt,c['design_order'][policy],budget)
                            method='fixed_calendar'
                        res=run_value_replay(time=tt,q_cms=qt,base_prediction=c['target_base'],
                                             concentration_hidden=hidden,label_valid_hidden=valid_hidden,
                                             feature_map=fmap,reference_library=library,q_scale=c['q_scale'],
                                             policy=method,budget=budget,config=cfg,seed=seed,preplanned_indices=plan)
                        k={**keys0,'budget':budget,'policy':policy,'mode':'online'}
                        modes={'online':res.online_prediction}
                        if any(mode!='online' for mode in args.reconstruction_modes):
                            returned=res.attempts.loc[res.attempts.label_available_by_horizon.astype(bool)]
                            idx=returned.sample_index.to_numpy(int)
                            observed=returned.observed_mg_l.to_numpy(float)
                            timeline=np.arange(len(target))
                            if len(idx):
                                modes['retrospective_residual']=np.maximum(c['target_base']+np.interp(timeline,idx,observed-c['target_base'][idx]),0)
                                modes['retrospective_linear']=np.maximum(np.interp(timeline,idx,observed),0)
                            else:
                                modes['retrospective_residual']=c['target_base'].copy()
                                modes['retrospective_linear']=c['target_base'].copy()
                        for mode in args.reconstruction_modes:
                            prediction=modes[mode]
                            stats,ev=evaluate(target,prediction,c['events'],res.attempts,.95)
                            metrics.append({**k,'mode':mode,**stats,**additional_metrics(target,prediction)})
                            event_rows.extend({**k,'mode':mode,**r} for r in ev)
                        attempt_rows.extend({**k,**r} for r in res.attempts.to_dict('records'))
                        if seed==args.seeds[0] and len(res.query_trace):
                            traces.append(res.query_trace.assign(**k))
                        if args.save_predictions and seed==args.seeds[0]:
                            predictions.append(pd.DataFrame({'time_utc':tt,**k,'prediction':res.online_prediction,
                                                              'base_prediction':c['target_base'],'latent_variance':res.latent_variance,
                                                              'q_at_time_cms':qt,'reference_nox_at_time':hidden,
                                                              'valid_hour':target.valid_hour.fillna(False).to_numpy(bool)}))
                audit.append({**keys0,'status':'evaluated','hour_coverage':coverage,'events_all':len(c['events']),
                              'config':asdict(cfg),'history_audit':c['audit']})
                # Checkpoint accumulated tabular outcomes after each site/seed;
                # a missing final manifest means the run is not complete.
                pd.DataFrame(metrics).to_csv(out/'metrics.csv',index=False)
                print(json.dumps({**keys0,'rows':len(metrics),'elapsed_seconds':round(time.perf_counter()-tick,1)}),flush=True)
    pd.DataFrame(metrics).to_csv(out/'metrics.csv',index=False)
    pd.DataFrame(event_rows).to_csv(out/'events.csv',index=False)
    pd.DataFrame(attempt_rows).to_csv(out/'sampling_attempts.csv',index=False)
    if traces:pd.concat(traces,ignore_index=True).to_parquet(out/'query_trace.parquet',index=False)
    if predictions:pd.concat(predictions,ignore_index=True).to_parquet(out/'predictions.parquet',index=False)
    (out/'model_audit.json').write_text(json.dumps(audit,indent=2,default=str),encoding='utf-8')
    manifest={'arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
              'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
              'elapsed_seconds':time.perf_counter()-tick,'cpu_seconds':time.process_time()-cpu,
              'data_sha256':source_hash,'config':CONFIGS[args.config_id],
              'code_sha256':{f:frame_digest(ROOT/'scripts'/f) for f in CORE_FILES},'metric_rows':len(metrics),
              'freeze_sha256':frame_digest(args.freeze_manifest) if args.freeze_manifest else None}
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(str(out),flush=True)

if __name__=='__main__':main()
