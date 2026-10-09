# -*- coding: utf-8 -*-
"""
Archive-based supplementary analyses for the river monitoring methods paper.

Reads ONLY from:
  D:/MLWork/NitrateAdaptiveSampling_20261005/revision_20261009/
Writes ONLY into:
  F:/SCI/nitrate_rev/analysis_arch/

Every number is computed here from the archived tables. Nothing is typed in by hand.
"""
from pathlib import Path
import hashlib, json, sys
import numpy as np
import pandas as pd

ARCH = Path(r"D:/MLWork/NitrateAdaptiveSampling_20261005/revision_20261009")
RES  = ARCH / "results"
SUM  = RES / "summary_main_v1"
TMP  = RES / "experiments_main_temporal_v1"
EXT  = RES / "experiments_main_external_v1"
DIA  = RES / "diagnostics_v1"
OUT  = Path(r"F:/SCI/nitrate_rev/analysis_arch")

BUDGET = 96
BOOT_REPLICATES = 10000
BOOT_SEED = 271828
GRID_HOURS = 6          # value_sampling.ValueSamplingConfig.candidate_interval_hours
MIN_SPACING_HOURS = 24  # value_sampling.ValueSamplingConfig.min_spacing_hours

COHORT_OF_STAGE = {"temporal": "temporal", "external": "additional", "development": "development"}
STAGE_OF_COHORT = {"temporal": "temporal", "additional": "external", "development": "development"}
POLICY_LABEL = {"uniform": "Periodic", "flow_trigger": "Flow trigger",
                "deadline_only": "Block deadline", "value": "Load value",
                "no_new_labels": "Historical predictor"}

# full measure list of the archived station/site-year tables
MEASURES = ["event_mean_absolute_relative_error", "absolute_valid_window_bias",
            "hourly_load_normalized_absolute_error", "concentration_mae_mg_l",
            "event_mean_signed_error_kg", "event_mean_absolute_error_kg",
            "event_fraction_within_10pct", "event_fraction_within_20pct",
            "event_fraction_worse_than_50pct"]
# measures that can be rebuilt from eligible_events.csv alone (event-level endpoints).
# absolute_valid_window_bias, hourly_load_normalized_absolute_error and concentration_mae_mg_l
# are whole-window metrics of experiments_*_v1/metrics.csv and are NOT archived per event.
# eligible_events.csv stores per-event columns only; the archives build these six
# endpoint measures with exactly the aggregation used in summarize_revision.py.
EVENT_COLUMN_MAP = {
    "event_mean_absolute_relative_error": "event_abs_relative_error",
    "event_mean_signed_error_kg": "event_signed_error_kg",
    "event_mean_absolute_error_kg": "event_absolute_error_kg",
    "event_fraction_within_10pct": "event_flag_10",
    "event_fraction_within_20pct": "event_flag_20",
    "event_fraction_worse_than_50pct": "event_flag_50",
}
EVENT_MEASURES = list(EVENT_COLUMN_MAP)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def station_bootstrap(frame, cluster="site"):
    """Exact copy of summarize_revision.py::interval (station-block resampling)."""
    groups = list(frame.dropna(subset=["difference", cluster]).groupby(cluster).difference)
    if len(groups) < 2:
        return np.nan, np.nan
    sums = np.array([v.sum() for _, v in groups])
    counts = np.array([len(v) for _, v in groups])
    draws = np.random.default_rng(BOOT_SEED).integers(len(groups), size=(BOOT_REPLICATES, len(groups)))
    values = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return float(np.quantile(values, .025)), float(np.quantile(values, .975))

# ---------------------------------------------------------------- inputs
inputs = {
    "eligible_events": SUM / "eligible_events.csv",
    "station_metrics": SUM / "station_metrics.csv",
    "site_year_metrics": SUM / "site_year_metrics.csv",
    "paired_effects": SUM / "paired_effects.csv",
    "aggregate_metrics": SUM / "aggregate_metrics.csv",
    "summary_manifest": SUM / "summary_manifest.json",
    "attempts_temporal": TMP / "attempts.csv",
    "attempts_external": EXT / "attempts.csv",
    "attempt_summaries": DIA / "attempt_summaries.csv",
    "factor_family_contrasts": DIA / "factor_family_contrasts.csv",
    "mechanism_contrasts": DIA / "mechanism_contrasts.csv",
    "context_events": RES / "context_events.csv",
    "context_site_year": RES / "context_site_year.csv",
    "context_station_year_diagnostics": RES / "context_station_year_diagnostics.csv",
    "context_residual_persistence": RES / "context_residual_persistence.csv",
    "context_forward_model": RES / "context_forward_model.csv",
    "context_event_retention_summary": RES / "context_event_retention_summary.csv",
    "context_summary": RES / "context_summary.json",
    "context_variable_definitions": RES / "context_variable_definitions.json",
    "context_manifest": RES / "context_manifest.json",
    "context_analysis_plan": RES / "context_analysis_plan.json",
    "docs_CONTEXT_ANALYSIS": ARCH / "docs" / "CONTEXT_ANALYSIS.md",
    "docs_EXPERIMENTS": ARCH / "docs" / "EXPERIMENTS.md",
}
for k, p in inputs.items():
    if not p.exists():
        sys.exit("MISSING INPUT: " + str(p))

