"""Supplementary contrasts from completed revision outputs; no model selection."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
R=Path(__file__).resolve().parents[1]/'results'
out=R/'diagnostics_v1';out.mkdir(exist_ok=False)
def equal_station(df, cols):
    return df.groupby(['site','year'])[cols].mean().groupby('site').mean()
def ci(values):
    v=np.asarray(values);rng=np.random.default_rng(271828)
    a=v[rng.integers(len(v),size=(10000,len(v)))].mean(axis=1)
    return np.quantile(a,[.025,.975]).tolist()
# Matched calendars and clocks: update-family contrasts retain all settings.
f=pd.read_csv(R/'summary_factorial_v1'/'site_year_metrics.csv',dtype={'site':str})
f=f[(f.budget==96)&(f.events_eligible>=1)].copy()
rows=[]
for k,g in f.groupby(['policy','half_life_hours','age_origin']):
    w=g.pivot(index=['site','year'],columns='reconstructor_family',values='event_mean_absolute_relative_error').dropna()
    d=(w.rff_pooled-w.latest_residual).groupby('site').mean()
    rows.append(dict(zip(['policy','half_life_hours','age_origin'],k))|{'stations':len(d),'mean_rff_minus_latest':d.mean(),'station_ci_low':ci(d)[0],'station_ci_high':ci(d)[1],'latest_lower_stations':int((d>0).sum())})
pd.DataFrame(rows).to_csv(out/'factor_family_contrasts.csv',index=False)
# Compare score assumptions or pending omission at fixed actual delay.
m=pd.read_csv(R/'summary_mechanisms_v1'/'site_year_metrics.csv',dtype={'site':str})
m=m[(m.policy=='value')&(m.events_eligible>=1)].copy();rows=[]
for delay in [24,72]:
    w=m[m.delay_hours==delay].pivot(index='site',columns='scenario',values='event_mean_absolute_relative_error')
    for alt in w.columns:
        if alt=='delay_aware_pending':continue
        d=w[alt]-w.delay_aware_pending
        rows.append({'delay_hours':delay,'alternative':alt,'stations':len(d),'alternative_minus_aware':d.mean(),'station_ci_low':ci(d)[0],'station_ci_high':ci(d)[1],'aware_lower_stations':int((d>0).sum())})
pd.DataFrame(rows).to_csv(out/'mechanism_contrasts.csv',index=False)
# Cost counts: distinguish scored-event stations from all included records.
main=pd.read_csv(R/'summary_main_v1'/'site_year_metrics.csv',dtype={'site':str})
attemptrows=[]
for stage in ['temporal','external']:
    a=pd.read_csv(R/f'experiments_main_{stage}_v1'/'attempts.csv',dtype={'site':str})
    a['forced_deadline']=a.forced_deadline.astype(str).str.lower().eq('true').astype(int)
    a['label_success']=a.label_success.astype(str).str.lower().eq('true').astype(int)
    good=main[(main.stage==stage)&(main.events_eligible>=1)][['site','year']].drop_duplicates()
    for scope,b in [('all_data_eligible',a),('event_primary',a.merge(good,on=['site','year']))]:
        for (policy,budget),g in b.groupby(['policy','budget']):
            s=equal_station(g,['forced_deadline','label_success'])
            attemptrows.append({'stage':stage,'scope':scope,'policy':policy,'budget':budget,'stations':len(s),'fallback_fraction':s.forced_deadline.mean(),'success_fraction':s.label_success.mean()})
pd.DataFrame(attemptrows).to_csv(out/'attempt_summaries.csv',index=False)
# Score utility is an isolated diagnostic, with station-centred rank association.
c=pd.read_csv(R/'experiments_candidate_development_v1'/'candidate_effects.csv',dtype={'site':str})
g=c[c.eligible_diagnostic.astype(str).str.lower().eq('true')].copy()
g['score_rank_within_site']=g.groupby('site').acquisition_score.rank(pct=True)
g['utility_rank_within_site']=g.groupby('site').absolute_error_reduction_kg.rank(pct=True)
site=[]
for siteid,h in g.groupby('site'):
    rs=spearmanr(h.acquisition_score,h.absolute_error_reduction_kg)
    site.append({'site':siteid,'candidates':len(h),'spearman_score_abs_kg_utility':rs.statistic,'beneficial_fraction':(h.absolute_error_reduction_kg>0).mean(),'median_relative_utility':h.absolute_relative_error_reduction.median()})
pd.DataFrame(site).to_csv(out/'candidate_site_diagnostics.csv',index=False)
stats={'planned_candidates':len(c),'eligible_candidates':len(g),'sites':g.site.nunique(),'station_years':g[['site','year']].drop_duplicates().shape[0],'beneficial':int((g.absolute_error_reduction_kg>1e-10).sum()),'harmful':int((g.absolute_error_reduction_kg<-1e-10).sum()),'unchanged':int((g.absolute_error_reduction_kg.abs()<=1e-10).sum()),'pooled_rank_association':float(spearmanr(g.acquisition_score,g.absolute_error_reduction_kg).statistic),'within_site_rank_association':float(spearmanr(g.score_rank_within_site,g.utility_rank_within_site).statistic),'median_relative_utility':float(g.absolute_relative_error_reduction.median()),'identity':'post-result isolated added-sample diagnostic; no inferential p value or deployment effect'}
g.to_csv(out/'candidate_plot_data.csv',index=False)
(out/'candidate_summary.json').write_text(json.dumps(stats,indent=2))
print(json.dumps(stats,indent=2))
