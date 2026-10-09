"""Revision experiment runner. All analyses are post-result, never unseen tests."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib, json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
REV = ROOT/'revision_20261009'
sys.path.insert(0,str(ROOT/'scripts'))
os.environ.setdefault('JOBLIB_TEMP_FOLDER',str(ROOT/'temp'))
import numpy as np
import pandas as pd
from paper_context import load_context, frame_digest, ORIGINAL_SITES
from paper_metrics import evaluate
from run_value_experiment import additional_metrics
from value_sampling import ValueSamplingConfig, RFFFeatureMap, make_context
from revision_state import (RevisionSpec, run_revision_replay, build_scoring_libraries,
                            reconstruct_fixed_calendar, SHORT_HALF_LIFE)

def source_hashes():
    files=[ROOT/'scripts'/n for n in ('paper_context.py','replay.py','paper_metrics.py','value_sampling.py')]
    files += [Path(__file__),Path(__file__).with_name('revision_state.py')]
    return {str(p.relative_to(ROOT)):frame_digest(p) for p in files}


def get_history_cache(data_hash,site,year,seed):
    code_hash=hashlib.sha256((ROOT/'scripts/paper_context.py').read_bytes()+
                            (ROOT/'scripts/replay.py').read_bytes()).hexdigest()[:12]
    p=ROOT/'cache/paper_contexts'/f'{data_hash[:12]}_{code_hash}'/f'{site}_{year}_{seed}.joblib'
    return {'path':str(p),'sha256':frame_digest(p)}


def invariants(result,budget,n,delay):
    a=result.attempts
    ix=a.sample_index.to_numpy(int)
    if len(a)!=budget or len(set(ix))!=budget or np.any(ix%6) or np.any(np.diff(ix)<24):
        raise AssertionError('Budget, candidate-grid or spacing violation')
    if len(a):
        if not np.all(a.arrival_index.to_numpy(int)-ix==delay):raise AssertionError('Actual delay changed')
        success=a.label_success.to_numpy(bool)
        available=a.label_available_by_horizon.to_numpy(bool)
        if not np.array_equal(available,success&(a.arrival_index.to_numpy(int)<n)):
            raise AssertionError('Return/success count mismatch')
        if (a.loc[success,'observed_mg_l']<0).any():raise AssertionError('Negative successful label')
    if not np.isfinite(result.online_prediction).all() or np.any(result.online_prediction<0):
        raise AssertionError('Invalid online output')
    return {'attempts':len(a),'successful_labels':int(a.label_success.sum()),
            'labels_arrived_within_horizon':int(a.label_available_by_horizon.sum()),
            'failed_attempts':int((~a.label_success).sum()),
            'minimum_spacing_hours':int(np.diff(ix).min()) if len(ix)>1 else None}


def experiment_rows(suite,budgets):
    if suite in ('systems','debug'):
        for budget in budgets:
            for policy in ('uniform','flow_trigger','deadline_only','value'):
                yield dict(policy=policy,budget=budget,delay_hours=24,scenario='delay_aware_pending',
                           assumed_delay=24,pending=True)
    elif suite=='mechanisms':
        for budget in budgets:
            for delay,scenario,assumed,pending in [
                (24,'delay_aware_pending',24,True),(24,'delay_zero_pending',0,True),
                (72,'delay_aware_pending',72,True),(72,'delay_zero_pending',0,True),
                (72,'delay_aware_omit_pending',72,False)]:
                yield dict(policy='value',budget=budget,delay_hours=delay,scenario=scenario,
                           assumed_delay=assumed,pending=pending)
    elif suite=='factorial':
        for policy in ('uniform','flow_trigger','deadline_only'):
            yield dict(policy=policy,budget=96,delay_hours=24,scenario='fixed_calendar_factorial',
                       assumed_delay=24,pending=True)
    else:raise ValueError(suite)


def self_test():
    """Synthetic timing, failure, clock and compatibility checks; no target fitting."""
    from value_sampling import run_value_replay
    from reconstruction_sensitivity import reconstruct
    from dataclasses import replace
    ht=pd.date_range('2021-01-01',periods=720,freq='h',tz='UTC')
    hq=2+np.sin(np.arange(720)/29)+.3*np.cos(np.arange(720)/7)
    fmap=RFFFeatureMap.fit(make_context(ht,hq,2.),seed=41)
    tt=pd.date_range('2023-01-01',periods=720,freq='h',tz='UTC')
    q=2+np.sin(np.arange(720)/23)
    base=np.full(720,2.)
    hidden=3+.5*np.sin(np.arange(720)/31)
    valid=np.ones(720,dtype=bool)
    banks=build_scoring_libraries(ht,hq,feature_map=fmap,q_scale=2.,actual_delay=24,max_contexts=24)
    cfg=ValueSamplingConfig(half_life_hours=2160)
    args=dict(time=tt,q_cms=q,base_prediction=base,concentration_hidden=hidden,
              label_valid_hidden=valid,feature_map=fmap,scoring_libraries=banks,q_scale=2.,
              policy='value',budget=12,config=cfg,seed=41)
    checks=[]
    def check(name,truth):
        if not truth:raise AssertionError(name)
        checks.append(name)
    r=run_revision_replay(**args)
    invariants(r,12,720,24)
    check('24h eligible candidate queue is empty',(r.query_trace.pending_count==0).all())
    s=int(r.attempts.sample_index.iloc[0]);arrival=s+24
    altered=hidden.copy();altered[s]+=10
    changed=run_revision_replay(**(args|{'concentration_hidden':altered}))
    check('purchased concentration invisible before arrival',np.array_equal(r.online_prediction[:arrival],changed.online_prediction[:arrival]))
    check('returned concentration changes output',r.online_prediction[arrival]!=changed.online_prediction[arrival])
    altered=hidden.copy();unbought=np.ones(720,dtype=bool);unbought[r.attempts.sample_index]=False
    altered[unbought]=1e6
    changed=run_revision_replay(**(args|{'concentration_hidden':altered}))
    check('unpurchased labels cannot change actions or predictions',
          np.array_equal(r.online_prediction,changed.online_prediction) and
          np.array_equal(r.attempts.sample_index,changed.attempts.sample_index))
    bad=valid.copy();bad[s]=False
    failed=run_revision_replay(**(args|{'label_valid_hidden':bad}))
    check('failure invisible until response',np.array_equal(r.online_prediction[:arrival],failed.online_prediction[:arrival]))
    check('failed attempt still consumes budget',len(failed.attempts)==12 and not failed.attempts.label_success.iloc[0])
    check('local replay matches previous 168h rule',np.allclose(r.online_prediction,reconstruct(base,r.attempts,'online_last_residual_fixed_calendar')))
    oldargs={k:v for k,v in args.items() if k!='scoring_libraries'}
    old=run_value_replay(**oldargs,reference_library=banks[24])
    new=run_revision_replay(**args,spec=RevisionSpec(output_family='rff_pooled',output_half_life=2160,output_age_basis='sample'))
    check('original RFF decision compatibility',np.array_equal(old.attempts.sample_index,new.attempts.sample_index))
    check('original RFF output compatibility',np.allclose(old.online_prediction,new.online_prediction,rtol=1e-12,atol=1e-12))
    deadline=run_revision_replay(**(args|{'policy':'deadline_only'}))
    bounds=np.linspace(0,720,13,dtype=int)
    expected=np.array([np.arange(bounds[i],bounds[i+1])[np.arange(bounds[i],bounds[i+1])%6==0][-1] for i in range(12)])
    check('pure deadline follows block endpoints',np.array_equal(deadline.attempts.sample_index,expected))
    check('pure deadline only uses fallback',(deadline.attempts.reason=='block_deadline').all())
    cfg72=replace(cfg,delay_hours=72)
    banks72=build_scoring_libraries(ht,hq,feature_map=fmap,q_scale=2.,actual_delay=72,max_contexts=24)
    long=run_revision_replay(**(args|{'config':cfg72,'scoring_libraries':banks72}))
    check('72h activates pending at eligible candidates',(long.query_trace.pending_count>0).any())
    aware=long.query_trace.query('pending_count > 0')
    check('pending changes score in activated queue',not np.allclose(aware.delay_aware_pending_score,aware.delay_aware_omit_score))
    zero=run_revision_replay(**(args|{'config':cfg72,'scoring_libraries':banks72}),spec=RevisionSpec(scoring_delay_hours=0))
    invariants(zero,12,720,72)
    check('ignoring scoring delay preserves real arrivals',np.all(zero.attempts.arrival_index-zero.attempts.sample_index==72))
    z=fmap.transform(make_context(tt,q,2.))
    fixed=reconstruct_fixed_calendar(base,z,r.attempts,family='latest_residual',half_life=SHORT_HALF_LIFE,age_basis='arrival',noise_variance=1.)
    check('half-life conversion equals tau168',np.allclose(fixed,r.online_prediction))
    check('sample age differs by delay attenuation',np.allclose(
        reconstruct_fixed_calendar(base,z,r.attempts,family='latest_residual',half_life=SHORT_HALF_LIFE,age_basis='sample',noise_variance=1.)-base,
        (fixed-base)*np.exp2(-24/SHORT_HALF_LIFE)))
    print(json.dumps({'synthetic_checks_passed':len(checks),'checks':checks}),flush=True)
    return checks


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--suite',choices=['debug','systems','factorial','mechanisms'],default='debug')
    p.add_argument('--stage',choices=['development','temporal','external'],default='development')
    p.add_argument('--years',nargs='+',type=int,default=[2023,2024])
    p.add_argument('--sites',nargs='*')
    p.add_argument('--seeds',nargs='+',type=int,default=[41,73,109])
    p.add_argument('--budgets',nargs='+',type=int,default=[24,48,96])
    p.add_argument('--data',type=Path,default=ROOT/'datasets/extended_hourly_2019_2025_v1.parquet')
    p.add_argument('--run-name')
    p.add_argument('--self-test',action='store_true')
    p.add_argument('--save-predictions',action='store_true')
    a=p.parse_args()
    if a.self_test:
        self_test()
        if not a.run_name:return
    if not a.run_name:p.error('--run-name is required for data replay')
    if a.suite=='factorial' and (a.stage!='development' or a.budgets!=[96]):p.error('Factorial is development only, B96')
    if a.stage=='temporal' and a.years!=[2025]:p.error('Temporal cohort is 2025')
    if a.stage!='temporal' and set(a.years)-{2023,2024}:p.error('Development/external cohorts are 2023/2024')
    start=time.perf_counter();started=datetime.now(timezone.utc).isoformat()
    hashes=source_hashes();data_hash=frame_digest(a.data)
    out=REV/'results'/('experiments_'+a.run_name)
    out.mkdir(parents=True,exist_ok=False)
    data=pd.read_parquet(a.data);data['site']=data.site.astype(str)
    data['time_utc']=pd.to_datetime(data.time_utc,utc=True)
    sites=sorted(set(data.site))
    if a.stage=='development':sites=[s for s in sites if s in ORIGINAL_SITES]
    elif a.stage=='external':sites=[s for s in sites if s not in ORIGINAL_SITES]
    if a.sites:
        if set(a.sites)-set(sites):p.error('Requested site is outside cohort')
        sites=[s for s in sites if s in a.sites]
    metrics,events,attempts,traces,predictions,audits=[],[],[],[],[],[]
    def record(c,keys,res,pred):
        stats,ev=evaluate(c['target'],pred,c['events'],res.attempts,.95)
        metrics.append(keys|stats|additional_metrics(c['target'],pred))
        events.extend(keys|r for r in ev)
        if a.save_predictions and keys['seed']==a.seeds[0]:
            predictions.append(pd.DataFrame({'time_utc':c['target'].time_utc,**keys,
                'prediction':pred,'base_prediction':c['target_base']}))
    for site in sites:
        for year in a.years:
            for seed in a.seeds:
                tick=time.perf_counter();c=load_context(data,site,year,seed,data_hash)
                key={'site':site,'year':year,'seed':seed,'stage':a.stage,'experiment':a.suite,
                     'analysis_status':'revision_post_result'}
                if c['status']!='ready':audits.append(key|c);continue
                coverage=float(c['target'].valid_hour.fillna(False).mean())
                if coverage<.5:
                    audits.append(key|{'status':'excluded_target_coverage','coverage':coverage});continue
                hist,target=c['history'],c['target'];ht=pd.DatetimeIndex(hist.time_utc);tt=pd.DatetimeIndex(target.time_utc)
                qh=hist.q_at_time_cms.to_numpy(float);qt=target.q_at_time_cms.to_numpy(float)
                xh=make_context(ht,qh,c['q_scale'])
                fmap=RFFFeatureMap.fit(xh[np.isfinite(qh)&(qh>=0)],n_frequencies=4,seed=seed)
                z=fmap.transform(make_context(tt,qt,c['q_scale']))
                banks={}
                for delay in [24,72] if a.suite=='mechanisms' else [24]:
                    banks[delay]=build_scoring_libraries(ht,qh,feature_map=fmap,q_scale=c['q_scale'],actual_delay=delay,seed=seed)
                input_args=dict(time=tt,q_cms=qt,base_prediction=c['target_base'],concentration_hidden=target.nox_at_time_mg_l.to_numpy(float),
                    label_valid_hidden=target.nox_sample_reference_ok.fillna(False).to_numpy(bool),feature_map=fmap,q_scale=c['q_scale'],seed=seed)
                # The historical-only comparator is repeated once per true delay.
                for delay in banks:
                    cfg=ValueSamplingConfig(half_life_hours=2160,noise_variance=c['audit']['noise_variance_forward_mse'],
                        prior_variance=c['audit']['noise_variance_forward_mse'],delay_hours=delay)
                    zero=run_revision_replay(**input_args,scoring_libraries=banks[delay],policy='uniform',budget=0,config=cfg)
                    keys=key|{'policy':'no_new_labels','budget':0,'delay_hours':delay,'scenario':'historical_only',
                              'reconstructor':'historical_forest','mode':'online'}
                    record(c,keys,zero,zero.online_prediction)
                case_audits=[]
                for case in experiment_rows(a.suite,a.budgets):
                    cfg=ValueSamplingConfig(half_life_hours=2160,noise_variance=c['audit']['noise_variance_forward_mse'],
                        prior_variance=c['audit']['noise_variance_forward_mse'],delay_hours=case['delay_hours'],
                        noise_adaptation_rate=0 if a.suite=='factorial' else .1)
                    spec=RevisionSpec(scoring_delay_hours=case['assumed_delay'],pending_aware=case['pending'])
                    res=run_revision_replay(**input_args,scoring_libraries=banks[case['delay_hours']],policy=case['policy'],
                                           budget=case['budget'],config=cfg,spec=spec)
                    checks=invariants(res,case['budget'],len(tt),case['delay_hours'])
                    keys=key|{k:case[k] for k in ('policy','budget','delay_hours','scenario')}
                    keys.update(reconstructor='latest_residual_tau168_arrival',mode='online',rho=cfg.noise_adaptation_rate,
                                assumed_delay_hours=case['assumed_delay'],pending_aware=case['pending'])
                    attempts.append(res.attempts.assign(**keys))
                    if len(res.query_trace):traces.append(res.query_trace.assign(**keys))
                    if a.suite=='factorial':
                        for family in ('rff_pooled','latest_residual'):
                            for half in (SHORT_HALF_LIFE,720.,2160.):
                                for age in ('sample','arrival'):
                                    pred=reconstruct_fixed_calendar(c['target_base'],z,res.attempts,
                                        family=family,half_life=half,age_basis=age,noise_variance=cfg.noise_variance)
                                    fkey=keys|{'reconstructor':f'{family}_half{half:.8f}_{age}',
                                        'reconstructor_family':family,'half_life_hours':half,'age_origin':age,'rho':0.,
                                        'mode':'online_fixed_calendar_factorial'}
                                    record(c,fkey,res,pred)
                    else:record(c,keys,res,res.online_prediction)
                    case_audits.append(case|checks|{'config':asdict(cfg),'revision_spec':asdict(spec),
                        'eligible_candidates':len(res.query_trace),'candidates_with_pending':int((res.query_trace.pending_count>0).sum())})
                audits.append(key|{'status':'evaluated','coverage':coverage,'history_audit':c['audit'],
                    'history_cache':get_history_cache(data_hash,site,year,seed),'cases':case_audits,
                    'context_elapsed_seconds':time.perf_counter()-tick})
                pd.DataFrame(metrics).to_csv(out/'metrics.csv',index=False)
                print(json.dumps(key|{'metric_rows':len(metrics),'context_seconds':round(time.perf_counter()-tick,3),
                                     'elapsed_seconds':round(time.perf_counter()-start,2)}),flush=True)
    pd.DataFrame(metrics).to_csv(out/'metrics.csv',index=False)
    pd.DataFrame(events).to_csv(out/'events.csv',index=False)
    if attempts:pd.concat(attempts,ignore_index=True).to_csv(out/'attempts.csv',index=False)
    if traces:pd.concat(traces,ignore_index=True).to_parquet(out/'candidate_trace.parquet',index=False)
    if predictions:pd.concat(predictions,ignore_index=True).to_parquet(out/'predictions.parquet',index=False)
    (out/'model_audit.json').write_text(json.dumps(audits,indent=2,default=str),encoding='utf-8')
    if source_hashes()!=hashes:raise RuntimeError('Implementation changed during run; outputs are not finalized')
    manifest={'arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},
        'analysis_status':'revision_post_result_not_unseen_validation','started_at_utc':started,
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':time.perf_counter()-start,
        'data_sha256':data_hash,'code_sha256':hashes,'metric_rows':len(metrics),'event_rows':len(events),
        'reconstructor_rule':'Latest returned residual with fixed tau168 (half-life168*ln2), arrival-age; chosen from prior observed diagnostic, not newly tuned',
        'acquisition_state':'Frozen C2 RFF covariance; innovation scale uses the actual published sample-time output',
        'output_path':str(out)}
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
