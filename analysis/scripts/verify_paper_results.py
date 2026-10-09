"""Independent artifact validation, without fitting or selecting any policy.

Reads one completed run explicitly named on the command line. Temporal outcomes
are blocked unless --allow-2025 is explicitly supplied after holdout release.
No production evaluation or policy implementation is imported.
"""
from __future__ import annotations
import argparse,hashlib,itertools,json,zipfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL={'03346500','03374100','05447500','05465500','05482000','05484500','05595000','07144100'}
KEY=['site','year','seed','budget','policy','mode']
CKEY=['site','year','seed']
SOURCE_CACHE={}
NATIVE_PROBE_CACHE={}

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()

def close(a,b):
    try:return bool(np.isclose(float(a),float(b),rtol=1e-8,atol=1e-8,equal_nan=True))
    except (TypeError,ValueError):return a==b

def path_from(s):
    p=Path(s);return p if p.is_absolute() else ROOT/p

def table(path):
    try:
        f=pd.read_csv(path,dtype={'site':str})
    except pd.errors.EmptyDataError:return pd.DataFrame()
    for c in ['time_utc','start_time','end_time','sample_time','arrival_time']:
        if c in f:f[c]=pd.to_datetime(f[c],utc=True)
    for c in ['eligible','boundary_uncertain','label_success','label_available_by_horizon']:
        if c in f:
            if f[c].dtype!=bool:f[c]=f[c].astype(str).str.lower().eq('true')
    return f

def independent_events(q,threshold):
    points=np.flatnonzero(np.isfinite(q)&(q>=threshold))
    events=[]
    if not len(points):return events
    first=last=int(points[0])
    for point in points[1:]:
        point=int(point)
        if point-last>25 or not np.isfinite(q[last+1:point]).all():
            if last-first+1>=12:events.append((first,last+1))
            first=point
        last=point
    if last-first+1>=12:events.append((first,last+1))
    return events

class Checks:
    def __init__(self):self.counts={};self.failures=[];self.warnings=[]
    def add(self,name,ok,context=None):
        d=self.counts.setdefault(name,{'passed':0,'failed':0});d['passed' if ok else 'failed']+=1
        if not ok and len(self.failures)<100:self.failures.append({'check':name,'context':context})
    def eq(self,name,a,b,context=None):self.add(name,close(a,b),{'key':context,'observed':a,'expected':b})

