"""Independent, all-cell audit of post-result fixed-calendar reconstructors.

Does not import reconstruction_sensitivity, model fitting, production evaluation,
or the production aggregation routine. Existing context files are read only.
"""
from pathlib import Path
import hashlib,json,subprocess,sys
import joblib
import numpy as np
import pandas as pd
from verify_paper_results import Checks,digest,table,independent_events

ROOT=Path(__file__).resolve().parents[1]
KEY=['site','year','seed','budget','policy','mode']
GROUP=['stage','config_id','delay_hours','noise_adaptation_rate','mode','budget']
MEASURES=['event_mean_absolute_relative_error','absolute_valid_window_bias','hourly_load_normalized_absolute_error','concentration_mae_mg_l','event_missed_fraction','attempts','successful_samples']
MODES=['online_last_residual_fixed_calendar','online_sample_hold_fixed_calendar']

def resolve(p):
    p=Path(p);return p if p.is_absolute() else ROOT/p

def local_predictions(base,attempt):
    """Segment construction, rather than production searchsorted reconstruction."""
    n=len(base);held=base.copy();residual=base.copy()
    arrivals=attempt.loc[attempt.label_available_by_horizon].sort_values('arrival_index').to_dict('records')
    for k,item in enumerate(arrivals):
        lo=int(item['arrival_index']);hi=int(arrivals[k+1]['arrival_index']) if k+1<len(arrivals) else n
        if lo>=n:continue
        hi=min(hi,n);observed=float(item['observed_mg_l']);sample=int(item['sample_index'])
        held[lo:hi]=observed
        age=np.arange(hi-lo,dtype=float)
        residual[lo:hi]=base[lo:hi]+(observed-base[sample])*np.exp(-age/168.)
    return {MODES[0]:np.clip(residual,0,None),MODES[1]:np.clip(held,0,None)}

def evaluate_independent(target,pred,specs,attempt):
    q=target.q_at_time_cms.to_numpy(float);ref=target.load_kg.to_numpy(float);vol=target.observed_volume_m3.to_numpy(float)
    valid=target.valid_hour.to_numpy(bool)&np.isfinite(ref)&np.isfinite(vol)&(vol>=0)
    pload=pred*vol/1000.;n=len(target);samples=attempt.sample_index.to_numpy(int)
    success=attempt.loc[attempt.label_success,'sample_index'].to_numpy(int)
    ev=[]
    for eid,(lo,hi) in enumerate(specs):
        support=valid[lo:hi];cov=float(support.mean())
        uncertain=lo<24 or hi+24>n or not np.isfinite(q[max(0,lo-24):lo]).all() or not np.isfinite(q[hi:min(n,hi+24)]).all()
        qualified=cov>=.95 and not uncertain;rl=float(ref[lo:hi][support].sum());ml=float(pload[lo:hi][support].sum())
        ev.append({'event_id':eid,'start_time':target.time_utc.iloc[lo],'end_time':target.time_utc.iloc[hi-1]+pd.Timedelta(hours=1),'hours':hi-lo,'coverage':cov,'eligible':qualified,'boundary_uncertain':uncertain,'reference_valid_window_load_kg':rl,'predicted_valid_window_load_kg':ml,'relative_error':(ml-rl)/rl if qualified and rl>1e-8 else np.nan,'sample_attempts':int(((samples>=lo)&(samples<hi)).sum()),'successful_samples':int(((success>=lo)&(success<hi)).sum()),'q_peak_cms':float(np.nanmax(q[lo:hi]))})
    event=pd.DataFrame(ev);errors=event.relative_error.abs().dropna().to_numpy() if len(event) else np.array([])
    refsum=float(ref[valid].sum());predsum=float(pload[valid].sum());truth=target.nox_at_time_mg_l.to_numpy(float)
    grab=target.nox_sample_reference_ok.to_numpy(bool)&np.isfinite(truth)
    stats={'hours':n,'valid_hours':int(valid.sum()),'hour_coverage':float(valid.mean()),'reference_valid_window_load_kg':refsum,'predicted_valid_window_load_kg':predsum,'valid_window_relative_bias':(predsum-refsum)/refsum if refsum>0 else np.nan,'concentration_mae_mg_l':float(np.abs(pred[grab]-truth[grab]).mean()) if grab.any() else np.nan,'events_all':len(specs),'events_eligible':len(errors),'event_median_absolute_relative_error':float(np.median(errors)) if len(errors) else np.nan,'event_mean_absolute_relative_error':float(errors.mean()) if len(errors) else np.nan,'event_missed_fraction':float(event.loc[event.eligible,'sample_attempts'].eq(0).mean()) if len(event) and event.eligible.any() else np.nan,'all_event_missed_fraction':float(event.sample_attempts.eq(0).mean()) if len(event) else np.nan,'all_event_no_usable_label_fraction':float(event.successful_samples.eq(0).mean()) if len(event) else np.nan,'events_boundary_uncertain':int(event.boundary_uncertain.sum()) if len(event) else 0,'attempts':len(attempt),'successful_samples':int(attempt.label_success.sum()),'returned_by_horizon':int(attempt.label_available_by_horizon.sum()),'hourly_load_normalized_absolute_error':float(np.abs(pload[valid]-ref[valid]).sum()/refsum) if refsum>0 else np.nan}
    return stats,ev