ctx_events = pd.read_csv(inputs["context_events"], dtype={"site": str, "huc4_group": str})
eligible   = pd.read_csv(inputs["eligible_events"], dtype={"site": str})
station_m  = pd.read_csv(inputs["station_metrics"], dtype={"site": str, "huc4": str})
site_year  = pd.read_csv(inputs["site_year_metrics"], dtype={"site": str, "huc4": str})
paired     = pd.read_csv(inputs["paired_effects"], dtype={"site": str})
aggregate  = pd.read_csv(inputs["aggregate_metrics"], dtype={"site": str})
ctx_sy     = pd.read_csv(inputs["context_site_year"], dtype={"site": str, "huc4_group": str})
ctx_res    = pd.read_csv(inputs["context_residual_persistence"], dtype={"site": str})
ctx_fwd    = pd.read_csv(inputs["context_forward_model"], dtype={"site": str})
att_t      = pd.read_csv(inputs["attempts_temporal"], dtype={"site": str})
att_e      = pd.read_csv(inputs["attempts_external"], dtype={"site": str})

# eligible_events.csv carries no HUC4 column; the archived station_metrics.csv does.
# Use exactly that archived mapping (it is the same mapping that produced paired_effects.csv).
HUC4 = station_m.drop_duplicates("site").set_index("site").huc4
eligible["huc4"] = eligible.site.map(HUC4)
if eligible.huc4.isna().any():
    sys.exit("site without archived HUC4: " + str(sorted(eligible.loc[eligible.huc4.isna(), 'site'].unique())))
ctx_events["huc4"] = ctx_events.site.map(HUC4)

log = {}

# =================================================================
# (1) COVERAGE-THRESHOLD SENSITIVITY
# =================================================================
# The pre-screen event universe IS archived: context_events.csv holds every
# detected event of the three cohorts with its reference_hour_coverage,
# before the 95% retention rule.  eligible_events.csv holds only events that
# already passed the 95% screen (coverage min 0.95556).
THRESHOLDS = [0.90, 0.95, 1.00]
EPS = 1e-9
universe = ctx_events.copy()
universe["passes_threshold"] = False

screen_rows, distribution_rows = [], []
for thr in THRESHOLDS:
    keep = universe[(universe.reference_hour_coverage >= thr - EPS) & (~universe.boundary_uncertain)]
    thr95 = universe[(universe.reference_hour_coverage >= 0.95 - EPS) & (~universe.boundary_uncertain)]
    for cohort in ["temporal", "additional", "development"]:
        stage = STAGE_OF_COHORT[cohort]
        k = keep[keep.stage == stage]
        b = thr95[thr95.stage == stage]
        added = set(zip(k.site, k.year, k.event_id)) - set(zip(b.site, b.year, b.event_id))
        addf = universe[[t in added for t in zip(universe.site, universe.year, universe.event_id)]]
        screen_rows.append(dict(
            added_events_median_event_hours=float(addf.hours.median()) if len(addf) else np.nan,
            added_events_median_q_peak_cms=float(addf.q_peak_cms.median()) if len(addf) else np.nan,
            added_events_median_reference_load_kg=float(addf.reference_load_kg.median()) if len(addf) else np.nan,
            added_events_share_reference_at_q_peak=(float(addf.q_peak_hour_reference_valid.mean()) if len(addf) else np.nan),
            added_events_nonpositive_reference_load=int((addf.reference_load_kg <= 1e-8).sum()),
            threshold=thr, cohort=cohort, stage=stage, record_type="screening",
            included_stations=int(k.site.nunique()), included_events=int(len(k)),
            mean_reference_support=float(k.reference_hour_coverage.mean()) if len(k) else np.nan,
            median_reference_support=float(k.reference_hour_coverage.median()) if len(k) else np.nan,
            min_reference_support=float(k.reference_hour_coverage.min()) if len(k) else np.nan,
            mean_event_hours=float(k.hours.mean()) if len(k) else np.nan,
            mean_reference_hours=float(k.reference_hours.mean()) if len(k) else np.nan,
            events_added_vs_95pct=int(len(added)),
            stations_added_vs_95pct=int(len(set(s for s, _, _ in added) - set(b.site))),
            stations_lost_vs_95pct=int(len(set(b.site) - set(k.site))),
        ))


