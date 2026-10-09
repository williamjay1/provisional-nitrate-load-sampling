
import json
import pandas as pd, numpy as np
pd.set_option("display.width",220); pd.set_option("display.max_columns",60); pd.set_option("display.max_rows",200)

R = r"D:\MLWork\NitrateAdaptiveSampling_20261005\revision_20261009\results"
S = R + r"\summary_main_v1"

pe = pd.read_csv(S + r"\paired_effects.csv")
b = pe[(pe.budget==96)&(pe.measure=="event_mean_absolute_relative_error")]
print("=== paired_effects B96 event_mean_absolute_relative_error ===")
print(b[["stage","minimum_events","baseline","stations","mean_difference","median_difference","candidate_lower","station_ci_low","station_ci_high","huc4_ci_low","huc4_ci_high"]].to_string(index=False))

sm = pd.read_csv(S + r"\station_metrics.csv")
print("\n=== station_metrics station counts by stage x minimum_events ===")
print(sm.groupby(["stage","minimum_events"]).agg(rows=("site","size"), stations=("site","nunique"), policies=("policy","nunique"), budgets=("budget","nunique")).to_string())

sy = pd.read_csv(S + r"\site_year_metrics.csv")
print("\n=== site_year_metrics events_eligible distribution ===")
print(sy.groupby(["stage","minimum_events" if "minimum_events" in sy.columns else "policy"]).size().to_string() if False else "")
print(sy[sy.policy=="value"][["stage","site","year","events_eligible","hour_coverage","attempts","successful_samples"]].sort_values(["stage","site","year"]).to_string(index=False))
