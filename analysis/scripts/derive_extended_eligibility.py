"""Clarify training support: model labels are joint-qualified exact-hour samples."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def main():
    data=pd.read_parquet(ROOT/'datasets/extended_hourly_2019_2025_v1.parquet')
    good=data.nox_sample_reference_ok&data.q_sample_reference_ok&np.isfinite(data.nox_at_time_mg_l)&data.nox_at_time_mg_l.ge(0)&data.q_at_time_cms.notna()
    counts=data.assign(year=data.time_utc.dt.year,training_joint_instant_samples=good).groupby(['site','year']).training_joint_instant_samples.sum()
    sy=pd.read_csv(ROOT/'results/extended_data_site_year_v1.csv',dtype={'site':str})
    sy=sy.merge(counts.rename('training_joint_instant_samples').reset_index(),on=['site','year'],validate='one_to_one')
    sy.to_csv(ROOT/'results/extended_data_site_year_v2.csv',index=False)
    old=pd.read_csv(ROOT/'results/extended_data_eligibility_v1.csv',dtype={'site':str})
    updated=[]
    for row in old.to_dict('records'):
        history=sy[sy.site.eq(row['site'])&sy.year.between(row['target_year']-3,row['target_year']-1)]
        n=int(history.training_joint_instant_samples.ge(1000).sum())
        updated.append({**row,'history_years_with_1000_valid_hours':row['history_years_with_1000_valid_hours'],
            'history_years_with_1000_joint_instant_samples':n,'training_support_definition':'joint-qualified original observation exactly at UTC hour',
            'data_eligible_before_event_count':n>=2 and row['target_valid_fraction']>=.5})
    v2=pd.DataFrame(updated);v2.to_csv(ROOT/'results/extended_data_eligibility_v2.csv',index=False)
    changes=v2.loc[v2.data_eligible_before_event_count.ne(old.data_eligible_before_event_count)].to_dict('records')
    info={'reason':'Training uses exact-hour concentrations, so history eligibility uses joint-qualified exact-hour labels; target coverage remains complete-hour quadrature.',
          'changed_site_year_eligibility':changes,'counts':v2.groupby('target_year').data_eligible_before_event_count.sum().to_dict()}
    (ROOT/'results/extended_eligibility_change_v2.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    print(json.dumps(info,indent=2))

if __name__=='__main__':main()