# coverage distribution of the events retained by the 95% rule (temporal + additional pooled)
_r95 = universe[(universe.reference_hour_coverage >= 0.95 - EPS) & (~universe.boundary_uncertain) &
                universe.stage.isin(["temporal", "external"])]
for q in [0, .05, .10, .25, .50, .75, .90, .95, 1.0]:
    distribution_rows.append(dict(threshold=0.95, cohort="temporal+additional",
                                  record_type="retained_coverage_quantile",
                                  quantile=q, value=float(_r95.reference_hour_coverage.quantile(q))))

# endpoint availability check: which events exist in eligible_events.csv?
elig_events = eligible[["site", "year", "stage", "event_id", "coverage", "hours"]].drop_duplicates(
    ["site", "year", "stage", "event_id"])
merged = elig_events.merge(
    ctx_events[["site", "year", "stage", "event_id", "reference_hour_coverage", "eligible"]],
    on=["site", "year", "stage", "event_id"], how="left", validate="one_to_one")
assert merged.reference_hour_coverage.notna().all()
assert np.allclose(merged.coverage, merged.reference_hour_coverage, atol=1e-12)
log["eligible_event_universe"] = dict(
    n_events=int(len(elig_events)), by_stage=elig_events.stage.value_counts().to_dict(),
    coverage_min=float(elig_events.coverage.min()), coverage_max=float(elig_events.coverage.max()),
    n_events_coverage_ge_1p0=int((elig_events.coverage >= 1 - EPS).sum()),
    n_events_coverage_lt_0p95=int((elig_events.coverage < 0.95 - EPS).sum()))
log["pre_screen_universe"] = dict(
    n_events=int(len(ctx_events)), by_stage=ctx_events.stage.value_counts().to_dict(),
    coverage_min=float(ctx_events.reference_hour_coverage.min()),
    n_below_0p90=int((ctx_events.reference_hour_coverage < 0.90 - EPS).sum()),
    n_in_0p90_to_0p95=int(((ctx_events.reference_hour_coverage >= 0.90 - EPS) &
                           (ctx_events.reference_hour_coverage < 0.95 - EPS)).sum()),
    n_in_0p95_to_1p0=int(((ctx_events.reference_hour_coverage >= 0.95 - EPS) &
                          (ctx_events.reference_hour_coverage < 1 - EPS)).sum()),
    excluded_reason=ctx_events.excluded_reason.value_counts().to_dict(),
    nonpositive_reference_load=int((ctx_events.reference_load_kg <= 0).sum()))

# ---- rebuild the archived site-year / station pipeline on eligible_events
BASE = ["stage", "experiment", "scenario", "reconstructor", "delay_hours", "budget",
        "reconstructor_family", "half_life_hours", "age_origin"]

def build_siteyear(events_frame, event_counts):
    """events_frame: eligible_events rows restricted to the chosen event subset."""
    sy = (events_frame.groupby(BASE + ["policy", "site", "year", "huc4"], dropna=False)
          [list(EVENT_COLUMN_MAP.values())].mean().reset_index()
          .rename(columns={v: k for k, v in EVENT_COLUMN_MAP.items()}))
    sy["events_eligible"] = sy.set_index(["site", "year"]).index.map(event_counts).to_numpy()
    return sy

def event_counts_for(subset):
    c = subset.drop_duplicates(["site", "year", "event_id"]).groupby(["site", "year"]).size()
    return c

def wide_by_policy(sy, stage, budget, measure, min_events=1):
    """(site, year) x policy matrix for one budget, with the zero-label comparator merged in,
    exactly as summarize_revision.py does it."""
    primary = sy[(sy.stage == stage) & (sy.events_eligible >= min_events)]
    frame = primary[primary.budget == budget]
    if frame.empty:
        return None
    wide = frame.pivot_table(index=["site", "year", "huc4"], columns="policy", values=measure)
    zero = primary[(primary.policy == "no_new_labels") & (primary.budget == 0)]
    if len(zero):
        wide["no_new_labels"] = zero.groupby(["site", "year", "huc4"])[measure].mean()
    return wide

def paired_block(sy, budget, stage, measure, baseline, min_events=1):
    wide = wide_by_policy(sy, stage, budget, measure, min_events)
    if wide is None or "value" not in wide or baseline not in wide:
        return None
    delta = wide[baseline] - wide["value"]
    z = delta.rename("difference").reset_index().groupby(["site", "huc4"]).difference.mean().reset_index()
    if len(z) < 2:
        return None
    lo, hi = station_bootstrap(z, "site")
    hz = z.assign(huc4=z.huc4.fillna("NA"))
    hlo, hhi = station_bootstrap(hz, "huc4")
    return dict(stations=int(len(z)), mean_difference=float(z.difference.mean()),
                median_difference=float(z.difference.median()),
                stations_value_better=int((z.difference > 0).sum()),
                station_ci_low=lo, station_ci_high=hi, huc4_ci_low=hlo, huc4_ci_high=hhi)

