
import pandas as pd
pd.set_option("display.width",280); pd.set_option("display.max_columns",60); pd.set_option("display.max_rows",300)
O = r"F:\SCI\nitrate_rev\analysis_arch"
print("=========== overlap_counts.csv ===========")
o = pd.read_csv(O+r"\overlap_counts.csv")
print(o.to_string(index=False))
print("\n=========== mass_error_pairs.csv ===========")
m = pd.read_csv(O+r"\mass_error_pairs.csv")
print(m[["cohort","specification","measure","baseline_label","paired_stations","paired_events","value_equal_station_mean","baseline_equal_station_mean","mean_difference","median_difference","stations_value_better","station_ci_low","station_ci_high","ci_excludes_zero","reproduction_max_abs_difference"]].to_string(index=False))
print("\n=========== per_station_differences.csv ===========")
p = pd.read_csv(O+r"\per_station_differences.csv", dtype={"site":str})
print(p[["cohort","site","huc4","events_eligible","events_detected","value_mean_abs_relative_error","flow_mean_abs_relative_error","value_minus_flow_abs_relative_error","value_minus_flow_abs_mass_error_kg","updating_worsened_relative_error"]].to_string(index=False))
print("\n=========== station_profile.csv ===========")
s = pd.read_csv(O+r"\station_profile.csv", dtype={"site":str,"huc4":str})
print(s.to_string(index=False))
