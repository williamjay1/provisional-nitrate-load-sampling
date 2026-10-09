"""Prepare exact-timestamp sensor pairs; integrate Q*C before aggregating.

Pilot reference: fixed UTC quarter-hour left-rectangle quadrature. No imputation,
no load scaling for missing intervals, no averaging C and Q before multiplying.
valid_hour requires all four common approved/nonestimated uncensored observations.
This is a sensor-derived reference, not error-free laboratory truth.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import numpy as np
import pandas as pd

WORK = Path('D:/MLWork/NitrateAdaptiveSampling_20261005')
DATA = WORK/'datasets'
RESULTS = WORK/'results'

def read_records(manifests):
    chunks, variable_metadata, duplicates = [], [], []
    all_meta, requested_years = [], []
    for manifest in manifests:
        m = json.loads(Path(manifest).read_text(encoding='utf-8'))
        requested_years.extend(m['years'])
        all_meta.extend(m['metadata'])
        for rec in m['downloads']:
            with gzip.open(rec['path'], 'rt', encoding='utf-8') as f:
                j = json.load(f)
            for ts in j['value']['timeSeries']:
                site = ts['sourceInfo']['siteCode'][0]['value']
                parameter = ts['variable']['variableCode'][0]['value']
                variable_metadata.append({'site':site, 'year':rec['year'],
                    'source':ts['sourceInfo'], 'variable':ts['variable'],
                    'value_metadata':[{k:v for k,v in block.items() if k!='value'} for block in ts['values']]})
                for block in ts['values']:
                    v = pd.DataFrame(block['value'])
                    if v.empty:
                        continue
                    v['time_utc'] = pd.to_datetime(v['dateTime'], utc=True)
                    v['value'] = pd.to_numeric(v['value'], errors='coerce')
                    v['site'], v['parameter'] = site, parameter
                    v['qualifier'] = v['qualifiers'].apply(lambda x: '|'.join(x))
                    v['approved'] = v['qualifiers'].apply(lambda x: 'A' in x)
                    v['estimated'] = v['qualifiers'].apply(lambda x: any(q.lower()=='e' for q in x))
                    v['uncensored'] = v['qualifiers'].apply(lambda x: not any(q in ('<','>','&lt;','&gt;') for q in x))
                    v['numeric_valid'] = v['value'].ge(0) & np.isfinite(v['value'])
                    v['reference_ok'] = v['approved'] & ~v['estimated'] & v['uncensored'] & v['numeric_valid']
                    chunks.append(v[['site','parameter','time_utc','value','qualifier','approved','estimated','uncensored','numeric_valid','reference_ok']])
    long = pd.concat(chunks, ignore_index=True)
    keys=['site','parameter','time_utc']
    dupe = long[long.duplicated(keys, keep=False)]
    if len(dupe):
        conflict = dupe.groupby(keys)['value'].nunique().gt(1)
        if conflict.any():
            raise ValueError('Conflicting duplicate observations: '+str(conflict[conflict].head()))
        qconflict = dupe.groupby(keys)['qualifier'].nunique().gt(1)
        if qconflict.any():
            raise ValueError('Conflicting duplicate qualifiers')
    removed=len(long)-len(long.drop_duplicates(keys))
    long=long.drop_duplicates(keys).sort_values(keys)
    start=pd.Timestamp(f'{min(requested_years)}-01-01',tz='UTC')
    end=pd.Timestamp(f'{max(requested_years)+1}-01-01',tz='UTC')
    long=long[long.time_utc.ge(start) & long.time_utc.lt(end)]
    return long, variable_metadata, all_meta, removed, start, end

def prepare_site(site, long, start, end):
    s = long[long.site.eq(site)]
    parts=[]
    for pc,prefix in [('00060','q'),('99133','nox')]:
        part=s[s.parameter.eq(pc)].drop(columns=['site','parameter']).set_index('time_utc')
        if part.empty:
            raise ValueError(site+' missing '+pc)
        if pc=='00060':
            part['value'] *= 0.028316846592
        parts.append(part.add_prefix(prefix+'_'))
    n=parts[0].join(parts[1],how='outer').sort_index()
    n=n.rename(columns={'q_value':'q_cms','nox_value':'nox_mg_l'})
    bool_cols=[c for c in n if any(c.endswith('_'+x) for x in ['approved','estimated','uncensored','numeric_valid','reference_ok'])]
    for c in bool_cols:
        n[c]=n[c].fillna(False).astype(bool)
    n['on_quarter_grid']=(n.index.minute%15==0)&(n.index.second==0)&(n.index.microsecond==0)
    n['joint_reference_ok']=n.q_reference_ok & n.nox_reference_ok & n.on_quarter_grid
    n['site']=site
    grid=n[n.on_quarter_grid].copy()
    good=grid.joint_reference_ok
    grid['native_joint_count']=good.astype(int)
    grid['native_observed_count']=(grid.q_numeric_valid & grid.nox_numeric_valid).astype(int)
    grid['observed_volume_m3']=np.where(good,grid.q_cms*900,0.)
    grid['load_kg']=np.where(good,grid.q_cms*grid.nox_mg_l*900*.001,0.)
    grid['q_count']=grid.q_numeric_valid.astype(int)
    grid['nox_count']=grid.nox_numeric_valid.astype(int)
    # Means retained as retrospective summaries, not instantaneous grab samples.
    grid.loc[~grid.q_numeric_valid,'q_cms']=np.nan
    grid.loc[~grid.nox_numeric_valid,'nox_mg_l']=np.nan
    agg={c:'sum' for c in ['native_joint_count','native_observed_count','observed_volume_m3','load_kg','q_count','nox_count']}
    agg.update({'q_cms':'mean','nox_mg_l':'mean','q_approved':'all','nox_approved':'all','q_estimated':'any','nox_estimated':'any'})
    h=grid.resample('h').agg(agg)
    idx=pd.date_range(start,end,freq='h',inclusive='left',name='time_utc')
    h=h.reindex(idx)
    for c in ['native_joint_count','native_observed_count','q_count','nox_count']:
        h[c]=h[c].fillna(0).astype(int)
    h['expected_count']=4
    h['coverage']=h.native_joint_count/4
    h['valid_hour']=h.coverage.ge(.9)
    # Missing hours carry no fabricated load. Partial hour sums retain observed
    # support only; users MUST apply valid_hour for complete-hour comparisons.
    h.loc[h.native_joint_count.eq(0),['observed_volume_m3','load_kg']]=np.nan
    instant=n.reindex(idx)
    h['q_at_time_cms']=instant.q_cms.where(instant.q_numeric_valid.fillna(False))
    h['nox_at_time_mg_l']=instant.nox_mg_l.where(instant.nox_numeric_valid.fillna(False))
    h['q_at_time_available']=h.q_at_time_cms.notna()
    h['nox_sample_approved']=instant.nox_approved.fillna(False).astype(bool)
    h['nox_sample_estimated']=instant.nox_estimated.fillna(False).astype(bool)
    h['nox_sample_reference_ok']=instant.nox_reference_ok.fillna(False).astype(bool)
    h['q_sample_reference_ok']=instant.q_reference_ok.fillna(False).astype(bool)
    h['site']=site
    for c in ['q_approved','nox_approved','q_estimated','nox_estimated']:
        h[c]=h[c].fillna(False).astype(bool)
    # Approval on an incomplete hour must not imply complete support.
    h['q_approved'] &= h.q_count.eq(4)
    h['nox_approved'] &= h.nox_count.eq(4)
    return h.reset_index(),n.reset_index()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifests',nargs='+')
    args=p.parse_args()
    manifests=args.manifests or sorted(str(x) for x in DATA.glob('acquisition_manifest_*.json'))
    long, vmeta, smeta, duplicates, start, end=read_records(manifests)
    hourly,native=[],[]
    for site in sorted(long.site.unique()):
        h,n=prepare_site(site,long,start,end)
        hourly.append(h);native.append(n)
        print(site,len(n),'native;',int(h.valid_hour.sum()),'valid hours;',round(h.valid_hour.mean(),4),flush=True)
    h=pd.concat(hourly,ignore_index=True)
    n=pd.concat(native,ignore_index=True)
    DATA.mkdir(exist_ok=True);RESULTS.mkdir(exist_ok=True)
    h.to_parquet(DATA/'hourly_observations.parquet',index=False)
    n.to_parquet(DATA/'native_observations.parquet',index=False)
    (DATA/'variable_metadata.json').write_text(json.dumps(vmeta,indent=2),encoding='utf-8')
    (DATA/'site_method_metadata.json').write_text(json.dumps(smeta,indent=2),encoding='utf-8')
    rows=[]
    for (site,year),g in h.assign(year=h.time_utc.dt.year).groupby(['site','year']):
        threshold=g.q_cms.quantile(.95)
        high=g.q_cms.ge(threshold)&g.q_cms.notna()
        rows.append({'site':site,'year':int(year),'expected_hours':len(g),
                     'valid_hours':int(g.valid_hour.sum()),'valid_fraction':g.valid_hour.mean(),
                     'q_at_time_fraction':g.q_at_time_available.mean(),
                     'nox_grab_reference_fraction':g.nox_sample_reference_ok.mean(),
                     'observed_pair_fraction':g.native_observed_count.sum()/(len(g)*4),
                     'native_valid_pair_fraction':g.native_joint_count.sum()/(len(g)*4),
                     'q_p95_cms':threshold,'high_flow_hours':int(high.sum()),
                     'valid_high_flow_hours':int((high&g.valid_hour).sum()),
                     'high_flow_reference_coverage':g.loc[high,'valid_hour'].mean(),
                     'valid_window_load_kg':g.loc[g.valid_hour,'load_kg'].sum(),
                     'all_hours_annual_total_identified':bool(g.valid_hour.all())})
    audit=pd.DataFrame(rows)
    audit.to_csv(RESULTS/'data_audit_site_year.csv',index=False)
    monthly=[]
    for (site,year,month),g in h.assign(year=h.time_utc.dt.year,month=h.time_utc.dt.month).groupby(['site','year','month']):
        monthly.append({'site':site,'year':int(year),'month':int(month),'hours':len(g),
                        'valid_hours':int(g.valid_hour.sum()),'valid_fraction':g.valid_hour.mean(),
                        'q_at_time_fraction':g.q_at_time_available.mean(),
                        'nox_reference_fraction':g.nox_sample_reference_ok.mean(),
                        'mean_native_count':g.native_joint_count.mean()})
    pd.DataFrame(monthly).to_csv(RESULTS/'data_audit_site_month.csv',index=False)
    flags=[]
    for (site,parameter),g in long.groupby(['site','parameter']):
        dif=g.time_utc.diff().dt.total_seconds().dropna()
        flags.append({'site':site,'parameter':parameter,'rows':len(g),
                      'qualifier_counts':g.qualifier.value_counts().to_dict(),
                      'interval_seconds_top10':{str(k):int(v) for k,v in dif.value_counts().head(10).items()},
                      'reference_ok_fraction':float(g.reference_ok.mean())})
    audit_json={'manifests':manifests,'duplicate_boundary_rows_removed':duplicates,
                'sites':h.site.nunique(),'hours':len(h),'valid_hours':int(h.valid_hour.sum()),
                'native_rows':len(n),'integration':'fixed UTC quarter-hour left-rectangle Q*C*900/1000, no gap fill',
                'flags_and_cadences':flags,'site_years':rows}
    (RESULTS/'data_audit_summary.json').write_text(json.dumps(audit_json,indent=2),encoding='utf-8')
    print(audit.to_string(index=False),flush=True)
    print('READY='+str(DATA/'hourly_observations.parquet'),flush=True)

if __name__=='__main__':
    main()