def equal_station_means(sy, budget, stage, measure, min_events=1):
    """Equal-station mean of the endpoint, the hierarchy of Tables 2 and 3."""
    wide = wide_by_policy(sy, stage, budget, measure, min_events)
    return {pol: float(wide[pol].groupby(level=["site"]).mean().mean())
            for pol in ["uniform", "flow_trigger", "deadline_only", "value", "no_new_labels"]
            if pol in wide.columns}

sy_all = build_siteyear(eligible, event_counts_for(elig_events))

# verification against the archived paired_effects.csv (95% screen, both specifications)
verify = []
# cross-check the rebuilt site-year table against the archived summary_main_v1/site_year_metrics.csv
# site_year_metrics.csv keeps station-years with zero eligible events (no event rows exist there);
# every row that does have events must reproduce exactly.
_chk = sy_all.merge(site_year, on=BASE + ["policy", "site", "year", "huc4"],
                    suffixes=("_mine", "_arch"), how="inner", validate="one_to_one")
_arch_no_events = len(site_year) - len(_chk)
_siteyear_repro_max = float(max((_chk[m + "_mine"] - _chk[m + "_arch"]).abs().max() for m in EVENT_MEASURES))
assert _siteyear_repro_max < 1e-9, _siteyear_repro_max  # float summation-order tolerance

for meas in EVENT_MEASURES:
    for stage in ["temporal", "external"]:
        for me in [1, 3]:
            for base in ["uniform", "flow_trigger", "deadline_only", "no_new_labels"]:
                got = paired_block(sy_all, BUDGET, stage, meas, base, me)
                if got is None:
                    continue
                arch = paired[(paired.stage == stage) & (paired.budget == BUDGET) & (paired.measure == meas) &
                              (paired.baseline == base) & (paired.minimum_events == me)]
                if arch.empty:
                    continue
                a = arch.iloc[0]
                verify.append(dict(measure=meas, stage=stage, minimum_events=me, baseline=base,
                                   stations_match=int(a.stations) == got["stations"],
                                   max_abs_diff=float(max(abs(a.mean_difference - got["mean_difference"]),
                                                           abs(a.median_difference - got["median_difference"]),
                                                           abs(a.station_ci_low - got["station_ci_low"]),
                                                           abs(a.station_ci_high - got["station_ci_high"])))))
log["reproduction_of_site_year_metrics"] = dict(
    rows_compared=int(len(_chk)), archived_rows_without_eligible_events=int(_arch_no_events),
    max_absolute_difference=_siteyear_repro_max)
log["reproduction_of_archived_paired_effects"] = dict(
    n_compared=len(verify),
    stations_all_match=bool(all(v["stations_match"] for v in verify)),
    max_absolute_difference=float(max(v["max_abs_diff"] for v in verify)) if verify else None)

# 100% subset pipeline
ev100 = elig_events[elig_events.coverage >= 1 - EPS]
sy_100 = build_siteyear(eligible.merge(ev100[["site", "year", "event_id"]], on=["site", "year", "event_id"], how="inner"),
                        event_counts_for(ev100))

PRIMARY_BASELINES = ["flow_trigger", "no_new_labels"]
ALL_BASELINES = ["uniform", "flow_trigger", "deadline_only", "no_new_labels"]
PRIMARY_MEASURES = ["event_mean_absolute_relative_error", "event_mean_absolute_error_kg"]

cov_rows = list(screen_rows)
for r in distribution_rows:
    cov_rows.append(dict(threshold=r["threshold"], cohort=r["cohort"], stage="temporal+external",
                         record_type=r["record_type"], included_stations=np.nan, included_events=np.nan,
                         mean_reference_support=np.nan, median_reference_support=np.nan,
                         min_reference_support=np.nan, mean_event_hours=np.nan, mean_reference_hours=np.nan,
                         events_added_vs_95pct=np.nan, stations_added_vs_95pct=np.nan,
                         stations_lost_vs_95pct=np.nan, quantile=r["quantile"], quantile_value=r["value"]))

