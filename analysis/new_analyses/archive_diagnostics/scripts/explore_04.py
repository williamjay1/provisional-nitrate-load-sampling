
import pandas as pd, numpy as np, json
pd.set_option("display.width",240); pd.set_option("display.max_columns",60); pd.set_option("display.max_rows",400)
R = r"D:\MLWork\NitrateAdaptiveSampling_20261005\revision_20261009\results"
S = R + r"\summary_main_v1"

ce = pd.read_csv(R+r"\context_events.csv", dtype={"site":str})
ee = pd.read_csv(S+r"\eligible_events.csv", dtype={"site":str})
sy = pd.read_csv(R+r"\context_site_year.csv", dtype={"site":str})
rp = pd.read_csv(R+r"\context_residual_persistence.csv", dtype={"site":str})
fm = pd.read_csv(R+r"\context_forward_model.csv", dtype={"site":str})

print("residual persistence pair_support:", rp.pair_support.value_counts().to_dict())
print("residual stages:", rp.stage.value_counts().to_dict())
print("residual lags:", sorted(rp.lag_hours.unique().tolist()))
print("residual sites:", rp.site.nunique(), "station-years:", rp.groupby(['site','year']).ngroups)
print("forward model stages:", fm.stage.value_counts().to_dict(), "sites:", fm.site.nunique())
print("site_year sites:", sy.site.nunique(), "names nonnull:", sy.site_name.notna().sum(), "of", len(sy))
print("huc4_sample:", sy.drop_duplicates('site')[['site','site_name','huc4_group']].to_string(index=False))

# development cohort membership
dev = fm[fm.stage=='development'][['site','year']].drop_duplicates()
ext = fm[fm.stage=='external'][['site','year']].drop_duplicates()
tem = fm[fm.stage=='temporal'][['site','year']].drop_duplicates()
print("\ndev station-years:", len(dev), dev.site.nunique())
print("ext station-years:", len(ext), ext.site.nunique())
print("tem station-years:", len(tem), tem.site.nunique())

# join eligible_events unique events to context_events
e1 = ee[['site','year','stage','event_id','coverage','start_time','hours']].drop_duplicates(['site','year','event_id'])
print("\neligible_events unique events:", len(e1))
print("by stage:", e1.stage.value_counts().to_dict())
c2 = ce[['site','year','stage','event_id','reference_hour_coverage','eligible','boundary_uncertain','excluded_reason','hours']]
m = e1.merge(c2, on=['site','year','stage','event_id'], how='outer', indicator=True, suffixes=('_ee','_ce'))
print("merge status:", m._merge.value_counts().to_dict())
mm = m[m._merge=='both']
print("coverage max abs diff:", (mm.coverage-mm.reference_hour_coverage).abs().max())
print("hours equal all:", bool((mm.hours_ee==mm.hours_ce).all()))
print("eligible flags in merged:", mm.eligible.value_counts().to_dict())
print("n eligible_events rows with coverage>=1.0 events:", (e1.coverage>=1.0).sum())
print("context eligible & cov>=1.0:", ((ce.eligible)&(ce.reference_hour_coverage>=1.0)).sum())

# retained-event coverage distributions
for st in ['temporal','external','development']:
    sub = ce[(ce.stage==st)&(ce.eligible)]
    print(f"\n{st}: retained n={len(sub)} sites={sub.site.nunique()} cov[min,med,max]={sub.reference_hour_coverage.min():.6f},{sub.reference_hour_coverage.median():.6f},{sub.reference_hour_coverage.max():.6f} mean={sub.reference_hour_coverage.mean():.6f}")
    print("   quantiles:", sub.reference_hour_coverage.quantile([0,.1,.25,.5,.75,.9,1]).round(6).to_dict())
    print("   events with cov>=1.0 among retained:", int((sub.reference_hour_coverage>=1.0).sum()))
