"""Isolated post-result candidate-value diagnostic, not a budget-feasible policy.

Candidates are fixed calendar dates. Future references determine evaluation
eligibility and realized errors only; never candidate dates or design scores.
The other purchases, future labels and their original innovation weights remain
fixed. An added label changes only the local latest-residual output until the
next scheduled successful response. There is no new acquisition feedback loop.
"""
from __future__ import annotations
import argparse, json, time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from revision_experiments import (ROOT, REV, source_hashes, get_history_cache,
    load_context, frame_digest, ORIGINAL_SITES, invariants)
from revision_state import (AgeResidualModel, RevisionSpec, PublicPending,
    run_revision_replay, build_scoring_libraries, _score)
from value_sampling import ValueSamplingConfig, RFFFeatureMap, make_context


def historical_state_at(i,attempts,z,base,cfg):
    """Read successful labels only after their true response index."""
    state=AgeResidualModel(z.shape[1],cfg,'sample')
    past_purchases=attempts.loc[attempts.sample_index<i].sort_values('arrival_index')
    pending=[]
    for r in past_purchases.itertuples():
        s,a=int(r.sample_index),int(r.arrival_index)
        item=PublicPending(s,a,z[s].copy(),float(r.measurement_variance_at_sample),
                           float(base[s]),float(r.prediction_at_sample))
        if a<=i:
            state.advance_to(a)
            if r.label_success:state.observe(item,float(r.observed_mg_l))
        else:
            # No inspection of success/concentration in the pending branch.
            pending.append(item)
    state.advance_to(i)
    return state,pending


def added_sample_prediction(base,baseline,attempts,*,sample_index,delay,observed,success,stop):
    """Local output branch with identical subsequent responses, no covariance refit."""
    result=np.array(baseline,copy=True)
    arrival=sample_index+delay
    if not success or arrival>=len(result):return result
    later=attempts.loc[attempts.label_available_by_horizon.astype(bool)&(attempts.arrival_index>arrival)]
    next_return=int(later.arrival_index.min()) if len(later) else len(result)
    end=min(stop,next_return,len(result))
    ix=np.arange(arrival,end)
    result[ix]=np.maximum(0.,np.asarray(base)[ix]+(observed-base[sample_index])*np.exp(-(ix-arrival)/168.))
    return result


