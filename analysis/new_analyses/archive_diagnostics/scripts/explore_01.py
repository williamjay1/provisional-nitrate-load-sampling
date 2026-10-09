
import json, sys
import pandas as pd, numpy as np
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 80)

R = r"D:\MLWork\NitrateAdaptiveSampling_20261005\revision_20261009\results"
S = R + r"\summary_main_v1"

def show(name, df, cols=None, n=8):
    print("="*100)
    print(name, "shape=", df.shape)
    print("cols:", list(df.columns))
    for c in (cols or []):
        if c in df.columns:
            vc = df[c].value_counts(dropna=False)
            print(f"  {c}: n_unique={df[c].nunique(dropna=True)} -> {dict(vc.head(n))}")

ee = pd.read_csv(S + r"\eligible_events.csv")
show("eligible_events", ee, ["stage","experiment","analysis_status","policy","budget","delay_hours","scenario","reconstructor","mode","eligible","boundary_uncertain"])
print("  coverage describe:", ee["coverage"].describe().to_dict())
print("  coverage min rows:")
print(ee.nsmallest(5, "coverage")[["site","year","stage","event_id","hours","coverage","eligible","policy","budget"]].to_string())
print("  eligible value counts:", ee["eligible"].value_counts(dropna=False).to_dict())

ce = pd.read_csv(R + r"\context_events.csv")
show("context_events", ce, ["stage","source_run","eligible","scorable","excluded_reason","start_season"])
print("  coverage describe:", ce["reference_hour_coverage"].describe().to_dict())
print("  coverage by stage:")
print(ce.groupby("stage")["reference_hour_coverage"].describe().to_string())
print("  stage x eligible:")
print(pd.crosstab(ce["stage"], ce["eligible"]).to_string())
print("  stage x scorable:")
print(pd.crosstab(ce["stage"], ce["scorable"]).to_string())
print("  n below 0.90 by stage:", ce.assign(b90=ce["reference_hour_coverage"]<0.90, b95=ce["reference_hour_coverage"]<0.95, b100=ce["reference_hour_coverage"]<1.0).groupby("stage")[["b90","b95","b100"]].sum().to_dict())
print("  sites per stage:", ce.groupby("stage")["site"].nunique().to_dict())
print("  unique (site,year) per stage:", ce.groupby("stage").apply(lambda d: d[["site","year"]].drop_duplicates().shape[0], include_groups=False).to_dict())

sm = pd.read_csv(S + r"\station_metrics.csv")
show("station_metrics", sm, ["stage","experiment","scenario","reconstructor","delay_hours","budget","reconstructor_family","half_life_hours","age_origin","minimum_events","policy"])
print("  stations per stage:", sm.groupby("stage")["site"].nunique().to_dict())
print("  rows at budget96:", (sm["budget"]==96).sum())

pe = pd.read_csv(S + r"\paired_effects.csv")
show("paired_effects", pe, ["stage","experiment","scenario","reconstructor","budget","measure","baseline","minimum_events"])
print("  stage x measure:")
print(pd.crosstab([pe["stage"],pe["budget"]], pe["measure"]).to_string())
print("  stage x baseline at B96:")
print(pd.crosstab(pe[pe["budget"]==96]["stage"], pe[pe["budget"]==96]["baseline"]).to_string())

ag = pd.read_csv(S + r"\aggregate_metrics.csv")
show("aggregate_metrics", ag, ["stage","scenario","budget","policy","minimum_events","reconstructor_family"])

sy = pd.read_csv(S + r"\site_year_metrics.csv")
show("site_year_metrics", sy, ["stage","budget","policy","year"])
print("  stage x station:", sy.groupby("stage")["site"].nunique().to_dict())
