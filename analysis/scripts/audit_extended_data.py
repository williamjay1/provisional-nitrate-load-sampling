"""Read-only validation of extended inputs; never reads policy results."""
from pathlib import Path
import hashlib,json,stat
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from acquire_extended import WORK, PILOT

def main():
    data=WORK/'datasets';results=WORK/'results'
    m=json.loads((data/'extended_preparation_manifest_v1.json').read_text())
    h=pd.read_parquet(data/'extended_hourly_2019_2025_v1.parquet')
    old=pd.read_parquet(data/'hourly_observations.parquet')
    overlap=h[h.site.isin(PILOT)&h.time_utc.dt.year.between(2021,2024)][old.columns].sort_values(['site','time_utc']).reset_index(drop=True)
    old=old.sort_values(['site','time_utc']).reset_index(drop=True)
    diffs={}
    for col in old:
        a,b=old[col],overlap[col]
        equal=a.eq(b)|(a.isna()&b.isna())
        if not equal.all():diffs[col]=int((~equal).sum())
    row_equal=(old.eq(overlap)|(old.isna()&overlap.isna())).all(axis=1)
    changed=old.loc[~row_equal,['site','time_utc']]
    boundary_only=bool(changed.time_utc.eq(pd.Timestamp('2021-01-01',tz='UTC')).all())
    # Additional 2020 raw responses supply the five 00:00 boundary hours absent
    # in the original 2021 request. Preserve this explained change, not a claim
    # that all overlap rows are identical. No pilot input is edited.
    records=m['used_raw_records'];raw=[]
    for rec in records:
        p=Path(rec['path']);sha=hashlib.sha256(p.read_bytes()).hexdigest()
        raw.append({'site':rec['site'],'year':rec['year'],'path':str(p),'sha256_match':sha==rec['sha256'],'readonly':bool(p.stat().st_file_attributes&stat.FILE_ATTRIBUTE_READONLY),'bytes':p.stat().st_size})
    inventory={}
    for discovery in data.glob('extended_discovery_*.json'):
        j=json.loads(discovery.read_text())
        for rec in j['records']:
            for f in rec['raw_files']+[rec['location']]:
                p=Path(f['path']);inventory[str(p)]={'path':str(p),'url':f['url'],'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'readonly':bool(p.stat().st_file_attributes&stat.FILE_ATTRIBUTE_READONLY)}
    sy=pd.read_csv(results/'extended_data_site_year_v1.csv',dtype={'site':str})
    e=pd.read_csv(results/'extended_data_eligibility_v1.csv',dtype={'site':str})
    y2025=sy[sy.year.eq(2025)]
    method_missing=sy[sy.raw_quality_pass_method_unknown.gt(0)][['site','year','raw_quality_pass_method_unknown']].to_dict('records')
    checks={'hourly_unique':not h.duplicated(['site','time_utc']).any(),
            'full_common_support_exactly_four':bool(h.valid_hour.eq(h.native_joint_count.eq(4)).all()),
            'qualified_samples_are_approved':bool((~h.nox_sample_reference_ok|h.nox_sample_approved).all()),
            'qualified_samples_method_verified':bool((~h.nox_sample_reference_ok|h.nox_sample_method_verified).all()),
            'qualified_samples_not_censored':bool((~h.nox_sample_reference_ok|~h.nox_sample_censored).all()),
            'qualified_samples_not_estimated':bool((~h.nox_sample_reference_ok|~h.nox_sample_estimated).all()),
            'qualified_samples_not_provisional':bool((~h.nox_sample_reference_ok|~h.nox_sample_provisional).all()),
            'all_raw_hashes_match':all(x['sha256_match'] for x in raw),
            'all_raw_readonly':all(x['readonly'] for x in raw),
            'all_metadata_raw_readonly':all(x['readonly'] for x in inventory.values()),
            'pilot_overlap_identical_outside_initial_boundary':boundary_only,
            'output_hashes_match':all(hashlib.sha256(Path(o['path']).read_bytes()).hexdigest()==o['sha256'] for o in m['output_files'].values())}
    summary={'checks':checks,'pilot_overlap_differing_columns':diffs,'pilot_overlap_changed_rows':changed.assign(time_utc=changed.time_utc.astype(str)).to_dict('records'),
        'pilot_overlap_explanation':'Five 2021-01-01 00:00 UTC boundary hours now include real observations returned by the additional 2020 request. One added complete hour; all later overlap rows are identical. The original pilot artifacts remain unchanged.',
        'hourly_rows':len(h),'sites_written':int(h.site.nunique()),'sites_requested':len(m['sites_requested']),
        'all_years_valid_hours':int(h.valid_hour.sum()),'native_rows':pq.ParquetFile(data/'extended_native_2019_2025_v1.parquet').metadata.num_rows,
        'raw_site_year_files':len(raw),'raw_compressed_bytes':sum(x['bytes'] for x in raw),'raw_response_bytes':sum(x['response_bytes'] for x in records),
        'new_response_bytes':sum(json.loads(p.read_text()).get('new_response_bytes',0) for p in data.glob('extended_acquisition_*.json')),
        'metadata_files':len(inventory),'year2025_site_coverage':y2025.to_dict('records'),
        'eligibility_summary':[{ 'year':int(year),'eligible_sites':int(g.data_eligible_before_event_count.sum()),'eligible_new_sites':int((g.data_eligible_before_event_count&~g.pilot_development_site).sum())} for year,g in e.groupby('target_year')],
        'method_unverified_quality_passing_rows':method_missing,'raw_integrity':raw,'metadata_inventory':list(inventory.values()),
        'note':'Data-only audit; no policy result read or computed. Method-interval filtering is an explicit extension to pilot preprocessing.'}
    (results/'extended_data_verification_v1.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['raw_integrity','metadata_inventory','year2025_site_coverage']},indent=2))
    if not all(checks.values()):raise AssertionError(checks)

if __name__=='__main__':main()