def self_test():
    base=np.ones(200);pred=np.ones(200)
    a=pd.DataFrame({'sample_index':[0,96],'arrival_index':[24,120],
                    'label_available_by_horizon':[True,True]})
    p=added_sample_prediction(base,pred,a,sample_index=48,delay=24,observed=3.,success=True,stop=144)
    assert np.array_equal(p[:72],pred[:72])
    assert p[72]==3.
    assert np.isclose(p[96],1+2*np.exp(-24/168.))
    assert np.array_equal(p[120:],pred[120:])
    failed=added_sample_prediction(base,pred,a,sample_index=48,delay=24,observed=np.nan,success=False,stop=144)
    assert np.array_equal(failed,pred)
    return ['no change before actual arrival','arrival uses sample residual',
            'tau168 maintained','same next response restores baseline trajectory',
            'failed added sample cannot change output']


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-name',default='candidate_development_v1')
    p.add_argument('--sites',nargs='*')
    p.add_argument('--years',nargs='+',type=int,default=[2023,2024])
    p.add_argument('--data',type=Path,default=ROOT/'datasets/extended_hourly_2019_2025_v1.parquet')
    a=p.parse_args()
    if set(a.years)-{2023,2024}:p.error('Development only')
    checks=self_test();out=REV/'results'/('experiments_'+a.run_name)
    out.mkdir(parents=True,exist_ok=False)
    started=datetime.now(timezone.utc).isoformat();tick=time.perf_counter()
    hashes=source_hashes();hashes[str(Path(__file__).relative_to(ROOT))]=frame_digest(__file__)
    h=frame_digest(a.data)
    data=pd.read_parquet(a.data);data['site']=data.site.astype(str);data['time_utc']=pd.to_datetime(data.time_utc,utc=True)
    sites=sorted(set(data.site)&ORIGINAL_SITES)
    if a.sites:
        if set(a.sites)-set(sites):p.error('Only original development sites')
        sites=[s for s in sites if s in a.sites]
    rows,audit=[],[]
    for site in sites:
        for year in a.years:
            c=load_context(data,site,year,41,h)
            if c['status']!='ready':audit.append(c);continue
            target,hist=c['target'],c['history']
            if target.valid_hour.fillna(False).mean()<.5:
                audit.append({'site':site,'year':year,'status':'excluded_target_coverage'});continue
            tt,ht=pd.DatetimeIndex(target.time_utc),pd.DatetimeIndex(hist.time_utc)
            qh,qt=hist.q_at_time_cms.to_numpy(float),target.q_at_time_cms.to_numpy(float)
            fmap=RFFFeatureMap.fit(make_context(ht,qh,c['q_scale'])[np.isfinite(qh)&(qh>=0)],seed=41)
            context=make_context(tt,qt,c['q_scale']);z=fmap.transform(context)
            banks=build_scoring_libraries(ht,qh,feature_map=fmap,q_scale=c['q_scale'],actual_delay=24,seed=41)
            noise=c['audit']['noise_variance_forward_mse']
            cfg=ValueSamplingConfig(noise_variance=noise,prior_variance=noise,half_life_hours=2160,delay_hours=24)
            base=np.asarray(c['target_base'])
            hidden=target.nox_at_time_mg_l.to_numpy(float)
            hidden_ok=target.nox_sample_reference_ok.fillna(False).to_numpy(bool)
            baseline=run_revision_replay(time=tt,q_cms=qt,base_prediction=base,concentration_hidden=hidden,
                label_valid_hidden=hidden_ok,feature_map=fmap,scoring_libraries=banks,q_scale=c['q_scale'],
                policy='uniform',budget=96,config=cfg,spec=RevisionSpec(trace_counterfactual_scores=False),seed=41)
            checks_baseline=invariants(baseline,96,len(tt),24)
            selected=np.array([tt.get_loc(pd.Timestamp(year=year,month=m,day=15,hour=12,tz='UTC')) for m in range(1,13)])
            known_calendar=baseline.attempts.sample_index.to_numpy(int)
            for i in selected:
                state,pending=historical_state_at(int(i),baseline.attempts,z,base,cfg)
                # This score is computed before reading candidate or future truth.
                score,threshold,trigger,horizon=_score(state,pending,24,n=len(tt),i=int(i),time=tt,
                    context=context,fmap=fmap,q_scale=c['q_scale'],z=z[i],library=banks[24],cfg=cfg)
                already=bool(i in known_calendar)
                spacing=bool(np.all(np.abs(known_calendar-i)>=24))
                start=int(i+24);stop=min(start+72,len(tt));window=np.arange(start,stop)
                # Oracle access starts here, exclusively for post-selection scoring.
                sample_valid=bool(hidden_ok[i] and np.isfinite(hidden[i]) and hidden[i]>=0)
                mask=target.valid_hour.fillna(False).to_numpy(bool)[window]
                coverage=float(mask.mean()) if len(mask) else 0.
                ref=target.load_kg.to_numpy(float)[window]
                vol=target.observed_volume_m3.to_numpy(float)[window]*.001
                truth=float(np.sum(ref[mask]))
                branch=added_sample_prediction(base,baseline.online_prediction,baseline.attempts,
                    sample_index=int(i),delay=24,observed=float(hidden[i]),success=sample_valid,stop=stop)
                no=np.asarray(baseline.online_prediction)[window]*vol
                yes=branch[window]*vol
                no_error=float(np.sum(no[mask])-truth);yes_error=float(np.sum(yes[mask])-truth)
                reasons=[]
                if already:reasons.append('already_purchased')
                if not spacing:reasons.append('minimum_spacing_not_admissible')
                if not sample_valid:reasons.append('candidate_sample_failed')
                if len(window)!=72:reasons.append('window_truncated')
                if coverage<.95:reasons.append('reference_coverage_below_95pct')
                if truth<=1e-8:reasons.append('reference_load_not_positive')
                row={'site':site,'year':year,'seed':41,'stage':'development','budget':96,'policy':'uniform',
                    'reconstructor':'latest_residual_tau168_arrival','scenario':'isolated_added_sample',
                    'analysis_status':'revision_post_result_not_closed_loop_effect','sample_index':int(i),
                    'sample_time':tt[i],'arrival_index':start,'arrival_time':tt[start],
                    'window_stop_time':tt[stop-1]+pd.Timedelta(hours=1),'delay_hours':24,
                    'candidate_selected_by':'month_15_day_12_UTC_no_replacement',
                    'acquisition_score':score,'historical_score_threshold':threshold,'score_trigger':trigger,
                    'pending_count_at_candidate':len(pending),'already_purchased':already,
                    'minimum_spacing_admissible':spacing,'candidate_sample_success':sample_valid,
                    'window_reference_coverage':coverage,'window_reference_load_kg':truth,
                    'eligible_diagnostic':not reasons,'exclusion_reason':';'.join(reasons),
                    'no_added_sample_signed_error_kg':no_error,'added_sample_signed_error_kg':yes_error,
                    'no_added_sample_absolute_error_kg':abs(no_error),'added_sample_absolute_error_kg':abs(yes_error),
                    'absolute_error_reduction_kg':abs(no_error)-abs(yes_error),
                    'absolute_relative_error_reduction':(abs(no_error)-abs(yes_error))/truth if truth>1e-8 else np.nan,
                    'no_added_sample_hourly_absolute_error_kg':float(np.sum(np.abs(no[mask]-ref[mask]))),
                    'added_sample_hourly_absolute_error_kg':float(np.sum(np.abs(yes[mask]-ref[mask])))}
                rows.append(row)
            audit.append({'site':site,'year':year,'seed':41,'status':'evaluated','baseline_checks':checks_baseline,
                          'history_cache':get_history_cache(h,site,year,41),'history_audit':c['audit']})
            pd.DataFrame(rows).to_csv(out/'candidate_effects.csv',index=False)
            print(json.dumps({'site':site,'year':year,'candidate_rows':len(rows),'elapsed_seconds':time.perf_counter()-tick}),flush=True)
    pd.DataFrame(rows).to_csv(out/'candidate_effects.csv',index=False)
    (out/'model_audit.json').write_text(json.dumps(audit,indent=2,default=str),encoding='utf-8')
    now=source_hashes();now[str(Path(__file__).relative_to(ROOT))]=frame_digest(__file__)
    if now!=hashes:raise RuntimeError('Implementation changed during diagnostic')
    manifest={'arguments':{k:str(v) if isinstance(v,Path) else v for k,v in vars(a).items()},
        'analysis_status':'post_result_isolated_candidate_diagnostic_not_closed_loop_policy_effect',
        'candidate_rule':'15th day of every month at12UTC, seed41, no outcome-dependent replacement',
        'baseline':'B96 periodic calendar and latest-residual tau168 arrival output; all other purchases and innovation weights frozen',
        'future_information':'reference eligibility and realized error only; no candidate selection, threshold fitting, or acquisition feedback',
        'data_sha256':h,'code_sha256':hashes,'synthetic_checks_passed':checks,'candidate_rows':len(rows),
        'started_at_utc':started,'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds':time.perf_counter()-tick}
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