def paired_rows(threshold, sy_frame, status, note):
    rows = []
    for cohort in ["temporal", "additional"]:
        stage = STAGE_OF_COHORT[cohort]
        for meas in PRIMARY_MEASURES:
            for base in ALL_BASELINES:
                if status != "computed":
                    rows.append(dict(threshold=threshold, cohort=cohort, stage=stage, record_type="paired",
                                     measure=meas, baseline=base, baseline_label=POLICY_LABEL[base],
                                     status=status, note=note))
                    continue
                got = paired_block(sy_frame, BUDGET, stage, meas, base, 1)
                means = equal_station_means(sy_frame, BUDGET, stage, meas, 1)
                ev = int(sy_frame[(sy_frame.stage == stage) & (sy_frame.budget == BUDGET) &
                                  (sy_frame.events_eligible >= 1)].drop_duplicates(["site", "year"]).events_eligible.sum())
                rows.append(dict(threshold=threshold, cohort=cohort, stage=stage, record_type="paired",
                                 measure=meas, baseline=base, baseline_label=POLICY_LABEL[base],
                                 paired_stations=got["stations"] if got else np.nan,
                                 paired_events=ev,
                                 value_equal_station_mean=means.get("value"),
                                 baseline_equal_station_mean=means.get(base),
                                 mean_difference=got["mean_difference"] if got else np.nan,
                                 median_difference=got["median_difference"] if got else np.nan,
                                 stations_value_better=got["stations_value_better"] if got else np.nan,
                                 station_ci_low=got["station_ci_low"] if got else np.nan,
                                 station_ci_high=got["station_ci_high"] if got else np.nan,
                                 huc4_ci_low=got["huc4_ci_low"] if got else np.nan,
                                 huc4_ci_high=got["huc4_ci_high"] if got else np.nan,
                                 status="computed", note=note))
    return rows

cov_rows += paired_rows(0.95, sy_all, "computed",
                        "archived 95% retention screen; recomputed here and identical to summary_main_v1/paired_effects.csv")
cov_rows += paired_rows(1.00, sy_100, "computed",
                        "strict subset of the 95% screen (coverage exactly 1.0); recomputed with the same station bootstrap")
cov_rows += paired_rows(0.90, None, "not_computable",
                        "events newly admitted between 90% and 95% coverage were never scored, so their event mass endpoints are not archived")

coverage_sensitivity = pd.DataFrame(cov_rows)
COVERAGE_COLUMNS = ["threshold", "cohort", "stage", "record_type", "included_stations", "included_events",
                    "mean_reference_support", "median_reference_support", "min_reference_support",
                    "mean_event_hours", "mean_reference_hours", "events_added_vs_95pct",
                    "stations_added_vs_95pct", "stations_lost_vs_95pct",
                    "added_events_median_event_hours", "added_events_median_q_peak_cms",
                    "added_events_median_reference_load_kg", "added_events_share_reference_at_q_peak",
                    "added_events_nonpositive_reference_load", "quantile", "quantile_value",
                    "measure", "baseline", "baseline_label", "paired_stations", "paired_events",
                    "value_equal_station_mean", "baseline_equal_station_mean", "mean_difference",
                    "median_difference", "stations_value_better", "station_ci_low", "station_ci_high",
                    "huc4_ci_low", "huc4_ci_high", "status", "note"]
coverage_sensitivity = coverage_sensitivity.reindex(columns=COVERAGE_COLUMNS)
coverage_sensitivity.to_csv(OUT / "coverage_sensitivity.csv", index=False)

# =================================================================
# (2) SAMPLING-OPPORTUNITY OVERLAP AT BUDGET 96
# =================================================================
att = pd.concat([att_t.assign(file="experiments_main_temporal_v1"),
                 att_e.assign(file="experiments_main_external_v1")], ignore_index=True)
att96 = att[att.budget == BUDGET].copy()
att96["t"] = pd.to_datetime(att96.sample_time, utc=True)
assert att96.groupby(["policy", "site", "year", "seed"]).size().eq(BUDGET).all()
# grid check -> exact timestamps are unambiguous on a 6 h candidate grid with 24 h spacing
assert bool(((att96.t.dt.hour % GRID_HOURS) == 0).all() and (att96.t.dt.minute == 0).all())
assert bool((att96.t.dt.second == 0).all())

# label_success must be a property of the purchased hour, not of the policy
ks = att96[["site", "year", "seed", "sample_index", "label_success"]].drop_duplicates()
assert not ks.duplicated(["site", "year", "seed", "sample_index"]).any()

# stations belonging to the primary (minimum_events = 1) analysis cohort
primary_sites = {}
for stage in ["temporal", "external"]:
    f = station_m[(station_m.stage == stage) & (station_m.budget == BUDGET) &
                  (station_m.minimum_events == 1) & (station_m.policy == "value")]
    primary_sites[stage] = set(f.site.unique())   # stations with >= 1 eligible event (primary specification)

