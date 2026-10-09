
import pandas as pd, json
pd.set_option("display.width",300); pd.set_option("display.max_columns",60)
O = r"F:\SCI\nitrate_rev\analysis_arch"
cs = pd.read_csv(O+r"\coverage_sensitivity.csv")
sc = cs[cs.record_type=="screening"]
print(json.dumps(sc[["threshold","cohort","included_stations","included_events","mean_reference_support","median_reference_support","min_reference_support","mean_event_hours","mean_reference_hours","events_added_vs_95pct","stations_added_vs_95pct","stations_lost_vs_95pct","added_events_median_event_hours","added_events_median_q_peak_cms","added_events_median_reference_load_kg","added_events_share_reference_at_q_peak"]].to_dict("records"), indent=1, default=str))
print("\nretained coverage quantiles:")
print(cs[cs.record_type=="retained_coverage_quantile"][["quantile","quantile_value"]].to_string(index=False))
p = pd.read_csv(O+r"\per_station_differences.csv", dtype={"site":str})
print("\nstation_years_in_primary:", p[["cohort","site","station_years_in_primary"]].to_dict("records"))
man = json.load(open(O+r"\run_manifest.json"))
print("\nmanifest outputs:", json.dumps(man["outputs"], indent=1))
print("generated:", man["generated_utc"])
