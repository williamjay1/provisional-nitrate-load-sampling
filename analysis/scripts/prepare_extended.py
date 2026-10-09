"""Versioned extended preprocessing without modifying frozen pilot artifacts.

Exact same quarter-hour quadrature as the pilot. Added temporal UV-method
verification and explicit reported censor bounds; no interpolation or scoring.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, os
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from acquire_extended import existing_records, WORK, PILOT
from prepare_data import prepare_site

def discovery_registry():
    out={}
    for path in sorted((WORK/'datasets').glob('extended_discovery_*.json')):
        for s in json.loads(path.read_text(encoding='utf-8'))['records']:
            out[s['site']]={**s,'discovery_manifest':str(path)}
    return out

def series_for_block(site,parameter,description,registry):
    choices=[s for s in registry[site]['series'] if s['series']['parameter_code']==parameter and s['series'].get('begin') is not None]
    if parameter!='99133':return choices
    if site=='03339000':
        # Explicit instrument rule established from metadata, not performance:
        # retain the long-standing UV016 series; NT3100 has no method evidence.
        return [s for s in choices if ('NT3100' in description)==('NT3100' in str(s['series'].get('sublocation_identifier')))]
    if site=='01646500':
        return [s for s in choices if ('Discontinued' in description)==('Discontinued' in str(s['series'].get('web_description')))]
    if len(choices)>1:
        raise ValueError(f'Ambiguous multi-series mapping for {site}: {description}')
    return choices

def method_flags(times,series):
    verified=pd.Series(False,index=times.index,dtype=bool)
    codes=pd.Series('',index=times.index,dtype='string')
    for s in series:
        for m in s['methods']:
            interval=m['interval'];code=interval['method_id']
            if not code.startswith('UV'):continue
            lo=interval['begin'];hi=interval['end']
            mask=pd.Series(True,index=times.index)
            if int(lo[:4])>=1678:mask &= times.ge(pd.Timestamp(lo))
            if int(hi[:4])<=2261:mask &= times.lt(pd.Timestamp(hi))
            verified |= mask;codes.loc[mask]=code
    return verified,codes

def read_site(site,records,registry,start,end):
    chunks=[];block_audit=[]
    for rec in sorted(records,key=lambda x:x['year']):
        with gzip.open(rec['path'],'rt',encoding='utf-8') as f:j=json.load(f)
        for ts in j.get('value',{}).get('timeSeries',[]):
            pc=ts['variable']['variableCode'][0]['value']
            if pc not in ['00060','99133']:continue
            for block in ts['values']:
                v=pd.DataFrame(block['value'])
                desc='; '.join(m.get('methodDescription','') for m in block.get('method',[]))
                mid=';'.join(str(m.get('methodID','')) for m in block.get('method',[]))
                block_audit.append({'site':site,'year':rec['year'],'parameter':pc,'legacy_method_id':mid,'description':desc,'rows':len(v),'path':rec['path']})
                if v.empty:continue
                v['time_utc']=pd.to_datetime(v.dateTime,utc=True)
                v['value']=pd.to_numeric(v.value,errors='coerce')
                v['site']=site;v['parameter']=pc
                v['qualifier']=v.qualifiers.apply(lambda x:'|'.join(x))
                v['approved']=v.qualifiers.apply(lambda x:'A' in x)
                v['estimated']=v.qualifiers.apply(lambda x:any(q.lower()=='e' for q in x))
                v['uncensored']=v.qualifiers.apply(lambda x:not any(q in ['<','>','&lt;','&gt;'] for q in x))
                v['numeric_valid']=v.value.ge(0)&np.isfinite(v.value)
                v['quality_reference_ok']=v.approved&~v.estimated&v.uncensored&v.numeric_valid
                if pc=='99133':
                    choices=series_for_block(site,pc,desc,registry)
                    v['method_verified'],v['method_code']=method_flags(v.time_utc,choices)
                    v['ogc_series_id']=';'.join(s['series']['id'] for s in choices)
                    v['reference_ok']=v.quality_reference_ok&v.method_verified
                else:
                    v['method_verified']=True;v['method_code']='Q_USGS_rated_or_measured'
                    v['ogc_series_id']=''
                    v['reference_ok']=v.quality_reference_ok
                v['legacy_method_id']=mid;v['method_description']=desc
                chunks.append(v[['site','parameter','time_utc','value','qualifier','approved','estimated','uncensored','numeric_valid','reference_ok','quality_reference_ok','method_verified','method_code','ogc_series_id','legacy_method_id','method_description']])
    if not chunks:return None,block_audit,[]
    long=pd.concat(chunks,ignore_index=True)
    long=long[long.time_utc.ge(start)&long.time_utc.lt(end)]
    # NT3100 remains in raw and block audit; its method is unverified. We do not
    # merge it into the canonical UV016 time series or resolve by better values.
    excluded=[]
    if site=='03339000':
        mask=long.parameter.eq('99133')&long.method_description.str.contains('NT3100',regex=False)
        excluded.append({'reason':'separate_NT3100_instrument_no_temporal_method_evidence','rows':int(mask.sum())})
        long=long.loc[~mask]
    keys=['site','parameter','time_utc'];dup=long[long.duplicated(keys,keep=False)]
    if len(dup):
        for col in ['value','qualifier','reference_ok']:
            conflicts=dup.groupby(keys)[col].nunique(dropna=False).gt(1)
            if conflicts.any():raise ValueError(f'Conflicting {col} duplicate at {site}: {conflicts[conflicts].index[0]}')
    long=long.drop_duplicates(keys).sort_values(keys)
    return long,block_audit,excluded

def site_hourly(site,long,start,end):
    basecols=['site','parameter','time_utc','value','qualifier','approved','estimated','uncensored','numeric_valid','reference_ok']
    if not all(long.parameter.eq(pc).any() for pc in ['00060','99133']):
        return None,None,'missing_all_observations_for_one_parameter'
    h,n=prepare_site(site,long[basecols],start,end)
    nox=long[long.parameter.eq('99133')].set_index('time_utc')
    n=n.merge(nox[['quality_reference_ok','method_verified','method_code','ogc_series_id','legacy_method_id','method_description']].add_prefix('nox_'),left_on='time_utc',right_index=True,how='left',validate='one_to_one')
    for c in ['nox_quality_reference_ok','nox_method_verified']:n[c]=n[c].fillna(False).astype(bool)
    for c in ['nox_method_code','nox_ogc_series_id','nox_legacy_method_id','nox_method_description']:n[c]=n[c].fillna('').astype('string')
    # Reported censor limits retained explicitly for possible later interval
    # sensitivity, not used as exact labels or filled into the main reference.
    qstr=n.nox_qualifier.fillna('')
    less=qstr.str.split('|').apply(lambda z:'<' in z or '&lt;' in z)
    greater=qstr.str.split('|').apply(lambda z:'>' in z or '&gt;' in z)
    n['nox_reported_lower_bound_mg_l']=np.where(less,0,n.nox_mg_l)
    n['nox_reported_upper_bound_mg_l']=np.where(greater,np.inf,n.nox_mg_l)
    n['nox_censored']=less|greater
    n['nox_provisional']=qstr.str.split('|').apply(lambda z:'P' in z)
    n['nox_interval_reference_ok']=n.nox_approved&~n.nox_estimated&n.nox_numeric_valid&n.nox_method_verified
    ih=n.set_index('time_utc').reindex(pd.DatetimeIndex(h.time_utc))
    for out,col in [('nox_sample_censored','nox_censored'),('nox_sample_provisional','nox_provisional'),('nox_sample_method_verified','nox_method_verified'),('nox_sample_interval_reference_ok','nox_interval_reference_ok')]:
        h[out]=ih[col].fillna(False).to_numpy(dtype=bool)
    h['nox_sample_lower_bound_mg_l']=ih.nox_reported_lower_bound_mg_l.to_numpy()
    h['nox_sample_upper_bound_mg_l']=ih.nox_reported_upper_bound_mg_l.to_numpy()
    return h,n,None

def station_info(site,rec):
    prop=rec['location']['data']['properties'];huc=str(prop.get('hydrologic_unit_code') or '')
    return {'site':site,'name':prop['monitoring_location_name'],'state':prop.get('state_name'),
            'huc':huc,'huc4_group':huc[:4] if len(huc)>=4 else None,
            'drainage_area_as_reported':prop.get('drainage_area'),
            'coordinates':rec['location']['data'].get('geometry',{}).get('coordinates'),
            'pilot_development_site':site in PILOT,'location_metadata':prop,
            'series_metadata':rec['series'],'candidate_provenance':rec['candidate_provenance'],
            'discovery_manifest':rec['discovery_manifest']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--tag',default='v1');p.add_argument('--sites',nargs='+');p.add_argument('--start-year',type=int,default=2019);p.add_argument('--end-year',type=int,default=2025)
    a=p.parse_args();os.environ['TEMP']=os.environ['TMP']=str(WORK/'temp')
    start=pd.Timestamp(f'{a.start_year}-01-01',tz='UTC');end=pd.Timestamp(f'{a.end_year+1}-01-01',tz='UTC')
    registry=discovery_registry();allrecords=existing_records()
    sites=a.sites or sorted(s for s,x in registry.items() if x['has_same_site_q'] and x['nox_uv_method_found'])
    pref=f'extended_{{kind}}_{a.start_year}_{a.end_year}_{a.tag}.parquet'
    outputs={k:WORK/'datasets'/pref.format(kind=k) for k in ['hourly','native']}
    if any(p.exists() for p in outputs.values()):raise FileExistsError('Use a new --tag; existing extended outputs will not be overwritten')
    writers={};audit=[];monthly=[];meta=[];issues=[];blocks=[];checks=[];used=[]
    try:
        for site in sites:
            records=[x for (s,y),x in allrecords.items() if s==site and a.start_year<=y<=a.end_year]
            used.extend(records);meta.append(station_info(site,registry[site]))
            long,ba,excluded=read_site(site,records,registry,start,end);blocks.extend(ba)
            if long is None:
                issues.append({'site':site,'reason':'no_observations','excluded':excluded});continue
            h,n,error=site_hourly(site,long,start,end)
            if error:
                issues.append({'site':site,'reason':error,'excluded':excluded});continue
            if excluded:issues.append({'site':site,'reason':'instrument_selection','excluded':excluded})
            for kind,frame in [('hourly',h),('native',n)]:
                table=pa.Table.from_pandas(frame,preserve_index=False)
                if kind not in writers:writers[kind]=pq.ParquetWriter(outputs[kind],table.schema,compression='zstd')
                else:table=table.cast(writers[kind].schema)
                writers[kind].write_table(table)
            # Independent within-station native-product agreement and sample
            # qualification checks are performed before accepting the output.
            g=n[n.joint_reference_ok].copy();g['hour']=g.time_utc.dt.floor('h');g['mass']=g.q_cms*g.nox_mg_l*.9;g['vol']=g.q_cms*900
            g=g.groupby('hour').agg(mass=('mass','sum'),vol=('vol','sum'),cnt=('mass','size'))
            join=h.set_index('time_utc').join(g)
            check={'site':site,'unique_native':not n.duplicated(['site','time_utc']).any(),'unique_hourly':not h.duplicated(['site','time_utc']).any(),'count_range':bool(h.native_joint_count.between(0,4).all()),'valid_exact_four':bool(h.valid_hour.eq(h.native_joint_count.eq(4)).all()),'load_product_sum':bool(np.allclose(join.loc[join.cnt.notna(),'load_kg'],join.loc[join.cnt.notna(),'mass'])),'volume_same_support':bool(np.allclose(join.loc[join.cnt.notna(),'observed_volume_m3'],join.loc[join.cnt.notna(),'vol'])),'no_censored_exact_sample':bool((~h.nox_sample_censored|~h.nox_sample_reference_ok).all())}
            checks.append(check)
            if not all(v for k,v in check.items() if k!='site'):raise AssertionError(check)
            for year,y in h.groupby(h.time_utc.dt.year):
                raw=n[n.time_utc.dt.year.eq(year)];q95=y.q_cms.quantile(.95);high=y.q_cms.ge(q95)&y.q_cms.notna()
                audit.append({'site':site,'year':int(year),'hours':len(y),'valid_hours':int(y.valid_hour.sum()),'valid_fraction':float(y.valid_hour.mean()),'instant_reference_samples':int(y.nox_sample_reference_ok.sum()),'instant_approved_samples':int(y.nox_sample_approved.sum()),'instant_censored_samples':int(y.nox_sample_censored.sum()),'instant_provisional_samples':int(y.nox_sample_provisional.sum()),'raw_nox_rows':int(raw.nox_numeric_valid.sum()),'raw_nox_approved':int(raw.nox_approved.sum()),'raw_nox_provisional':int(raw.nox_provisional.sum()),'raw_quality_pass_method_unknown':int((raw.nox_quality_reference_ok&~raw.nox_method_verified).sum()),'q_at_time_fraction':float(y.q_at_time_available.mean()),'high_flow_hours':int(high.sum()),'high_flow_reference_fraction':float(y.loc[high,'valid_hour'].mean()) if high.any() else None,'valid_reference_volume_m3':float(y.loc[y.valid_hour,'observed_volume_m3'].sum()),'valid_window_load_kg':float(y.loc[y.valid_hour,'load_kg'].sum())})
                for month,m in y.groupby(y.time_utc.dt.month):monthly.append({'site':site,'year':int(year),'month':int(month),'hours':len(m),'valid_hours':int(m.valid_hour.sum()),'valid_fraction':float(m.valid_hour.mean())})
            print(json.dumps({'prepared_site':site,'native_rows':len(n),'valid_hours':int(h.valid_hour.sum()),'target2025_valid_fraction':float(h.loc[h.time_utc.dt.year.eq(2025),'valid_hour'].mean())}),flush=True)
    finally:
        for writer in writers.values():writer.close()
    df=pd.DataFrame(audit);eligibility=[]
    for site in sites:
        sy=df[df.site.eq(site)]
        for year in [2023,2024,2025]:
            y=sy[sy.year.eq(year)];hist=sy[sy.year.between(year-3,year-1)];enough=int(hist.valid_hours.ge(1000).sum())
            coverage=float(y.valid_fraction.iloc[0]) if len(y) else 0.
            eligibility.append({'site':site,'target_year':year,'history_years':list(range(year-3,year)),'history_years_with_1000_valid_hours':enough,'target_valid_fraction':coverage,'data_eligible_before_event_count':enough>=2 and coverage>=.5,'pilot_development_site':site in PILOT,'event_eligibility':'not_evaluated_by_data_acquisition_agent'})
    result=WORK/'results';data=WORK/'datasets'
    df.to_csv(result/f'extended_data_site_year_{a.tag}.csv',index=False)
    pd.DataFrame(monthly).to_csv(result/f'extended_data_site_month_{a.tag}.csv',index=False)
    pd.DataFrame(eligibility).to_csv(result/f'extended_data_eligibility_{a.tag}.csv',index=False)
    (data/f'extended_station_metadata_{a.tag}.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    manifest={'source_manifests':sorted({x['source_manifest'] for x in used}),'used_raw_records':used,'output_files':{k:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for k,p in outputs.items()},'preparation_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'pilot_prepare_dependency_sha256':hashlib.sha256((WORK/'scripts/prepare_data.py').read_bytes()).hexdigest(),'rule':'pilot-compatible exact 15min joint quadrature, adding time-specific UV method requirement and explicit censor bounds','sites_requested':sites,'sites_written':sorted(df.site.unique()),'issues':issues,'block_audit':blocks,'checks':checks,'policy_results_computed':False,'data_eligibility':eligibility}
    (data/f'extended_preparation_manifest_{a.tag}.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('READY='+str(outputs['hourly']),flush=True)
    print(pd.DataFrame(eligibility).query('target_year==2025').to_string(index=False),flush=True)

if __name__=='__main__':main()