overlap_rows = []
for stage in ["temporal", "external"]:
    sub = att96[att96.stage == stage]
    for scope in ["all_archived_station_years", "primary_event_eligible_station_years"]:
        use = sub if scope == "all_archived_station_years" else sub[sub.site.isin(primary_sites[stage])]
        for base in ["flow_trigger", "uniform", "deadline_only"]:
            identical = 0; near_only = 0; n_groups = 0; attempts_a = 0; attempts_b = 0
            succ_a = 0; succ_b = 0; avail_a = 0; avail_b = 0
            for (site, year, seed), grp in use.groupby(["site", "year", "seed"]):
                A = np.sort(grp[grp.policy == "value"].t.values.astype("datetime64[h]").astype(np.int64))
                B = np.sort(grp[grp.policy == base].t.values.astype("datetime64[h]").astype(np.int64))
                n_groups += 1; attempts_a += len(A); attempts_b += len(B)
                succ_a += int(grp[grp.policy == "value"].label_success.sum())
                succ_b += int(grp[grp.policy == base].label_success.sum())
                avail_a += int(grp[grp.policy == "value"].label_available_by_horizon.sum())
                avail_b += int(grp[grp.policy == base].label_available_by_horizon.sum())
                inter = np.intersect1d(A, B)
                identical += len(inter)
                idx = np.searchsorted(B, A)
                left = np.clip(idx - 1, 0, len(B) - 1); right = np.clip(idx, 0, len(B) - 1)
                within = np.minimum(np.abs(A - B[left]), np.abs(A - B[right])) <= GRID_HOURS
                near_only += int(within.sum()) - len(inter)
            overlap_rows.append(dict(
                cohort=COHORT_OF_STAGE[stage], stage=stage, scope=scope, budget=BUDGET,
                policy_a="value", policy_a_label=POLICY_LABEL["value"],
                policy_b=base, policy_b_label=POLICY_LABEL[base],
                station_year_seed_groups=n_groups,
                attempts_a=attempts_a, attempts_b=attempts_b,
                identical_timestamps=identical, differing_timestamps=attempts_a - identical,
                timestamps_within_6h_not_identical=near_only,
                successful_returns_a=succ_a, successful_returns_b=succ_b,
                success_rate_a=succ_a / attempts_a if attempts_a else np.nan,
                success_rate_b=succ_b / attempts_b if attempts_b else np.nan,
                returns_available_in_year_a=avail_a, returns_available_in_year_b=avail_b,
                note=("all purchase times lie on the archived 6 h candidate grid with 24 h minimum spacing, "
                      "so identical/differing counts use exact timestamp equality; the 6 h column counts "
                      "timestamps whose nearest counterpart is an adjacent 6 h grid slot"),
            ))
overlap_counts = pd.DataFrame(overlap_rows)
overlap_counts.to_csv(OUT / "overlap_counts.csv", index=False)
log["overlap"] = dict(rows=len(overlap_counts), attempts_per_policy_group=int(BUDGET))

# =================================================================
# (3) PAIRED MASS ERROR AND PER-STATION DIFFERENCES
# =================================================================
mass_rows = []
for stage in ["temporal", "external"]:
    cohort = COHORT_OF_STAGE[stage]
    for me in [1, 3]:
        for meas in ["event_mean_absolute_error_kg", "event_mean_absolute_relative_error"]:
            for base in ["uniform", "flow_trigger", "deadline_only"]:
                arch = paired[(paired.stage == stage) & (paired.budget == BUDGET) & (paired.measure == meas) &
                              (paired.baseline == base) & (paired.minimum_events == me)]
                a = arch.iloc[0]
                got = paired_block(sy_all, BUDGET, stage, meas, base, me)
                means = equal_station_means(sy_all, BUDGET, stage, meas, me)
                ev = int(sy_all[(sy_all.stage == stage) & (sy_all.budget == BUDGET) &
                                (sy_all.events_eligible >= me)].drop_duplicates(["site", "year"]).events_eligible.sum())
                mass_rows.append(dict(
                    cohort=cohort, stage=stage, budget=BUDGET,
                    specification="minimum_events=%d" % me,
                    primary_specification=(me == 1),
                    measure=meas, baseline=base, baseline_label=POLICY_LABEL[base],
                    paired_stations=int(a.stations), paired_events=ev,
                    value_equal_station_mean=means.get("value"),
                    baseline_equal_station_mean=means.get(base),
                    mean_difference=float(a.mean_difference), median_difference=float(a.median_difference),
                    stations_value_better=int(a.candidate_lower),
                    station_ci_low=float(a.station_ci_low), station_ci_high=float(a.station_ci_high),
                    huc4_ci_low=float(a.huc4_ci_low), huc4_ci_high=float(a.huc4_ci_high),
                    ci_excludes_zero=bool(float(a.station_ci_low) > 0 or float(a.station_ci_high) < 0),
                    independently_recomputed_mean_difference=got["mean_difference"] if got else np.nan,
                    reproduction_max_abs_difference=(None if got is None else float(max(
                        abs(a.mean_difference - got["mean_difference"]),
                        abs(a.station_ci_low - got["station_ci_low"]),
                        abs(a.station_ci_high - got["station_ci_high"])))),
                    convention="difference = baseline minus value; positive means value has the lower error",
                    source="results/summary_main_v1/paired_effects.csv",
                ))
