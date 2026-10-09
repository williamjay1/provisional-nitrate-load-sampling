
import pandas as pd, numpy as np
pd.set_option("display.width",240)
R = r"D:\MLWork\NitrateAdaptiveSampling_20261005\revision_20261009\results"
S = R + r"\summary_main_v1"
O = r"F:\SCI\nitrate_rev\analysis_arch"
sy = pd.read_csv(S+r"\site_year_metrics.csv", dtype={"site":str})
print("sy.year dtype:", sy.year.dtype, sy.year.unique())
ce = pd.read_csv(R+r"\context_site_year.csv", dtype={"site":str})
print("ctx.year dtype:", ce.year.dtype)

sp = pd.read_csv(O+r"\station_profile.csv", dtype=str)
print("\nrepr evaluation_years_temporal:", [repr(x) for x in sp.evaluation_years_temporal.head(4)])
print("repr evaluation_years:", [repr(x) for x in sp.evaluation_years.head(4)])

pe = pd.read_csv(S+r"\paired_effects.csv", dtype={"site":str})
q = pe[(pe.stage=="external")&(pe.budget==96)&(pe.measure=="event_mean_absolute_error_kg")&(pe.baseline=="uniform")]
print("\narchived external mass error vs periodic:")
print(q[["minimum_events","stations","mean_difference","median_difference","candidate_lower","station_ci_low","station_ci_high","huc4_ci_low","huc4_ci_high"]].to_string(index=False))

ee = pd.read_csv(S+r"\eligible_events.csv", dtype={"site":str})
ev = ee.drop_duplicates(["site","year","event_id"]).groupby(["stage","site"]).size()
print("\nproper event counts per station:")
print(ev.to_string())
# site_year events_eligible sums
se = sy[sy.policy=="value"].groupby(["stage","site"]).events_eligible.sum()
print("\nsite_year events_eligible sums:"); print(se.to_string())
