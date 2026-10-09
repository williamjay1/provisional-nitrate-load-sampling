
import pandas as pd, numpy as np
pd.set_option("display.width",240); pd.set_option("display.max_columns",60); pd.set_option("display.max_rows",400)
R = r"D:\MLWork\NitrateAdaptiveSampling_20261005\revision_20261009\results"
fm = pd.read_csv(R+r"\context_forward_model.csv", dtype={"site":str})
rp = pd.read_csv(R+r"\context_residual_persistence.csv", dtype={"site":str})
sy = pd.read_csv(R+r"\context_site_year.csv", dtype={"site":str})
for st in ['development','external','temporal']:
    s = sorted(fm[fm.stage==st].site.unique().tolist())
    print(st, len(s), s)
print("\nunion:", len(set(fm.site)))
print("\nsite_year all sites:", sorted(sy.site.unique().tolist()))
print("n:", sy.site.nunique())
missing = sorted(set(sy.site) - set(fm.site))
print("sites in site_year but not forward_model:", missing)
print("\nrp site list:", sorted(rp.site.unique().tolist()))
print("\nforward_model available_before_target:", fm.available_before_target.value_counts().to_dict() if 'available_before_target' in fm else 'n/a')
print("\nrp per (site,year,lag) rows with pair_support continuous:")
c = rp[rp.pair_support=='continuous_all_hours_qualified']
print(c.groupby(['site','year']).size().describe().to_dict())
print("NaN corr count:", c.pearson_residual_autocorrelation.isna().sum(), "of", len(c))
print("\nsite_year rows per stage (context):")
ce = pd.read_csv(R+r"\context_events.csv", dtype={"site":str})
print(ce.groupby('stage').site.nunique().to_dict())
print("\nsite_year 2025 coverage per site (temporal):")
print(sy[(sy.year==2025)][['site','hour_coverage','reference_nox_mean_mg_l']].to_string(index=False))