mass_error_pairs = pd.DataFrame(mass_rows)
mass_error_pairs.to_csv(OUT / "mass_error_pairs.csv", index=False)

# per-station value minus flow
per_station_rows = []
for stage in ["temporal", "external"]:
    cohort = COHORT_OF_STAGE[stage]
    f = station_m[(station_m.stage == stage) & (station_m.budget == BUDGET) & (station_m.minimum_events == 1)]
    wide = f.pivot_table(index=["site", "huc4"], columns="policy",
                         values=["event_mean_absolute_relative_error", "event_mean_absolute_error_kg"])
    ev = elig_events[elig_events.stage == stage].drop_duplicates(["site", "year", "event_id"]).groupby("site").size()
    ev_det = ctx_events[ctx_events.stage == stage].groupby("site").size()
    syrow = site_year[(site_year.stage == stage) & (site_year.policy == "value") &
                      (site_year.budget == BUDGET) & (site_year.events_eligible >= 1)]
    sycount = syrow.groupby("site").size()
    for (site, huc4), row in wide.iterrows():
        per_station_rows.append(dict(
            cohort=cohort, stage=stage, site=site, huc4=huc4,
            specification="budget=96, minimum_events=1",
            station_years_in_primary=int(sycount.get(site, 0)),
            events_eligible=int(ev.get(site, 0)), events_detected=int(ev_det.get(site, 0)),
            value_mean_abs_relative_error=row[("event_mean_absolute_relative_error", "value")],
            flow_mean_abs_relative_error=row[("event_mean_absolute_relative_error", "flow_trigger")],
            value_minus_flow_abs_relative_error=row[("event_mean_absolute_relative_error", "value")] -
                                                 row[("event_mean_absolute_relative_error", "flow_trigger")],
            value_mean_abs_mass_error_kg=row[("event_mean_absolute_error_kg", "value")],
            flow_mean_abs_mass_error_kg=row[("event_mean_absolute_error_kg", "flow_trigger")],
            value_minus_flow_abs_mass_error_kg=row[("event_mean_absolute_error_kg", "value")] -
                                               row[("event_mean_absolute_error_kg", "flow_trigger")],
        ))
per_station = pd.DataFrame(per_station_rows)
per_station["updating_worsened_relative_error"] = per_station.value_minus_flow_abs_relative_error > 0
per_station["updating_worsened_mass_error"] = per_station.value_minus_flow_abs_mass_error_kg > 0
per_station = per_station.sort_values(["value_minus_flow_abs_relative_error", "site"],
                                      ascending=[False, True]).reset_index(drop=True)
per_station.to_csv(OUT / "per_station_differences.csv", index=False)

# =================================================================
# (4) STATION PROFILE
# =================================================================
cohort_sites = {
    "temporal":    sorted(site_year[site_year.stage == "temporal"].site.unique()),
    "additional":  sorted(site_year[site_year.stage == "external"].site.unique()),
    "development": sorted(ctx_fwd[ctx_fwd.stage == "development"].site.unique()),
}
cohort_years = {
    "temporal":    sorted(site_year[site_year.stage == "temporal"].year.unique()),
    "additional":  sorted(site_year[site_year.stage == "external"].year.unique()),
    "development": sorted(ctx_fwd[ctx_fwd.stage == "development"].year.unique()),
}
elig_ctx = ctx_events[ctx_events.eligible]
res_primary = ctx_res[ctx_res.pair_support == "continuous_all_hours_qualified"]