def verify_frame(checks,name,computed,reported,keys):
    checks.add(name+'_unique',not reported.duplicated(keys).any())
    left=computed.set_index(keys).sort_index();right=reported.set_index(keys).sort_index()
    checks.add(name+'_index',left.index.equals(right.index),{'computed':len(left),'reported':len(right)})
    if not left.index.equals(right.index):return
    for col in left:
        if col not in right:checks.add(name+'_column_present',False,col);continue
        a,b=left[col],right[col]
        if pd.api.types.is_numeric_dtype(a):ok=np.allclose(a.to_numpy(float),b.to_numpy(float),rtol=1e-8,atol=1e-9,equal_nan=True)
        else:ok=bool((a.eq(b)|(a.isna()&b.isna())).all())
        checks.add(name+'_'+col,bool(ok))

def bootstrap_interval(frame,cluster):
    """Multiplicity-weight resampling of clusters, keeping the equal-site ratio."""
    grouped=[g.difference.to_numpy(float) for _,g in frame.groupby(cluster,sort=True)]
    n=len(grouped)
    if n<2:return np.nan,np.nan
    choices=np.random.default_rng(271828).integers(n,size=(10000,n))
    multiplicities=np.stack([(choices==i).sum(axis=1) for i in range(n)],axis=1)
    total=np.array([x.sum() for x in grouped]);size=np.array([len(x) for x in grouped])
    sampled=(multiplicities@total)/(multiplicities@size)
    return tuple(np.quantile(sampled,[.025,.975]))

