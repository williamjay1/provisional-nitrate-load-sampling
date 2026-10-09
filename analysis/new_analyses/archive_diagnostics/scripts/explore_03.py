
import pandas as pd, numpy as np
pd.set_option("display.width",240); pd.set_option("display.max_columns",60); pd.set_option("display.max_rows",300)
R = r"D:\MLWork\NitrateAdaptiveSampling_20261005\revision_20261009\results"
for name, path in [("temporal", R+r"\experiments_main_temporal_v1\attempts.csv"),
                   ("external", R+r"\experiments_main_external_v1\attempts.csv")]:
    d = pd.read_csv(path, dtype={"site":str})
    print("="*100); print(name, d.shape)
    print(" policies:", d.policy.value_counts().to_dict())
    print(" budgets:", d.budget.value_counts().to_dict())
    print(" stages:", d.stage.unique().tolist(), "seeds:", sorted(d.seed.unique().tolist()))
    b = d[d.budget==96]
    print(" B96 rows:", len(b), " sites:", b.site.nunique(), " groups(policy,site,year,seed):", b.groupby(["policy","site","year","seed"]).ngroups)
    g = b.groupby(["policy","site","year","seed"]).size()
    print(" attempts per group: min",g.min(),"max",g.max(), "n_groups", len(g))
    print(" reason by policy:", b.groupby(["policy","reason"]).size().to_dict())
    print(" label_success by policy:", b.groupby("policy").label_success.agg(["sum","mean"]).to_dict())
    print(" sample_time dtype:", b.sample_time.dtype, b.sample_time.iloc[0])
    # grid alignment
    t = pd.to_datetime(b.sample_time, utc=True)
    print(" all on 6h? ", bool(((t.dt.hour % 6)==0).all() and (t.dt.minute==0).all()))
    print(" example value/flow times (site 02035000, 2025, seed41):")
    sub = b[(b.site=="02035000")&(b.year==2025)&(b.seed==41)&(b.policy.isin(["value","flow_trigger"]))]
    print(sub.groupby("policy").sample_time.apply(lambda s: sorted(pd.to_datetime(s,utc=True).tolist())[:6]).to_string())
    print(" arrivals available:", b.label_available_by_horizon.sum(), "of", len(b))
    print(" forced_deadline by policy:", b.groupby("policy").forced_deadline.sum().to_dict())