profile_rows = []
all_sites = sorted(set().union(*[set(v) for v in cohort_sites.values()]))
for site in all_sites:
    members = [c for c in ["temporal", "additional", "development"] if site in cohort_sites[c]]
    ev = elig_ctx[elig_ctx.site == site]
    ev_all = ctx_events[ctx_events.site == site]
    yrs = sorted(set(y for c in members for y in cohort_years[c]))
    name = ctx_sy.loc[ctx_sy.site == site, "site_name"].dropna()
    huc = ctx_sy.loc[ctx_sy.site == site, "huc4_group"].dropna()
    conc = ctx_sy[(ctx_sy.site == site) & (ctx_sy.year.isin(yrs))].reference_nox_mean_mg_l.dropna()
    lag = {}
    for L in [6, 24, 72, 168]:
        v = res_primary[(res_primary.site == site) & (res_primary.lag_hours == L)].pearson_residual_autocorrelation.dropna()
        lag[L] = float(v.median()) if len(v) else np.nan
        lag[str(L) + "_n"] = int(len(v))
    profile_rows.append(dict(
        site=site,
        site_name=name.iloc[0] if len(name) else "",
        huc4=huc.iloc[0] if len(huc) else "",
        cohort_membership=";".join(members),
        evaluation_years=";".join(str(y) for y in yrs),
        evaluation_years_temporal=";".join(str(y) for y in cohort_years["temporal"]) if "temporal" in members else "",
        evaluation_years_additional=";".join(str(y) for y in cohort_years["additional"]) if "additional" in members else "",
        evaluation_years_development=";".join(str(y) for y in cohort_years["development"]) if "development" in members else "",
        events_eligible_total=int(len(ev)),
        events_eligible_temporal=int((ev.stage == "temporal").sum()),
        events_eligible_additional=int((ev.stage == "external").sum()),
        events_eligible_development=int((ev.stage == "development").sum()),
        events_detected_total=int(len(ev_all)),
        median_reference_coverage_eligible=float(ev.reference_hour_coverage.median()) if len(ev) else np.nan,
        median_q_peak_cms_eligible=float(ev.q_peak_cms.median()) if len(ev) else np.nan,
        median_reference_load_kg_eligible=float(ev.reference_load_kg.median()) if len(ev) else np.nan,
        median_reference_nox_mean_mg_l=float(conc.median()) if len(conc) else np.nan,
        n_reference_concentration_years=int(len(conc)),
        historical_forward_residual_lag_corr_6h=lag[6],
        historical_forward_residual_lag_corr_24h=lag[24],
        historical_forward_residual_lag_corr_72h=lag[72],
        historical_forward_residual_lag_corr_168h=lag[168],
        historical_forward_residual_lag_corr_station_years=lag["6_n"],
    ))
station_profile = pd.DataFrame(profile_rows).sort_values("site").reset_index(drop=True)
station_profile.to_csv(OUT / "station_profile.csv", index=False)

# =================================================================
# (5) MANIFEST + CONSOLE SUMMARY
# =================================================================
manifest = dict(
    generated_utc=pd.Timestamp.now(tz="UTC").isoformat(),
    python=sys.version.split()[0], pandas=pd.__version__, numpy=np.__version__,
    archive_root=str(ARCH), output_root=str(OUT),
    read_only_note="no file under the archive root was created, modified or deleted",
    bootstrap_replicates=BOOT_REPLICATES, bootstrap_seed=BOOT_SEED,
    primary_budget=BUDGET, candidate_grid_hours=GRID_HOURS, minimum_spacing_hours=MIN_SPACING_HOURS,
    estimand="mean within station-year-seed events, across seeds, then years within station, equal stations",
    difference_convention="baseline minus value; positive means value has the lower error",
    cohort_naming={"temporal": "temporal", "external": "additional-station", "development": "development"},
    input_sha256={k: sha256(p) for k, p in sorted(inputs.items())},
    script_sha256=sha256(Path(__file__)),
    outputs={},
)
for f in ["coverage_sensitivity.csv", "overlap_counts.csv", "mass_error_pairs.csv",
          "per_station_differences.csv", "station_profile.csv"]:
    manifest["outputs"][f] = dict(sha256=sha256(OUT / f), rows=int(len(pd.read_csv(OUT / f))))
(OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

log["coverage_sensitivity_headline"] = {
    "%d%%" % int(t * 100): {
        c: dict(stations=int(coverage_sensitivity[(coverage_sensitivity.threshold == t) &
                                                  (coverage_sensitivity.cohort == c) &
                                                  (coverage_sensitivity.record_type == "screening")].included_stations.iloc[0]),
                events=int(coverage_sensitivity[(coverage_sensitivity.threshold == t) &
                                                (coverage_sensitivity.cohort == c) &
                                                (coverage_sensitivity.record_type == "screening")].included_events.iloc[0]),
                mean_support=float(coverage_sensitivity[(coverage_sensitivity.threshold == t) &
                                                        (coverage_sensitivity.cohort == c) &
                                                        (coverage_sensitivity.record_type == "screening")].mean_reference_support.iloc[0]),
                added=int(coverage_sensitivity[(coverage_sensitivity.threshold == t) &
                                               (coverage_sensitivity.cohort == c) &
                                               (coverage_sensitivity.record_type == "screening")].events_added_vs_95pct.iloc[0]))
        for c in ["temporal", "additional", "development"]}
    for t in THRESHOLDS}
log["station_profile"] = dict(stations=int(len(station_profile)),
                              with_residual_lags=int(station_profile.historical_forward_residual_lag_corr_6h.notna().sum()),
                              cohorts={c: len(v) for c, v in cohort_sites.items()})
log["per_station"] = dict(
    temporal_worsened=int(((per_station.cohort == "temporal") & per_station.updating_worsened_relative_error).sum()),
    temporal_n=int((per_station.cohort == "temporal").sum()),
    additional_worsened=int(((per_station.cohort == "additional") & per_station.updating_worsened_relative_error).sum()),
    additional_n=int((per_station.cohort == "additional").sum()))
print(json.dumps(log, indent=2, default=str))
