import pandas as pd, numpy as np
from pathlib import Path
D = Path(r"F:/SCI/nitrate_rev/analysis_delay_ext")
res = pd.read_csv(D / "results.csv")
# station-level mean across seeds
st = res.groupby(["policy","origin","delay","site"])["event_mean_absolute_relative_error"].mean().reset_index()
def cell(p, o, d):
    x = st[(st.policy==p)&(st.origin==o)&(st.delay==d)].set_index("site")["event_mean_absolute_relative_error"]
    return x
def paired(a, b, label):
    diff = (a - b).dropna()
    rng = np.random.default_rng(271828)
    boots = np.array([diff.values[rng.integers(0,len(diff),len(diff))].mean() for _ in range(10000)])
    print("%-52s %+6.2f pp  [%+.2f, %+.2f]  stations favouring candidate %d/%d" % (
        label, 100*diff.mean(), 100*np.percentile(boots,2.5), 100*np.percentile(boots,97.5),
        int((diff>0).sum()), len(diff)))
print("=== levels (%) ===")
piv = st.pivot_table(index=["policy","origin"], columns="delay", values="event_mean_absolute_relative_error")
print((100*piv).round(2).to_string())
print()
print("=== 168 h contrasts (arrival origin, candidate = later/other) ===")
for p in ["flow_trigger","uniform","deadline_only"]:
    paired(cell(p,"arrival",24), cell(p,"arrival",168), p+": 168h vs 24h")
    paired(cell(p,"arrival",6),  cell(p,"arrival",168), p+": 168h vs 6h")
print()
print("=== ranking at 168 h (arrival): uniform vs flow_trigger ===")
paired(cell("uniform","arrival",168), cell("flow_trigger","arrival",168), "168h uniform vs flow (positive = uniform better)")
print("=== ranking at 24 h (arrival): uniform vs flow_trigger ===")
paired(cell("uniform","arrival",24), cell("flow_trigger","arrival",24), "24h uniform vs flow (positive = uniform better)")
print("=== ranking at 72 h (arrival) ===")
paired(cell("uniform","arrival",72), cell("flow_trigger","arrival",72), "72h uniform vs flow (positive = uniform better)")
