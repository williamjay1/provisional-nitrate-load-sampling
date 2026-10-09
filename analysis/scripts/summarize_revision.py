"""Station-paired revision summaries and an independent event-to-endpoint check."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
BASE=['stage','experiment','scenario','reconstructor','delay_hours','budget']
EXTRA=['reconstructor_family','half_life_hours','age_origin']
ID=['site','year','seed','policy']
MEASURES=['event_mean_absolute_relative_error','absolute_valid_window_bias',
          'hourly_load_normalized_absolute_error','concentration_mae_mg_l',
          'event_mean_signed_error_kg','event_mean_absolute_error_kg',
          'event_fraction_within_10pct','event_fraction_within_20pct',
          'event_fraction_worse_than_50pct','attempts','successful_samples']

def interval(frame,cluster):
    groups=list(frame.dropna(subset=['difference',cluster]).groupby(cluster).difference)
    if len(groups)<2:return np.nan,np.nan
    sums=np.array([v.sum() for _,v in groups]);counts=np.array([len(v) for _,v in groups])
    draws=np.random.default_rng(271828).integers(len(groups),size=(10000,len(groups)))
    values=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
    return np.quantile(values,[.025,.975])

def main():
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    metadata=json.loads((PROJECT/'datasets/extended_station_metadata_v1.json').read_text())
    hucs={x['site']:x['huc4_group'] for x in metadata}
    frames=[];evs=[];checks=[];sources=[]
    for run in a.runs:
        manifest=json.loads((run/'run_manifest.json').read_text())
        assert manifest,run
        m=pd.read_csv(run/'metrics.csv',dtype={'site':str});e=pd.read_csv(run/'events.csv',dtype={'site':str})
        for d in [m,e]:
            for field in EXTRA:
                if field not in d:d[field]='none'
                d[field]=d[field].fillna('none')
        key=BASE+EXTRA+ID
        assert not m.duplicated(key).any(),str(run)
        good=e.loc[e.eligible.astype(str).str.lower().isin(['true','1']) &
                   e.relative_error.notna() & (e.reference_valid_window_load_kg>1e-8)].copy()
        good['event_signed_error_kg']=good.predicted_valid_window_load_kg-good.reference_valid_window_load_kg
        good['event_absolute_error_kg']=good.event_signed_error_kg.abs()
        good['event_abs_relative_error']=good.relative_error.abs()
        for tol in [10,20,50]:good[f'event_flag_{tol}']=good.event_abs_relative_error.le(tol/100) if tol<50 else good.event_abs_relative_error.gt(.5)
        gg=good.groupby(key,dropna=False)
        calc=gg.agg(event_check=('event_abs_relative_error','mean'),
                    event_mean_signed_error_kg=('event_signed_error_kg','mean'),
                    event_mean_absolute_error_kg=('event_absolute_error_kg','mean'),
                    event_fraction_within_10pct=('event_flag_10','mean'),
                    event_fraction_within_20pct=('event_flag_20','mean'),
                    event_fraction_worse_than_50pct=('event_flag_50','mean')).reset_index()
        m=m.merge(calc,on=key,how='left',validate='one_to_one')
        err=(m.event_mean_absolute_relative_error-m.event_check).abs().dropna()
        assert err.empty or err.max()<1e-12,(run,err.max())
        checks.append({'run':run.name,'metrics':len(m),'eligible_event_rows':len(good),
                       'maximum_endpoint_discrepancy':float(err.max()) if len(err) else 0,'status':'PASS'})
        m['absolute_valid_window_bias']=m.valid_window_relative_bias.abs()
        m['huc4']=m.site.map(hucs);m['run']=run.name;frames.append(m);evs.append(good)
        sources.append({'run':run.name,'manifest':manifest,
                        'metrics_sha256':hashlib.sha256((run/'metrics.csv').read_bytes()).hexdigest(),
                        'events_sha256':hashlib.sha256((run/'events.csv').read_bytes()).hexdigest()})
    raw=pd.concat(frames,ignore_index=True);keys=BASE+EXTRA
    siteyear=raw.groupby(keys+['policy','site','year','huc4'],dropna=False)[MEASURES+['events_eligible','hour_coverage']].mean().reset_index()
    siteyear.to_csv(a.output/'site_year_metrics.csv',index=False)
    pd.concat(evs,ignore_index=True).to_csv(a.output/'eligible_events.csv',index=False)
    sums=[];pairs=[];leave=[];stationrows=[]
    for min_events in [1,3]:
        primary=siteyear.loc[siteyear.events_eligible>=min_events]
        for key,frame in primary.groupby(keys,dropna=False):
            labels=dict(zip(keys,key))
            for policy,f in frame.groupby('policy'):
                ss=f.groupby(['site','huc4'],dropna=False)[MEASURES].mean().reset_index()
                sums.append({**labels,'minimum_events':min_events,'policy':policy,'stations':len(ss),
                             'station_years':len(f),'events':int(f.events_eligible.sum()),
                             'huc4_groups':ss.huc4.nunique(),**ss[MEASURES].mean().to_dict()})
                for row in ss.to_dict('records'):stationrows.append({**labels,'minimum_events':min_events,'policy':policy,**row})
            for measure in MEASURES[:9]:
                wide=frame.pivot_table(index=['site','year','huc4'],columns='policy',values=measure)
                if 'value' not in wide:continue
                zero=primary.loc[(primary.policy=='no_new_labels')&(primary.budget==0)&(primary.stage==labels['stage'])&
                                 (primary.experiment==labels['experiment'])&(primary.delay_hours==labels['delay_hours'])]
                if len(zero):
                    zz=zero.groupby(['site','year','huc4'])[measure].mean()
                    wide['no_new_labels']=zz
                for baseline in [v for v in wide.columns if v!='value']:
                    w=wide[[baseline,'value']].dropna();delta=w[baseline]-w.value
                    if measure in ['event_fraction_within_10pct','event_fraction_within_20pct']:
                        # Difference remains baseline minus value; larger is better here.
                        pass
                    z=delta.rename('difference').reset_index().groupby(['site','huc4']).difference.mean().reset_index()
                    if z.empty:continue
                    st=interval(z,'site');hc=interval(z,'huc4')
                    pairs.append({**labels,'minimum_events':min_events,'measure':measure,'baseline':baseline,
                                  'stations':len(z),'mean_difference':z.difference.mean(),'median_difference':z.difference.median(),
                                  'candidate_lower':int((z.difference>0).sum()),
                                  'station_ci_low':st[0],'station_ci_high':st[1],
                                  'huc4_ci_low':hc[0],'huc4_ci_high':hc[1]})
                    if measure==MEASURES[0]:
                        for group in sorted(z.huc4.unique()):
                            leave.append({**labels,'minimum_events':min_events,'baseline':baseline,'omitted_huc4':group,
                                          'mean_difference':z.loc[z.huc4!=group,'difference'].mean()})
    pd.DataFrame(sums).to_csv(a.output/'aggregate_metrics.csv',index=False)
    pd.DataFrame(stationrows).to_csv(a.output/'station_metrics.csv',index=False)
    pd.DataFrame(pairs).to_csv(a.output/'paired_effects.csv',index=False)
    pd.DataFrame(leave).to_csv(a.output/'leave_one_huc4_out.csv',index=False)
    allwindows=siteyear.groupby(keys+['policy','site'],dropna=False)[MEASURES[1:4]+['hour_coverage']].mean().reset_index()
    allwindows.groupby(keys+['policy'],dropna=False)[MEASURES[1:4]+['hour_coverage']].mean().reset_index().to_csv(a.output/'all_sites_window_metrics.csv',index=False)
    (a.output/'summary_manifest.json').write_text(json.dumps({'status':'PASS','analysis_status':'revision_post_result',
        'sources':sources,'event_endpoint_checks':checks,'bootstrap_replicates':10000,'bootstrap_seed':271828,
        'estimand':'mean within station-year-seed events, across seeds, years within station, equal stations',
        'difference':'baseline minus value; positive favors lower candidate ERROR but not accuracy-scenario fraction',
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','output':str(a.output),'endpoint_checks':checks},indent=2))

if __name__=='__main__':main()