def main():
    checks=Checks();run_reports=[];frames=[];manifests=[];cache_records=[]
    data_path=ROOT/'datasets/extended_hourly_2019_2025_v1.parquet';data_hash=digest(data_path);data=pd.read_parquet(data_path)
    station={(s,int(y)):g.reset_index(drop=True) for (s,y),g in data.groupby(['site',data.time_utc.dt.year])}
    code_key=hashlib.sha256((ROOT/'scripts/paper_context.py').read_bytes()+(ROOT/'scripts/replay.py').read_bytes()).hexdigest()[:12]
    cache_dir=ROOT/'cache/paper_contexts'/f'{data_hash[:12]}_{code_key}'
    for name in ['temporal_reconstruction_sensitivity_v1','external_reconstruction_sensitivity_v1']:
        folder=ROOT/'results/paper_runs'/name;manifest=json.loads((folder/'run_manifest.json').read_text());manifests.append(manifest)
        parent=resolve(manifest['arguments']['parent']);pm=json.loads((parent/'run_manifest.json').read_text())
        checks.add('diagnostic_parent_manifest_hash',digest(parent/'run_manifest.json')==manifest['parent_manifest_sha256'],name)
        checks.add('diagnostic_data_hash',manifest['data_sha256']==data_hash==pm['data_sha256'],name)
        checks.add('diagnostic_code_hash',digest(ROOT/'scripts/reconstruction_sensitivity.py')==manifest['code_sha256']['reconstruction_sensitivity.py'],name)
        checks.add('diagnostic_post_result_timing',pd.Timestamp(manifest['started_at_utc'])>pd.Timestamp(pm['completed_at_utc']),name)
        checks.add('diagnostic_status_explicit_post_result','post-result' in manifest['status'],name)
        prior=json.loads((parent/'independent_verification.json').read_text())
        for file in ['sampling_attempts.csv','metrics.csv','events.csv','predictions.parquet']:
            checks.add('audited_parent_artifact_unchanged',digest(parent/file)==prior['artifact_sha256'][file],name+'/'+file)
        for file,value in pm['code_sha256'].items():checks.add('parent_dependency_current_hash',digest(ROOT/'scripts'/file)==value,name+'/'+file)
        metrics=table(folder/'metrics.csv');events=table(folder/'events.csv');taken=table(parent/'sampling_attempts.csv');paid=table(parent/'metrics.csv')
        paid=paid[(paid['mode']=='online')&(paid.budget>0)]
        expected={tuple(r[k] for k in KEY[:-1])+(mode,) for r in paid.to_dict('records') for mode in MODES}
        checks.add('diagnostic_full_factorial',set(metrics[KEY].itertuples(index=False,name=None))==expected and not metrics.duplicated(KEY).any(),name)
        checks.eq('diagnostic_manifest_rows',manifest['metric_rows'],len(metrics),name)
        testsaved=pd.read_parquet(parent/'predictions.parquet',columns=['site','year','seed','time_utc','base_prediction'],filters=[('budget','==',24),('policy','==','uniform')])
        base_saved={(s,int(y),int(z)):g.sort_values('time_utc').base_prediction.to_numpy(float) for (s,y,z),g in testsaved.groupby(['site','year','seed'])}
        tgroups={k:g.sort_values('sample_index') for k,g in taken.groupby(['site','year','seed','budget','policy'])}
        egroups={k:g.sort_values('event_id') for k,g in events.groupby(KEY)}
        checked_rows=checked_events=0
        for (s,y,z),sub in metrics.groupby(['site','year','seed']):
            cp=cache_dir/f'{s}_{y}_{z}.joblib';checks.add('cache_exists_no_training_required',cp.exists(),str(cp))
            if not cp.exists():continue
            cache=joblib.load(cp);base=np.asarray(cache['target_base'],dtype=float);target=station[s,int(y)]
            if (s,y,z) in base_saved:checks.add('cached_base_matches_parent_saved_prediction',bool(np.array_equal(base,base_saved[s,y,z])),(s,y,z))
            checks.add('cache_predates_diagnostic',cp.stat().st_mtime<=pd.Timestamp(manifest['started_at_utc']).timestamp(),str(cp))
            cache_records.append({'site':s,'year':int(y),'seed':int(z),'file':str(cp),'mtime_utc':pd.Timestamp(cp.stat().st_mtime,unit='s',tz='UTC').isoformat()})
            hist=data[data.site.eq(s)&data.time_utc.dt.year.between(y-3,y-1)]
            q90=hist.q_at_time_cms.where(hist.q_sample_reference_ok).quantile(.9)
            specs=independent_events(target.q_at_time_cms.to_numpy(float),q90)
            for (budget,policy),cells in sub.groupby(['budget','policy']):
                attempt=tgroups[s,y,z,budget,policy];estimates=local_predictions(base,attempt)
                checks.eq('inherited_exact_attempt_budget',len(attempt),budget,(s,y,z,budget,policy))
                successful=attempt.loc[attempt.label_available_by_horizon]
                first=int(successful.arrival_index.min()) if len(successful) else len(base)
                for r in cells.to_dict('records'):
                    key=tuple(r[k] for k in KEY);pred=estimates[r['mode']]
                    checks.add('independent_no_prearrival_change',bool(np.array_equal(pred[:first],base[:first])),key)
                    stats,ev=evaluate_independent(target,pred,specs,attempt)
                    for field,val in stats.items():checks.eq('recomputed_metric_'+field,r[field],val,key)
                    original=egroups.get(key,pd.DataFrame());checks.eq('recomputed_event_count',len(original),len(ev),key)
                    for rr,expected_event in zip(original.to_dict('records'),ev):
                        for field,val in expected_event.items():checks.eq('recomputed_event_'+field,rr[field],val,key+(expected_event['event_id'],))
                    checked_rows+=1;checked_events+=len(ev)
            del cache
        frames.append(metrics)
        run_reports.append({'run':name,'contexts':int(metrics[['site','year','seed']].drop_duplicates().shape[0]),'metric_rows_checked':checked_rows,'event_rows_checked':checked_events,'all_7_policies_3_budgets_3_seeds_2_modes':True})
    # Aggregate independently from all verified cell metrics, averaging seeds,
    # then available years within station, then equally across stations.
    raw=pd.concat(frames,ignore_index=True);raw['absolute_valid_window_bias']=raw.valid_window_relative_bias.abs()
    registry=json.loads((ROOT/'datasets/extended_station_metadata_v1.json').read_text());huc={x['site']:x['huc4_group'] for x in registry}
    cols=MEASURES+['events_eligible','hour_coverage'];site_rows=[]
    for key,g in raw.groupby(GROUP+['policy','site','year'],sort=True):
        site_rows.append(dict(zip(GROUP+['policy','site','year'],key))|{c:float(g[c].mean()) for c in cols}|{'huc4':huc[key[-2]]})
    sy=pd.DataFrame(site_rows);analysis=ROOT/'results/paper_analysis_reconstructors'
    am=json.loads((analysis/'summary_manifest.json').read_text())
    checks.add('summary_manifest_run_sources',am['run_manifests']==manifests)
    checks.add('summary_script_hash',am['script_sha256']==digest(ROOT/'scripts/summarize_paper.py'))
    read=lambda n:pd.read_csv(analysis/n,dtype={'site':str,'huc4':str,'omitted_huc4':str})
    verify_frame(checks,'site_year_summary',sy,read('site_year_metrics.csv'),GROUP+['policy','site','year'])
    aggregates=[];pairs=[];leave=[]
    for minimum in [1,3]:
        qualifying=sy[sy.events_eligible>=minimum]
        for key,f in qualifying.groupby(GROUP):
            labels=dict(zip(GROUP,key));labels['minimum_events']=minimum
            for policy,g in f.groupby('policy'):
                bysite=g.groupby(['site','huc4'])[MEASURES].mean()
                aggregates.append(labels|{'policy':policy,'stations':len(bysite),'station_years':len(g),'huc4_groups':len(set(bysite.index.get_level_values('huc4'))),'unique_events':int(g.events_eligible.sum())}|{field:float(bysite[field].mean()) for field in MEASURES})
            value=f[f.policy.eq('value')]
            for baseline in sorted(set(f.policy)-{'value'}):
                common=value.merge(f[f.policy.eq(baseline)],on=['site','year','huc4'],suffixes=('_value','_baseline'),validate='one_to_one')
                for measure in MEASURES[:4]:
                    aa=common.dropna(subset=[measure+'_value',measure+'_baseline']).copy()
                    aa['difference']=aa[measure+'_baseline']-aa[measure+'_value']
                    diff=aa.groupby(['site','huc4'],sort=True).difference.mean().reset_index()
                    ci_station=bootstrap_interval(diff,'site');ci_huc=bootstrap_interval(diff,'huc4')
                    pairs.append(labels|{'measure':measure,'baseline':baseline,'stations':len(diff),'huc4_groups':diff.huc4.nunique(),'mean_improvement':float(diff.difference.mean()),'median_improvement':float(diff.difference.median()),'wins':int(diff.difference.gt(0).sum()),'ties':int(diff.difference.eq(0).sum()),'station_ci_low':ci_station[0],'station_ci_high':ci_station[1],'huc4_ci_low':ci_huc[0],'huc4_ci_high':ci_huc[1]})
                    if measure==MEASURES[0]:
                        for group in sorted(diff.huc4.unique()):leave.append(labels|{'baseline':baseline,'omitted_huc4':group,'mean_improvement':float(diff.loc[diff.huc4.ne(group),'difference'].mean())})
    verify_frame(checks,'aggregate_summary',pd.DataFrame(aggregates),read('aggregate_metrics.csv'),GROUP+['minimum_events','policy'])
    verify_frame(checks,'paired_summary',pd.DataFrame(pairs),read('paired_effects.csv'),GROUP+['minimum_events','measure','baseline'])
    verify_frame(checks,'leave_huc4_summary',pd.DataFrame(leave),read('leave_one_huc4_out.csv'),GROUP+['minimum_events','baseline','omitted_huc4'])
    whole=[]
    for key,g in sy.groupby(GROUP+['policy']):
        bysite=g.groupby('site')[MEASURES[1:4]+['hour_coverage']].mean()
        whole.append(dict(zip(GROUP+['policy'],key))|{field:float(bysite[field].mean()) for field in bysite})
    verify_frame(checks,'whole_window_summary',pd.DataFrame(whole),read('all_eligible_sites_window_metrics.csv'),GROUP+['policy'])
    # The existing tests are supporting evidence, distinct from the numerical
    # reconstruction above, which never invokes the production function.
    unit=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_reconstruction_sensitivity.py','-v'],cwd=ROOT,capture_output=True,text=True)
    checks.add('provided_unit_tests_pass',unit.returncode==0)
    source_files=[ROOT/'scripts/reconstruction_sensitivity.py',ROOT/'tests/test_reconstruction_sensitivity.py',ROOT/'scripts/summarize_paper.py']
    output={'status':'PASS' if not checks.failures else 'FAIL','checks':checks.counts,'failures':checks.failures,'warnings':checks.warnings,'run_scope':run_reports,'cache_records':cache_records,'source_hashes':{str(p.relative_to(ROOT)):digest(p) for p in source_files},'aggregation_files':{p.name:digest(p) for p in analysis.iterdir() if p.is_file()},'provided_unit_test_output':unit.stdout+unit.stderr,
            'independence':'All 87 station-year-seed contexts, seven policies, three budgets, two modes recomputed directly from unchanged parent attempts and pre-existing cached base arrays. Production reconstruct/evaluate/summary functions were not called by the independent calculations. No training, policy decision, or parameter change occurred.',
            'interpretation_boundaries':['Post-result descriptive analysis: sampling calendars are the realized calendars from the original closed loop, held fixed under alternative reconstruction. These are not newly simulated alternative closed-loop policies.','168 hours is a residual e-folding time measured from label arrival, not a half-life and not time since sample collection. The residual is observation minus frozen base prediction at SAMPLE time.','Both modes use only successful labels returned before the horizon. Failed samples do not overwrite the latest usable label.','The main-paper aggregation is seed mean, then available years within site, then equal-site mean. Median summaries in earlier independent run checks are supplementary diagnostics, not this paper estimand.','Existing supplied unit tests cover prearrival invariance, sample-time residual, and unreturned labels. They do not alone cover multiple arrivals, exact 168 h decay, failed-label gaps, or clipping; all real-run cells were independently recomputed here.']}
    dest=ROOT/'results/INDEPENDENT_RECONSTRUCTOR_CHECK.json';dest.write_text(json.dumps(output,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'status':output['status'],'runs':run_reports,'failures':checks.failures,'warnings':checks.warnings,'summary_rows':{'site_year':len(sy),'aggregate':len(aggregates),'paired':len(pairs),'leave_huc4':len(leave),'whole_window':len(whole)}},indent=2),flush=True)
    if checks.failures:raise SystemExit(1)

if __name__=='__main__':main()
