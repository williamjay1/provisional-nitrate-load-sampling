"""Paired station-level summaries; seeds/events are never independent replicates."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
KEYS=['stage','config_id','delay_hours','noise_adaptation_rate','mode','budget']
MEASURES=['event_mean_absolute_relative_error','absolute_valid_window_bias',
          'hourly_load_normalized_absolute_error','concentration_mae_mg_l',
          'event_missed_fraction','attempts','successful_samples']

def paired_interval(frame,cluster,replicates=10000):
    f=frame.dropna(subset=['difference',cluster]);groups=list(f.groupby(cluster).difference)
    if len(groups)<2:return [float('nan'),float('nan')]
    sums=np.array([v.sum() for _,v in groups]);counts=np.array([len(v) for _,v in groups])
    draws=np.random.default_rng(271828).integers(0,len(groups),size=(replicates,len(groups)))
    boot=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
    return np.quantile(boot,[.025,.975]).tolist()

def main():
    p=argparse.ArgumentParser();p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    frames=[];manifest=[]
    for run in a.runs:
        meta=json.loads((run/'run_manifest.json').read_text());manifest.append(meta)
        d=pd.read_csv(run/'metrics.csv',dtype={'site':str});d['run']=run.name;frames.append(d)
    d=pd.concat(frames,ignore_index=True)
    if d.duplicated(KEYS+['site','year','seed','policy']).any():raise ValueError('Duplicate experimental cells')
    d['absolute_valid_window_bias']=d.valid_window_relative_bias.abs()
    meta=json.loads((ROOT/'datasets/extended_station_metadata_v1.json').read_text())
    groups={x['site']:x['huc4_group'] for x in meta}
    siteyear=d.groupby(KEYS+['policy','site','year'],dropna=False)[MEASURES+['events_eligible','hour_coverage']].mean().reset_index()
    siteyear['huc4']=siteyear.site.map(groups)
    siteyear.to_csv(a.output/'site_year_metrics.csv',index=False)
    summaries=[];pairs=[];influence=[]
    for min_events in (1,3):
        primary=siteyear.loc[siteyear.events_eligible>=min_events]
        for key,frame in primary.groupby(KEYS,dropna=False):
            labels=dict(zip(KEYS,key))
            for policy,f in frame.groupby('policy'):
                station=f.groupby(['site','huc4'])[MEASURES].mean().reset_index()
                row={**labels,'minimum_events':min_events,'policy':policy,'stations':len(station),
                     'station_years':len(f),'huc4_groups':station.huc4.nunique(),
                     'unique_events':int(f.events_eligible.sum()),**station[MEASURES].mean().to_dict()}
                summaries.append(row)
            for measure in MEASURES[:4]:
                wide=frame.pivot_table(index=['site','year','huc4'],columns='policy',values=measure)
                if 'value' not in wide:continue
                if labels['mode']=='online' and labels['budget']>0:
                    z=primary.loc[(primary.policy=='no_new_labels')&(primary.budget==0)]
                    for field in KEYS:
                        if field!='budget':z=z.loc[z[field]==labels[field]]
                    if len(z):wide['no_new_labels']=z.set_index(['site','year','huc4'])[measure]
                for baseline in [x for x in wide if x!='value']:
                    paired=wide[[baseline,'value']].dropna().copy()
                    paired['difference']=paired[baseline]-paired['value']
                    paired=paired.reset_index().groupby(['site','huc4']).difference.mean().reset_index()
                    if not len(paired):continue
                    stci=paired_interval(paired,'site');gci=paired_interval(paired,'huc4')
                    pairs.append({**labels,'minimum_events':min_events,'measure':measure,'baseline':baseline,
                                  'stations':len(paired),'huc4_groups':paired.huc4.nunique(),
                                  'mean_improvement':paired.difference.mean(),'median_improvement':paired.difference.median(),
                                  'wins':int((paired.difference>0).sum()),'ties':int((paired.difference==0).sum()),
                                  'station_ci_low':stci[0],'station_ci_high':stci[1],
                                  'huc4_ci_low':gci[0],'huc4_ci_high':gci[1]})
                    if measure==MEASURES[0]:
                        for group in sorted(paired.huc4.unique()):
                            influence.append({**labels,'minimum_events':min_events,'baseline':baseline,'omitted_huc4':group,
                                              'mean_improvement':paired.loc[paired.huc4!=group,'difference'].mean()})
    pd.DataFrame(summaries).to_csv(a.output/'aggregate_metrics.csv',index=False)
    pd.DataFrame(pairs).to_csv(a.output/'paired_effects.csv',index=False)
    pd.DataFrame(influence).to_csv(a.output/'leave_one_huc4_out.csv',index=False)
    # Whole-window outcomes also retain sites that have no qualifying events.
    allwindow=siteyear.groupby(KEYS+['policy','site'])[MEASURES[1:4]+['hour_coverage']].mean().reset_index()
    allwindow.groupby(KEYS+['policy'])[MEASURES[1:4]+['hour_coverage']].mean().reset_index().to_csv(a.output/'all_eligible_sites_window_metrics.csv',index=False)
    out={'run_manifests':manifest,'bootstrap_replicates':10000,'bootstrap_seed':271828,
         'estimand':'seed mean, then available years within site, then equal site mean; groups are coarse HUC4 sensitivity, not certified independence',
         'difference':'baseline minus value; positive favors value',
         'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (a.output/'summary_manifest.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(a.output)
if __name__=='__main__':main()