def context_vectors(target):
    q=target.q_at_time_cms.to_numpy(float)
    valid=target.valid_hour.fillna(False).to_numpy(bool,copy=True)
    load=target.load_kg.to_numpy(float);vol=target.observed_volume_m3.to_numpy(float)
    valid &= np.isfinite(load)&np.isfinite(vol)&(vol>=0)
    return q,valid,load,vol

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path);p.add_argument('--batch-runs',nargs='+',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--allow-2025',action='store_true')
    p.add_argument('--compare-run',type=Path);p.add_argument('--native-probe',action='store_true')
    args=p.parse_args(argv)
    if args.batch_runs:
        if args.output:p.error('--output cannot be shared across a batch')
        failures=0
        for folder in args.batch_runs:
            command=['--run',str(folder)]
            if args.allow_2025:command+=['--allow-2025']
            if args.native_probe:command+=['--native-probe']
            if args.compare_run:command+=['--compare-run',str(args.compare_run)]
            try:main(command)
            except SystemExit as err:failures+=bool(err.code)
        if failures:raise SystemExit(1)
        return
    if not args.run:p.error('--run or --batch-runs is required')
    run=path_from(args.run)
    mp=run/'run_manifest.json'
    if not mp.exists():raise RuntimeError('Missing final run_manifest.json: run is incomplete, do not validate checkpoint metrics.')
    manifest=json.loads(mp.read_text());a=manifest['arguments']
    if 2025 in a['years'] and not args.allow_2025:raise RuntimeError('Temporal holdout results are locked; explicit --allow-2025 required after release.')
    c=Checks();source=path_from(a['data'])
    c.add('data_hash',digest(source)==manifest['data_sha256'])
    code_match={k:(ROOT/'scripts'/k).exists() and digest(ROOT/'scripts'/k)==v for k,v in manifest['code_sha256'].items()}
    if not all(code_match.values()):c.warnings.append({'current_code_drift':code_match,'meaning':'Run remains an archived execution; current code cannot stand in for its recorded version.'})
    if a.get('freeze_manifest'):
        fp=path_from(a['freeze_manifest']);c.add('freeze_exists',fp.exists())
        if fp.exists():
            freeze=json.loads(fp.read_text());fdata=freeze.get('data_sha256');fcode=freeze.get('code_sha256')
            if manifest.get('freeze_sha256'):c.add('freeze_file_hash',digest(fp)==manifest['freeze_sha256'])
            if fdata:c.add('freeze_data_hash',manifest['data_sha256']==fdata)
            else:c.warnings.append('Freeze schema has no top-level data_sha256; binding needs explicit review.')
            if fcode:
                c.add('freeze_core_code_hashes',all(manifest['code_sha256'].get(k)==v for k,v in fcode.items()))
            else:c.warnings.append('Freeze schema has no top-level code_sha256; binding needs explicit review.')
            if freeze.get('config_id'):c.eq('freeze_config_id',a['config_id'],freeze['config_id'])
            if freeze.get('selected_config'):c.eq('freeze_selected_config',a['config_id'],freeze['selected_config'])
            if freeze.get('config'):c.add('freeze_config',manifest['config']==freeze['config'])
            if freeze.get('selected_parameters'):c.add('freeze_selected_parameters',manifest['config']==freeze['selected_parameters'])
            if freeze.get('created_at_utc'):c.add('freeze_predates_run',pd.Timestamp(freeze['created_at_utc'])<=pd.Timestamp(manifest['started_at_utc']))
            for field in ['seeds','budgets','policies','reconstruction_modes']:
                if 'allowed_'+field in freeze:c.add('freeze_allowed_'+field,set(a[field])<=set(freeze['allowed_'+field]))
            if 'allowed_delays' in freeze:c.add('freeze_allowed_delay',a['delay_hours'] in freeze['allowed_delays'])
            if 'allowed_adaptation_rates' in freeze:c.add('freeze_allowed_adaptation',a['noise_adaptation_rate'] in freeze['allowed_adaptation_rates'])
            snapshot=fp.parent/'implementation_snapshot.zip'
            if snapshot.exists():
                with zipfile.ZipFile(snapshot) as z:
                    archived={Path(name).name:hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if not name.endswith('/')}
                c.add('freeze_snapshot_core_hashes',all(archived.get(k)==v for k,v in fcode.items()))
                if freeze.get('analysis_plan_sha256'):c.add('freeze_snapshot_analysis_plan',archived.get('FULL_PAPER_PLAN.md')==freeze['analysis_plan_sha256'])
                if 'freeze_manifest.json' in archived:c.add('freeze_snapshot_manifest',archived['freeze_manifest.json']==digest(fp))
            else:c.warnings.append('No implementation snapshot accompanies freeze; hashes alone cannot recover execution source.')
    elif a['stage']!='development':c.add('holdout_requires_freeze',False)
    metrics=table(run/'metrics.csv');events=table(run/'events.csv');attempts=table(run/'sampling_attempts.csv')
    audit=json.loads((run/'model_audit.json').read_text())
    source_key=(str(source.resolve()),manifest['data_sha256'])
    if source_key not in SOURCE_CACHE:
        data=pd.read_parquet(source);data['time_utc']=pd.to_datetime(data.time_utc,utc=True);data['site']=data.site.astype(str)
        SOURCE_CACHE[source_key]=data
    data=SOURCE_CACHE[source_key]
    c.add('metrics_unique',not metrics.duplicated(KEY).any());c.eq('manifest_metric_rows',len(metrics),manifest['metric_rows'])
    if len(events):c.add('event_keys_unique',not events.duplicated(KEY+['event_id']).any())
    if len(attempts):c.add('attempt_keys_unique',not attempts.duplicated(KEY+['sample_index']).any())
    sites=set(data.site)
    if a['stage']=='development':sites &= ORIGINAL
    if a['stage']=='external':sites -= ORIGINAL
    if a.get('sites'):sites &= set(a['sites'])
    requested=set(itertools.product(sites,a['years'],a['seeds']))
    actual=[(r['site'],r['year'],r['seed']) for r in audit]
    c.add('audit_requested_contexts_complete',set(actual)==requested and len(actual)==len(set(actual)),{'expected':len(requested),'actual':len(actual)})
    evaluated={(r['site'],r['year'],r['seed']):r for r in audit if r['status']=='evaluated'}
    expected=set()
    for x in evaluated:
        expected.add(x+(0,'no_new_labels','online'))
        expected.update(x+(b,pol,mode) for b,pol,mode in itertools.product(a['budgets'],a['policies'],a['reconstruction_modes']))
    actualkeys=set(metrics[KEY].itertuples(index=False,name=None))
    c.add('complete_metric_factorial',actualkeys==expected,{'expected':len(expected),'actual':len(actualkeys)})
    c.add('only_requested_years',set(metrics.year)<=set(a['years']))
    c.add('only_requested_seeds',set(metrics.seed)<=set(a['seeds']))
    if a['stage']=='development':c.add('development_original_sites_only',set(metrics.site)<=ORIGINAL)
    if a['stage']=='external':c.add('external_new_sites_only',not bool(set(metrics.site)&ORIGINAL))
    # Index small tables once; large source is grouped by station-year.
    targets={(s,int(y)):g.sort_values('time_utc').reset_index(drop=True) for (s,y),g in data.groupby(['site',data.time_utc.dt.year])}
    for ar in audit:
        if ar['status']=='evaluated':continue
        s,yy=ar['site'],ar['year'];hh=data[data.site.eq(s)&data.time_utc.dt.year.between(yy-3,yy-1)]
        good=hh.nox_sample_reference_ok&hh.q_sample_reference_ok&np.isfinite(hh.nox_at_time_mg_l)&hh.nox_at_time_mg_l.ge(0)&hh.q_at_time_cms.notna()
        counts=[int((good&hh.time_utc.dt.year.eq(y)).sum()) for y in range(yy-3,yy)]
        if ar['status']=='insufficient_history':c.add('exclusion_insufficient_history_verified',sum(n>=1000 for n in counts)<2,(s,yy,ar['seed']))
        elif ar['status']=='excluded_target_coverage':c.add('exclusion_target_coverage_verified',targets[s,yy].valid_hour.mean()<.5,(s,yy,ar['seed']))
        else:c.warnings.append({'unverified_context_exclusion':ar})
    agroups={k:g.sort_values('sample_index') for k,g in attempts.groupby(KEY)} if len(attempts) else {}
    egroups={k:g.sort_values('event_id') for k,g in events.groupby(KEY)} if len(events) else {}
    pgroups={};tracegroups={}
    if (run/'predictions.parquet').exists():
        predictions=pd.read_parquet(run/'predictions.parquet');predictions['time_utc']=pd.to_datetime(predictions.time_utc,utc=True)
        c.add('prediction_keys_unique',not predictions.duplicated(KEY+['time_utc']).any())
        pgroups={k:g.sort_values('time_utc') for k,g in predictions.groupby(KEY)}
    if (run/'query_trace.parquet').exists():
        trace=pd.read_parquet(run/'query_trace.parquet');trace['time_utc']=pd.to_datetime(trace.time_utc,utc=True)
        c.add('trace_keys_unique',not trace.duplicated(KEY+['time_utc']).any())
        tracegroups={k:g.sort_values('time_utc') for k,g in trace.groupby(KEY)}
    expected_saved={x+(b,pol,'online') for x in evaluated if x[2]==a['seeds'][0] for b,pol in itertools.product(a['budgets'],a['policies'])}
    c.add('trace_groups_complete_first_seed',set(tracegroups)==expected_saved)
    if a.get('save_predictions'):c.add('prediction_groups_complete_first_seed',set(pgroups)==expected_saved)
    prior_groups={}
    for k,g in pgroups.items():
        if k[:3] in prior_groups:c.add('same_prior_across_policies',bool(np.allclose(g.base_prediction,prior_groups[k[:3]].base_prediction)),k)
        else:prior_groups[k[:3]]=g
    event_specs={};native_probes=[]
    for x,ar in evaluated.items():
        site,year,seed=x;t=targets[site,year];q,valid,load,vol=context_vectors(t)
        c.eq('target_coverage_gate',valid.mean()>=.5,True,x)
        h=data[data.site.eq(site)&data.time_utc.dt.year.between(year-3,year-1)]
        histq=h.q_at_time_cms.where(h.q_sample_reference_ok.fillna(False))
        ha=ar['history_audit'];c.eq('past_only_q90',ha['q90'],histq.quantile(.9),x)
        c.eq('past_only_q_scale',ha['q_scale'],histq.median(),x)
        c.add('training_strictly_past',pd.Timestamp(ha['training_last_timestamp'])<t.time_utc.iloc[0],x)
        good=h.nox_sample_reference_ok&h.q_sample_reference_ok&np.isfinite(h.nox_at_time_mg_l)&h.nox_at_time_mg_l.ge(0)&h.q_at_time_cms.notna()
        counts={yy:int((good&h.time_utc.dt.year.eq(yy)).sum()) for yy in range(year-3,year)}
        c.add('historical_label_counts',counts=={int(k):v for k,v in ha['history_valid_counts'].items()},x)
        c.add('historical_label_gate',sum(n>=1000 for n in counts.values())>=2,x)
        c.add('forward_calibration_year',ha['calibration_year']==max(yy for yy,n in counts.items() if n>=1000) and ha['calibration_year']<year,x)
        specs=independent_events(q,ha['q90']);event_specs[x]=specs
        c.eq('event_definition_count',ar['events_all'],len(specs),x)
        if args.native_probe and specs and seed==a['seeds'][0] and source.name=='extended_hourly_2019_2025_v1.parquet':
            lo,hi=specs[0];npth=source.with_name('extended_native_2019_2025_v1.parquet')
            pk=source_key+(site,year,lo,hi)
            if pk not in NATIVE_PROBE_CACHE:
                native=pd.read_parquet(npth,columns=['time_utc','q_cms','nox_mg_l','joint_reference_ok'],filters=[('site','==',site),('time_utc','>=',t.time_utc.iloc[lo]),('time_utc','<',t.time_utc.iloc[hi-1]+pd.Timedelta(hours=1))])
                native=native[native.joint_reference_ok].copy();native['time_utc']=native.time_utc.dt.floor('h')
                native['mass']=native.q_cms*native.nox_mg_l*.9;native['volume']=native.q_cms*900
                ng=native.groupby('time_utc').agg(mass=('mass','sum'),volume=('volume','sum'),count=('mass','size'))
                hh=t.iloc[lo:hi].set_index('time_utc').join(ng);goodcount=hh.native_joint_count.gt(0)
                ok=np.allclose(hh.loc[goodcount,'load_kg'],hh.loc[goodcount,'mass']) and np.allclose(hh.loc[goodcount,'observed_volume_m3'],hh.loc[goodcount,'volume'])
                NATIVE_PROBE_CACHE[pk]=(bool(ok),len(native))
            ok,raw_count=NATIVE_PROBE_CACHE[pk]
            c.add('native_event_probe_mass_and_volume',ok,x);native_probes.append({'site':site,'year':year,'event_id':0,'native_rows':raw_count})
    # Failed/excluded contexts must account for all requested contexts, without
    # silently creating metrics for them. Model audit supplies the reason.
    for row in metrics.to_dict('records'):
        key=tuple(row[k] for k in KEY);x=key[:3];t=targets[x[:2]];q,valid,load,vol=context_vectors(t);n=len(t)
        ak=key[:-1]+('online',);attempt=agroups.get(ak,pd.DataFrame());ev=egroups.get(key,pd.DataFrame());pred=pgroups.get(ak)
        if row['policy']=='no_new_labels' and x in prior_groups:
            pred=prior_groups[x].assign(prediction=prior_groups[x].base_prediction)
        if len(attempt):
            ix=attempt.sample_index.to_numpy(int);ai=attempt.arrival_index.to_numpy(int)
            success=attempt.label_success.to_numpy(bool);returned=attempt.label_available_by_horizon.to_numpy(bool)
            c.add('attempt_exact_budget',len(attempt)==row['budget'],key)
            c.add('attempt_spacing_24h',bool(np.all(np.diff(ix)>=24)),key)
            c.add('attempt_candidate_6h',bool(np.all(ix%6==0)),key)
            c.add('attempt_horizon',bool(np.all((ix>=0)&(ix<n))),key)
            c.add('attempt_delay_index',bool(np.all(ai-ix==a['delay_hours'])),key)
            c.add('attempt_sample_timestamp',pd.DatetimeIndex(attempt.sample_time).equals(pd.DatetimeIndex(t.time_utc.iloc[ix])),key)
            c.add('attempt_arrival_timestamp',bool(((attempt.arrival_time-attempt.sample_time)==pd.Timedelta(hours=a['delay_hours'])).all()),key)
            sv=t.nox_sample_reference_ok.to_numpy(bool)[ix]&np.isfinite(t.nox_at_time_mg_l.to_numpy(float)[ix])&t.nox_at_time_mg_l.to_numpy(float)[ix].__ge__(0)
            c.add('sample_QC_success',bool(np.array_equal(success,sv)),key)
            c.add('sample_QC_values',bool(np.allclose(attempt.observed_mg_l.to_numpy(float)[success],t.nox_at_time_mg_l.to_numpy(float)[ix[success]],equal_nan=True)),key)
            c.add('sample_failed_value_hidden',bool(attempt.observed_mg_l.loc[~success].isna().all()),key)
            c.add('return_horizon_definition',bool(np.array_equal(returned,success&(ai<n))),key)
        else:
            ix=ai=np.array([],dtype=int);success=returned=np.array([],dtype=bool)
            c.add('zero_reference_no_attempts',row['budget']==0 and row['policy']=='no_new_labels',key)
        for field,value in [('attempts',len(ix)),('successful_samples',int(success.sum())),('returned_by_horizon',int(returned.sum())),('hours',n),('valid_hours',int(valid.sum())),('hour_coverage',float(valid.mean())),('reference_valid_window_load_kg',float(load[valid].sum()))]:c.eq('metric_'+field,row[field],value,key)
        specs=event_specs[x];c.eq('events_per_metric',len(ev),len(specs),key)
        for (lo,hi),r in zip(specs,ev.to_dict('records')):
            cov=float(valid[lo:hi].mean())
            if 'paper_metrics.py' in manifest['code_sha256']:
                boundary=lo<24 or hi+24>n or not np.isfinite(q[max(0,lo-24):lo]).all() or not np.isfinite(q[hi:min(n,hi+24)]).all()
            else:boundary=lo==0 or hi==n or not np.isfinite(q[lo-1]) or not np.isfinite(q[hi])
            eligible=cov>=.95 and not boundary
            reference=float(load[lo:hi][valid[lo:hi]].sum());rel=(r['predicted_valid_window_load_kg']-reference)/reference if eligible and reference>1e-8 else np.nan
            vals={'hours':hi-lo,'coverage':cov,'boundary_uncertain':boundary,'eligible':eligible,'reference_valid_window_load_kg':reference,'relative_error':rel,'sample_attempts':int(((ix>=lo)&(ix<hi)).sum()),'successful_samples':int(((ix[success]>=lo)&(ix[success]<hi)).sum()),'q_peak_cms':float(np.nanmax(q[lo:hi]))}
            c.add('event_exact_time_support',r['start_time']==t.time_utc.iloc[lo] and r['end_time']==t.time_utc.iloc[hi-1]+pd.Timedelta(hours=1),key)
            for field,value in vals.items():c.eq('event_'+field,r[field],value,key+(r['event_id'],))
        errs=ev.relative_error.abs().dropna().to_numpy() if len(ev) else np.array([])
        vals={'events_all':len(specs),'events_eligible':len(errs),'event_mean_absolute_relative_error':float(errs.mean()) if len(errs) else np.nan,'event_median_absolute_relative_error':float(np.median(errs)) if len(errs) else np.nan,'events_boundary_uncertain':int(ev.boundary_uncertain.sum()) if len(ev) else 0,
              'event_missed_fraction':float(ev.loc[ev.eligible,'sample_attempts'].eq(0).mean()) if len(ev) and ev.eligible.any() else np.nan,'all_event_missed_fraction':float(ev.sample_attempts.eq(0).mean()) if len(ev) else np.nan,'all_event_no_usable_label_fraction':float(ev.successful_samples.eq(0).mean()) if len(ev) else np.nan}
        for field,value in vals.items():c.eq('aggregate_'+field,row[field],value,key)
        c.eq('aggregate_window_bias',row['valid_window_relative_bias'],(row['predicted_valid_window_load_kg']-row['reference_valid_window_load_kg'])/row['reference_valid_window_load_kg'] if row['reference_valid_window_load_kg']>0 else np.nan,key)
        if pred is not None:
            estimate=pred.prediction.to_numpy(float)
            c.add('prediction_time_alignment',pd.DatetimeIndex(pred.time_utc).equals(pd.DatetimeIndex(t.time_utc)),key)
            c.add('prediction_finite_nonnegative',bool(np.isfinite(estimate).all() and (estimate>=0).all()),key)
            if row['mode']=='retrospective_residual':
                estimate=np.maximum(pred.base_prediction.to_numpy(float)+np.interp(np.arange(n),ix[returned],attempt.observed_mg_l.to_numpy(float)[returned]-pred.base_prediction.to_numpy(float)[ix[returned]]),0) if returned.any() else pred.base_prediction.to_numpy(float)
            elif row['mode']=='retrospective_linear':
                estimate=np.maximum(np.interp(np.arange(n),ix[returned],attempt.observed_mg_l.to_numpy(float)[returned]),0) if returned.any() else pred.base_prediction.to_numpy(float)
            pload=estimate*vol*.001
            c.eq('predicted_window_load_from_hours',row['predicted_valid_window_load_kg'],float(pload[valid].sum()),key)
            c.eq('hourly_load_NAE_from_hours',row['hourly_load_normalized_absolute_error'],float(np.abs(pload[valid]-load[valid]).sum()/load[valid].sum()),key)
            sample=t.nox_sample_reference_ok.to_numpy(bool)&np.isfinite(t.nox_at_time_mg_l.to_numpy(float))
            c.eq('concentration_MAE_from_hours',row['concentration_mae_mg_l'],float(np.abs(estimate[sample]-t.nox_at_time_mg_l.to_numpy(float)[sample]).mean()) if sample.any() else np.nan,key)
            for (lo,hi),r in zip(specs,ev.to_dict('records')):c.eq('predicted_event_load_from_hours',r['predicted_valid_window_load_kg'],float(pload[lo:hi][valid[lo:hi]].sum()),key+(r['event_id'],))
        if key in tracegroups:
            tr=tracegroups[key];received=np.searchsorted(np.sort(ai[success]),np.arange(n),side='right')
            pending=np.searchsorted(ix,np.arange(n),side='left')-np.searchsorted(ai,np.arange(n),side='right')
            c.add('trace_received_only_after_arrival',bool(np.array_equal(tr.received_labels.to_numpy(int),received)),key)
            c.add('trace_pending_before_action',bool(np.array_equal(tr.pending_labels.to_numpy(int),pending)),key)
            first=int(ai[success].min()) if success.any() else n
            c.add('trace_no_residual_before_first_arrival',bool(np.allclose(tr.residual_mean.to_numpy(float)[:first],0)),key)
            change=np.flatnonzero(np.abs(np.diff(tr.noise_variance.to_numpy(float)))>1e-10)+1
            c.add('noise_adapts_only_at_successful_arrival',set(change)<=set(ai[success]),key)
            if pred is not None:
                c.add('prediction_equals_base_plus_released_residual',bool(np.allclose(pred.prediction,np.maximum(pred.base_prediction.to_numpy()+tr.residual_mean.to_numpy(),0))),key)
    # Independently aggregate the primary estimand: event-mean absolute RE per
    # station/seed, then seed mean within station, then median across stations.
    primary=[]
    for (year,policy,budget,mode),g in metrics.groupby(['year','policy','budget','mode']):
        bysite=g.groupby('site').event_mean_absolute_relative_error.mean().dropna()
        primary.append({'year':int(year),'policy':policy,'budget':int(budget),'mode':mode,'station_count':len(bysite),'median_station_seed_mean_event_absRE':float(bysite.median()) if len(bysite) else None,'station_seed_means':bysite.to_dict()})
    if args.compare_run:
        otherpath=path_from(args.compare_run);other=json.loads((otherpath/'run_manifest.json').read_text())
        if 2025 in other['arguments']['years'] and not args.allow_2025:raise RuntimeError('Comparison would read locked temporal metadata; explicit release required.')
        c.add('comparison_same_data_hash',manifest['data_sha256']==other['data_sha256'])
        c.add('comparison_same_core_code_hashes',manifest['code_sha256']==other['code_sha256'])
    hashes={f.name:digest(f) for f in run.iterdir() if f.is_file() and f.name!='independent_verification.json'}
    result={'run':str(run),'status':'PASS' if not c.failures else 'FAIL','checks':c.counts,'failures':c.failures,'warnings':c.warnings,'current_code_matches':code_match,'artifact_sha256':hashes,'run_data_sha256':manifest['data_sha256'],
            'contexts_requested':len(requested),'contexts_evaluated':len(evaluated),'metric_rows':len(metrics),'event_rows':len(events),'attempt_rows':len(attempts),'prediction_groups':len(pgroups),'trace_groups':len(tracegroups),'native_probes':native_probes,'primary_aggregation':primary,
            'limitations':['Checks of arrival traces establish recorded-update timing; they do not replace causal-interface or hidden-label perturbation tests.','Hourly prediction recomputation is limited to saved prediction groups (normally first seed); event-row arithmetic is checked for every group.','Output hashes are generated by this audit and are not contemporaneous signatures of the original run.','Current code drift is reported separately; archived execution code cannot be reconstructed from hashes alone.']}
    out=args.output or run/'independent_verification.json';out=path_from(out)
    out.write_text(json.dumps(result,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['status','run','contexts_requested','contexts_evaluated','metric_rows','event_rows','attempt_rows','prediction_groups','trace_groups','failures','warnings']},indent=2),flush=True)
    if c.failures:raise SystemExit(1)

if __name__=='__main__':main()
