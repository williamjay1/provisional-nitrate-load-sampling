
import pandas as pd, json
pd.set_option("display.width",260); pd.set_option("display.max_columns",60); pd.set_option("display.max_rows",300)
O = r"F:\SCI\nitrate_rev\analysis_arch"
cs = pd.read_csv(O+r"\coverage_sensitivity.csv")
print("=== coverage_sensitivity.csv  screening rows ===")
print(cs[cs.record_type=="screening"][["threshold","cohort","included_stations","included_events","mean_reference_support","median_reference_support","min_reference_support","mean_reference_hours","events_added_vs_95pct","stations_added_vs_95pct","stations_lost_vs_95pct"]].to_string(index=False))
print("\n=== paired rows ===")
print(cs[cs.record_type=="paired"][["threshold","cohort","measure","baseline","paired_stations","paired_events","value_equal_station_mean","baseline_equal_station_mean","mean_difference","stations_value_better","station_ci_low","station_ci_high","status"]].to_string(index=False))
print("\ncolumns:", list(cs.columns))
