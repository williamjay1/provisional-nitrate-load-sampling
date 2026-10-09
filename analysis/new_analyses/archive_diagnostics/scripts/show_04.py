
import pandas as pd
pd.set_option("display.width",300); pd.set_option("display.max_columns",60); pd.set_option("display.max_rows",60)
O = r"F:\SCI\nitrate_rev\analysis_arch"
o = pd.read_csv(O+r"\overlap_counts.csv")
print(o[["cohort","scope","policy_b_label","station_year_seed_groups","attempts_a","identical_timestamps","differing_timestamps","timestamps_within_6h_not_identical","successful_returns_a","successful_returns_b","returns_available_in_year_a","returns_available_in_year_b"]].to_string(index=False))
p = pd.read_csv(O+r"\per_station_differences.csv", dtype={"site":str,"huc4":str})
print("\n"); print(p[["cohort","site","huc4","station_years_in_primary","events_eligible","events_detected","value_mean_abs_relative_error","flow_mean_abs_relative_error","value_minus_flow_abs_relative_error","value_minus_flow_abs_mass_error_kg"]].to_string(index=False))
print("\ncolumn order:", list(p.columns))
