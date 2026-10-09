
import pandas as pd, json
pd.set_option("display.width",300); pd.set_option("display.max_columns",40)
O = r"F:\SCI\nitrate_rev\analysis_arch"
cs = pd.read_csv(O+r"\coverage_sensitivity.csv")
print("rows:", len(cs), "record_types:", cs.record_type.value_counts().to_dict())
print(cs[cs.record_type=="screening"][["threshold","cohort","included_events","included_stations","events_added_vs_95pct","added_events_nonpositive_reference_load","added_events_share_reference_at_q_peak"]].to_string(index=False))
print("\nquantile rows:", len(cs[cs.record_type=="retained_coverage_quantile"]))
print(cs[cs.record_type=="paired"][["threshold","cohort","measure","baseline_label","mean_difference","station_ci_low","station_ci_high","status"]].to_string(index=False))
man = json.load(open(O+r"\run_manifest.json"))
print("\noutputs:", json.dumps(man["outputs"], indent=0))
