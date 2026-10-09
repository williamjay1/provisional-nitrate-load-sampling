"""Post-review monitoring context diagnostics; reads frozen inputs without alteration.

All load shares describe observed support, never missing true transport or an error
lower bound. Historical persistence is independently reconstructed forward prediction,
not the cached in-sample ``history_base``. No policy is tuned by this script.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
REVISION = PROJECT / "revision_20261009"
os.environ.setdefault("TEMP", str(REVISION / "temp"))
os.environ.setdefault("TMP", str(REVISION / "temp"))
os.environ.setdefault("JOBLIB_TEMP_FOLDER", str(REVISION / "temp"))
sys.path.insert(0, str(PROJECT / "scripts"))
import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.ensemble import RandomForestRegressor
from paper_context import RF_SPEC, select_training_indices

CFS_TO_CMS = 0.3048 ** 3  # International foot is exactly 0.3048 m.
LAGS = (6, 24, 72, 168)
DATA = PROJECT / "datasets/extended_hourly_2019_2025_v1.parquet"
NATIVE = PROJECT / "datasets/extended_native_2019_2025_v1.parquet"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean_json(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def write_json(path, value):
    path.write_text(json.dumps(clean_json(value), indent=2, ensure_ascii=False), encoding="utf-8")


def fraction(a, b):
    return float(a / b) if np.isfinite(b) and b > 0 else np.nan


def qualified(frame):
    y = frame.nox_at_time_mg_l.to_numpy(float)
    return (frame.nox_sample_reference_ok.fillna(False).to_numpy(bool)
            & frame.q_sample_reference_ok.fillna(False).to_numpy(bool)
            & np.isfinite(y) & (y >= 0)
            & frame.q_at_time_cms.notna().to_numpy())


def valid_reference(frame):
    return (frame.valid_hour.fillna(False).to_numpy(bool)
            & np.isfinite(frame.load_kg.to_numpy(float))
            & np.isfinite(frame.observed_volume_m3.to_numpy(float))
            & (frame.observed_volume_m3.to_numpy(float) >= 0))


def longest_true_run(mask):
    x = np.r_[False, np.asarray(mask, bool), False].astype(int)
    starts, stops = np.flatnonzero(np.diff(x) == 1), np.flatnonzero(np.diff(x) == -1)
    return int((stops - starts).max()) if len(starts) else 0


def load_runs(paths):
    metrics, events, manifests = [], [], []
    for name in paths:
        run = Path(name)
        if not run.is_absolute():
            run = PROJECT / "results/paper_runs" / run
        manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
        assert manifest.get("completed_at_utc"), f"Unfinished run: {run}"
        m = pd.read_csv(run / "metrics.csv", dtype={"site": str})
        e = pd.read_csv(run / "events.csv", dtype={"site": str})
        for x in (m, e):
            x["source_run"] = run.name
            x["source_run_path"] = str(run)
        metrics.append(m)
        events.append(e)
        manifests.append({"path": str(run), "manifest_sha256": digest(run / "run_manifest.json"),
                          "metrics_sha256": digest(run / "metrics.csv"),
                          "events_sha256": digest(run / "events.csv"),
                          "data_sha256": manifest.get("data_sha256")})
    return pd.concat(metrics, ignore_index=True), pd.concat(events, ignore_index=True), manifests


def native_volume_audit():
    """Stream native Q without concentration-dependent selection of its denominator."""
    columns = ["site", "time_utc", "q_cms", "q_numeric_valid", "q_reference_ok", "on_quarter_grid"]
    chunks = []
    for batch in pq.ParquetFile(NATIVE).iter_batches(batch_size=200000, columns=columns):
        n = batch.to_pandas()
        on = n.on_quarter_grid.fillna(False).to_numpy(bool)
        q = n.q_cms.to_numpy(float)
        numeric = on & np.isfinite(q) & (q >= 0) & n.q_numeric_valid.fillna(False).to_numpy(bool)
        qok = numeric & n.q_reference_ok.fillna(False).to_numpy(bool)
        d = pd.DataFrame({"site": n.site.astype(str), "year": n.time_utc.dt.year,
                          "native_q_observed_volume_m3": np.where(numeric, q * 900, 0),
                          "native_q_qualified_volume_m3": np.where(qok, q * 900, 0),
                          "native_q_observed_count": numeric.astype(int),
                          "native_q_qualified_count": qok.astype(int)})
        chunks.append(d.groupby(["site", "year"]).sum())
    return pd.concat(chunks).groupby(level=[0, 1]).sum().reset_index()


def site_year_context(hourly, native, memberships):
    rows = []
    names = {x["site"]: x for x in json.loads((PROJECT / "datasets/extended_station_metadata_v1.json").read_text())}
    for site, all_years in hourly.groupby("site", sort=True):
        for year, f in all_years.groupby(all_years.time_utc.dt.year, sort=True):
            hist = all_years.loc[(all_years.time_utc.dt.year >= year - 3)
                                & (all_years.time_utc.dt.year < year)]
            hq = hist.loc[hist.q_sample_reference_ok.fillna(False), "q_at_time_cms"].dropna()
            q90 = float(hq.quantile(.9)) if len(hq) else np.nan
            ok = valid_reference(f)
            load = f.load_kg.to_numpy(float)
            total = float(np.nansum(load[ok]))
            high = ok & (f.q_at_time_cms.to_numpy(float) >= q90)
            n_top = int(math.ceil(.1 * ok.sum()))
            top_sum = float(np.sort(load[ok])[-n_top:].sum()) if n_top else 0
            qvol = np.where(f.q_count.to_numpy(float) > 0,
                            f.q_cms.to_numpy(float) * f.q_count.to_numpy(float) * 900, 0)
            q_observed = float(np.nansum(qvol))
            reference_volume = float(f.loc[ok, "observed_volume_m3"].sum())
            paired_volume = float(f.observed_volume_m3.sum())
            paired = qualified(f)
            history_paired = qualified(hist) if len(hist) else np.zeros(0, bool)
            row = {"site": str(site), "year": int(year), "site_name": names[site]["name"],
                   "huc4_group": names[site]["huc4_group"], "hours": len(f),
                   "complete_reference_hours": int(ok.sum()), "hour_coverage": float(ok.mean()),
                   "exact_hour_joint_qualified_labels": int(paired.sum()),
                   "reference_load_kg": total, "reference_volume_m3": reference_volume,
                   "partial_and_complete_joint_volume_m3": paired_volume,
                   "all_numeric_observed_q_volume_m3": q_observed,
                   "reference_volume_fraction_observed_q": fraction(reference_volume, q_observed),
                   "paired_volume_fraction_observed_q": fraction(paired_volume, q_observed),
                   "q_quarter_grid_coverage": float(f.q_count.sum() / (len(f) * 4)),
                   "historical_q90_cms": q90, "historical_q_count": len(hq),
                   "high_q_reference_hours": int(high.sum()),
                   "high_q_reference_load_kg": float(np.nansum(load[high])),
                   "load_fraction_q_ge_historical_q90": fraction(np.nansum(load[high]), total) if len(hq) else np.nan,
                   "top10pct_reference_hour_count": n_top,
                   "top10pct_reference_load_kg": top_sum,
                   "top10pct_reference_load_fraction": fraction(top_sum, total),
                   "reference_nox_mean_mg_l": float(f.loc[paired, "nox_at_time_mg_l"].mean()),
                   "history_nox_mean_mg_l": float(hist.loc[history_paired, "nox_at_time_mg_l"].mean()) if len(hist) else np.nan,
                   "history_window_start_year": int(year - 3),
                   "available_before_target": False}
            rows.append(row)
    result = pd.DataFrame(rows).merge(native, on=["site", "year"], how="left", validate="one_to_one")
    for column in native.columns:
        if column not in ["site", "year"]:
            result[column] = result[column].fillna(0)  # No native rows means no observed support, not zero true flow.
    np.testing.assert_allclose(result.all_numeric_observed_q_volume_m3,
                               result.native_q_observed_volume_m3, rtol=1e-12, atol=1e-3)
    result["reference_volume_fraction_qualified_q"] = result.reference_volume_m3 / result.native_q_qualified_volume_m3
    result = result.merge(memberships, on=["site", "year"], how="left", validate="one_to_one")
    result["included_in_original_data_gate"] = result.stage.notna()
    return result


def event_context(hourly, events, site_year):
    baseline = events.loc[(events.policy == "no_new_labels") & (events.budget == 0) & (events["mode"] == "online")]
    identity = ["site", "year", "event_id"]
    # Outcomes repeated by seeds are not independent environmental observations.
    for field in ["hours", "coverage", "eligible", "reference_valid_window_load_kg", "q_peak_cms"]:
        assert baseline.groupby(identity)[field].nunique(dropna=False).max() <= 1, field
    baseline = baseline.sort_values("seed").drop_duplicates(identity)
    frames = {(s, int(y)): f.reset_index(drop=True) for (s, y), f in hourly.groupby(["site", hourly.time_utc.dt.year])}
    q90s = site_year.set_index(["site", "year"]).historical_q90_cms
    rows = []
    for e in baseline.itertuples(index=False):
        start, end = pd.Timestamp(e.start_time), pd.Timestamp(e.end_time)
        f = frames[(e.site, e.year)]
        f = f.loc[(f.time_utc >= start) & (f.time_utc < end)].reset_index(drop=True)
        assert len(f) == e.hours
        ok = valid_reference(f)
        load = f.load_kg.to_numpy(float)
        volume = f.observed_volume_m3.to_numpy(float)
        q = f.q_at_time_cms.to_numpy(float)
        load_sum = float(np.nansum(load[ok]))
        np.testing.assert_allclose(load_sum, e.reference_valid_window_load_kg, rtol=1e-10, atol=1e-5)
        np.testing.assert_allclose(ok.mean(), e.coverage, atol=1e-12)
        peak = int(np.nanargmax(q))
        split = np.array_split(np.arange(len(f)), 3)
        missing = ~ok
        edge = np.zeros(len(f), bool)
        edge[:min(24, len(f))] = True
        edge[max(0, len(f)-24):] = True
        any_edge, any_interior = bool(missing[edge].any()), bool(missing[~edge].any())
        missing_position = ("both_edges_and_interior" if any_edge and any_interior else
                            "first_or_last_24h" if any_edge else "interior_only" if any_interior else "none")
        month = start.month
        season = "DJF" if month in [12, 1, 2] else "MAM" if month in [3, 4, 5] else "JJA" if month in [6, 7, 8] else "SON"
        q_observed = float(np.nansum(np.where(f.q_count > 0, f.q_cms * f.q_count * 900, 0)))
        reason = []
        if e.coverage < .95:
            reason.append("reference_coverage_below_0.95")
        if e.boundary_uncertain:
            reason.append("uncertain_discharge_boundary")
        if e.eligible and load_sum <= 1e-8:
            reason.append("zero_reference_load")
        row = {"site": e.site, "year": e.year, "stage": e.stage, "source_run": e.source_run,
               "event_id": e.event_id, "start_time": str(start), "end_time_exclusive": str(end),
               "hours": len(f), "reference_hours": int(ok.sum()), "reference_hour_coverage": float(ok.mean()),
               "eligible": bool(e.eligible), "scorable": bool(e.eligible and load_sum > 1e-8),
               "excluded_reason": ";".join(reason) or "retained", "boundary_uncertain": bool(e.boundary_uncertain),
               "start_month": month, "start_season": season,
               "q_peak_cms": float(np.nanmax(q)), "q_peak_time": str(f.iloc[peak].time_utc),
               "q_peak_over_historical_q90": fraction(np.nanmax(q), q90s.loc[(e.site, e.year)]),
               "q_peak_hour_reference_valid": bool(ok[peak]),
               "reference_load_kg": load_sum, "reference_volume_m3": float(np.nansum(volume[ok])),
               "all_observed_q_volume_m3": q_observed,
               "reference_volume_fraction_observed_q": fraction(np.nansum(volume[ok]), q_observed),
               "missing_reference_hours": int(missing.sum()), "longest_missing_reference_run_hours": longest_true_run(missing),
               "missing_reference_position": missing_position,
               "missing_reference_hours_before_or_at_peak": int(missing[:peak+1].sum()),
               "missing_reference_hours_after_peak": int(missing[peak+1:].sum()),
               "missing_reference_hours_first24": int(missing[:24].sum()),
               "missing_reference_hours_last24": int(missing[-24:].sum()),
               "available_before_target": False}
        for j, indices in enumerate(split, 1):
            row[f"missing_reference_hours_third{j}"] = int(missing[indices].sum())
            row[f"hours_third{j}"] = len(indices)
        for lag in [24, 72]:
            early = np.arange(len(f)) < lag
            early_load = float(np.nansum(load[ok & early]))
            row[f"load_occurred_first{lag}h_kg"] = early_load
            row[f"load_fraction_occurred_first{lag}h"] = fraction(early_load, load_sum)
            row[f"first{lag}h_reference_coverage"] = float(ok[early].mean())
        rows.append(row)
    return pd.DataFrame(rows)


def forward_context(memberships, cache_dir, seed, out):
    summaries, lag_rows, residual_series = [], [], []
    for item in memberships.sort_values(["site", "year"]).itertuples(index=False):
        p = cache_dir / f"{item.site}_{item.year}_{seed}.joblib"
        if not p.exists():
            raise FileNotFoundError(p)
        ctx = joblib.load(p)
        assert ctx["status"] == "ready"
        history = ctx["history"]
        target = ctx["target"]
        hist_years = history.time_utc.dt.year.to_numpy()
        ok = qualified(history)
        calyear = int(ctx["audit"]["calibration_year"])
        train = ok & (hist_years < calyear)
        cal = hist_years == calyear
        train_ix = select_training_indices(train, seed)
        model = RandomForestRegressor(**RF_SPEC, random_state=seed)
        y = history.nox_at_time_mg_l.to_numpy(float)
        model.fit(ctx["history_features"].iloc[train_ix], y[train_ix])
        pred = model.predict(ctx["history_features"].loc[cal])
        cf = history.loc[cal].reset_index(drop=True)
        good = ok[cal]
        residual = np.where(good, cf.nox_at_time_mg_l.to_numpy(float) - pred, np.nan)
        # Reproduce old forward calibration audit using its sampled 4,000 labels.
        cal_ix = select_training_indices(ok & cal, seed, max_points=4000)
        sample_pred = model.predict(ctx["history_features"].iloc[cal_ix])
        sample_residual = y[cal_ix] - sample_pred
        np.testing.assert_allclose(sample_residual.mean(), ctx["audit"]["calibration_bias"], rtol=1e-8, atol=1e-10)
        np.testing.assert_allclose(max(np.mean(sample_residual**2), ctx["audit"]["noise_floor"]),
                                   ctx["audit"]["noise_variance_forward_mse"], rtol=1e-8, atol=1e-10)
        assert history.time_utc.max() < target.time_utc.min()
        assert cf.time_utc.diff().iloc[1:].eq(pd.Timedelta(hours=1)).all()
        target_ok = qualified(target)
        tr = target.nox_at_time_mg_l.to_numpy(float)[target_ok] - np.asarray(ctx["target_base"])[target_ok]
        rr = residual[good]
        summary = {"site": item.site, "year": item.year, "stage": item.stage, "seed": seed,
                   "calibration_year": calyear, "training_start": str(history.loc[train].time_utc.min()),
                   "training_end": str(history.loc[train].time_utc.max()),
                   "calibration_start": str(cf.time_utc.min()), "calibration_end": str(cf.time_utc.max()),
                   "calibration_qualified_hours": int(good.sum()), "training_labels_used": len(train_ix),
                   "longest_contiguous_qualified_calibration_hours": longest_true_run(good),
                   "historical_forward_residual_bias_mg_l": float(rr.mean()),
                   "historical_forward_residual_rmse_mg_l": float(np.sqrt(np.mean(rr**2))),
                   "historical_forward_residual_mae_mg_l": float(np.mean(np.abs(rr))),
                   "target_qualified_hours": int(target_ok.sum()),
                   "target_zero_label_residual_bias_mg_l": float(tr.mean()),
                   "target_zero_label_residual_rmse_mg_l": float(np.sqrt(np.mean(tr**2))),
                   "target_zero_label_residual_mae_mg_l": float(np.mean(np.abs(tr))),
                   "target_minus_historical_forward_bias_mg_l": float(tr.mean() - rr.mean()),
                   "target_over_historical_forward_rmse": fraction(np.sqrt(np.mean(tr**2)), np.sqrt(np.mean(rr**2))),
                   "calibration_nox_mean_mg_l": float(cf.loc[good, "nox_at_time_mg_l"].mean()),
                   "target_nox_mean_mg_l": float(target.loc[target_ok, "nox_at_time_mg_l"].mean()),
                   "forward_audit_reproduced": True, "historical_characteristics_available_before_target": True,
                   "target_drift_characteristics_available_before_target": False, "context_sha256": digest(p)}
        summaries.append(summary)
        bad_prefix = np.r_[0, np.cumsum(~good)]
        for lag in LAGS:
            endpoint = good[:-lag] & good[lag:]
            continuous = (bad_prefix[lag+1:] - bad_prefix[:-(lag+1)]) == 0
            assert len(continuous) == len(good) - lag
            assert np.all(~continuous | endpoint)
            for kind, keep in [("continuous_all_hours_qualified", continuous), ("endpoints_only_sensitivity", endpoint)]:
                a, b = residual[:-lag][keep], residual[lag:][keep]
                correlation = float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 and np.std(a) > 0 and np.std(b) > 0 else np.nan
                lag_rows.append({"site": item.site, "year": item.year, "stage": item.stage, "seed": seed,
                                 "calibration_year": calyear, "lag_hours": lag, "pair_support": kind,
                                 "pairs": len(a), "pearson_residual_autocorrelation": correlation,
                                 "same_sign_fraction": float(np.mean(np.sign(a) == np.sign(b))) if len(a) else np.nan,
                                 "residual_change_rmse_mg_l": float(np.sqrt(np.mean((b-a)**2))) if len(a) else np.nan,
                                 "available_before_target": True})
        residual_series.append(pd.DataFrame({"site": item.site, "target_year": item.year,
                                            "calibration_year": calyear, "seed": seed, "time_utc": cf.time_utc,
                                            "qualified": good, "forward_prediction_mg_l": pred,
                                            "reference_mg_l": cf.nox_at_time_mg_l.where(good), "residual_mg_l": residual}))
        print(f"forward {item.site} {item.year} calibration={calyear} labels={good.sum()}", flush=True)
    pd.concat(residual_series, ignore_index=True).to_parquet(out / "context_historical_forward_residuals.parquet", index=False)
    return pd.DataFrame(summaries), pd.DataFrame(lag_rows)


def baseline_context(metrics):
    base = metrics.loc[(metrics.policy == "no_new_labels") & (metrics.budget == 0) & (metrics["mode"] == "online")].copy()
    keys = ["site", "year", "stage", "source_run"]
    columns = ["event_mean_absolute_relative_error", "event_median_absolute_relative_error",
               "valid_window_relative_bias", "concentration_mae_mg_l", "hourly_load_normalized_absolute_error",
               "reference_valid_window_load_kg", "predicted_valid_window_load_kg", "events_all", "events_eligible",
               "valid_hours", "hour_coverage"]
    grouped = base.groupby(keys, as_index=False)[columns].mean()
    grouped["seeds"] = base.groupby(keys).seed.nunique().to_numpy()
    grouped["aggregation"] = "within_site_year_arithmetic_mean_over_model_seeds"
    grouped["zero_label_signed_load_error_kg"] = grouped.predicted_valid_window_load_kg - grouped.reference_valid_window_load_kg
    return grouped


def independent_unit_example(hourly):
    site, year = "02035000", 2025
    f = hourly.loc[(hourly.site == site) & (hourly.time_utc.dt.year == year)]
    h = f.loc[valid_reference(f)].iloc[0]
    times = pd.date_range(h.time_utc, periods=4, freq="15min")
    n = pd.read_parquet(NATIVE, filters=[("site", "==", site)],
                        columns=["site", "time_utc", "q_cms", "nox_mg_l", "joint_reference_ok"])
    n = n.loc[n.time_utc.isin(times)].set_index("time_utc").loc[times]
    assert n.joint_reference_ok.all() and len(n) == 4
    prep = json.loads((PROJECT / "datasets/extended_preparation_manifest_v1.json").read_text())
    records = prep["used_raw_records"]
    records = [r for r in records if str(r["site"]) == site and int(r["year"]) in [year-1, year]]
    found_q, found_c, source_units, sources = {}, {}, [], []
    for rec in records:
        p = Path(rec["path"])
        with gzip.open(p, "rt", encoding="utf-8") as z:
            payload = json.load(z)
        sources.append({"path": str(p), "sha256": digest(p)})
        assert sources[-1]["sha256"] == rec["sha256"]
        for series in payload["value"]["timeSeries"]:
            code = series["variable"]["variableCode"][0]["value"]
            if code not in ["00060", "99133"]:
                continue
            expected_unit = "ft3/s" if code == "00060" else "mg/l as N"
            assert series["variable"]["unit"]["unitCode"] == expected_unit
            source_units.append({"parameter": code, "unit": series["variable"]["unit"]})
            dest = found_q if code == "00060" else found_c
            for block in series["values"]:
                for v in block["value"]:
                    t = pd.Timestamp(v["dateTime"]).tz_convert("UTC")
                    if t in times:
                        value = float(v["value"])
                        if t in dest:
                            assert value == dest[t]
                        dest[t] = value
    assert set(found_q) == set(times) and set(found_c) == set(times)
    rows = []
    for t in times:
        q_cfs, c = found_q[t], found_c[t]
        q_cms = q_cfs * CFS_TO_CMS
        volume = q_cms * 900
        load = volume * c * .001
        np.testing.assert_allclose(q_cms, n.loc[t, "q_cms"], rtol=1e-14)
        np.testing.assert_allclose(c, n.loc[t, "nox_mg_l"], rtol=1e-14)
        rows.append({"time_utc": str(t), "q_cfs_raw": q_cfs, "nox_mg_l_as_N_raw": c,
                     "q_cms_independent": q_cms, "quarter_volume_m3": volume, "quarter_load_kg_N": load})
    np.testing.assert_allclose(sum(r["quarter_volume_m3"] for r in rows), h.observed_volume_m3, rtol=1e-13)
    np.testing.assert_allclose(sum(r["quarter_load_kg_N"] for r in rows), h.load_kg, rtol=1e-13)
    return {"status": "PASS", "site": site, "hour_start_utc": str(h.time_utc),
            "source_files": sources, "source_units": source_units, "quarter_records": rows,
            "independent_cfs_to_cms_factor": CFS_TO_CMS,
            "dimensional_derivation": "(ft^3/s)*(0.3048 m/ft)^3*(900 s)*(mg N/L)*(1000 L/m^3)*(1 kg/10^6 mg)",
            "hour_volume_m3": float(h.observed_volume_m3), "hour_load_kg_N": float(h.load_kg),
            "constant_example": {"q_cfs": 100, "concentration_mg_l_N": 2,
                                 "q_cms": 100*CFS_TO_CMS, "one_hour_load_kg_N": 100*CFS_TO_CMS*3600*2*.001}}


def select_and_export_cases(hourly, events, run, out, budget=96, seed=41):
    """Declare the extrema/median rule in manifest before reading outcomes."""
    e = events.loc[(events.source_run == run.name) & (events.seed == seed)
                   & (events.budget == budget) & (events["mode"] == "online")
                   & events.eligible & events.policy.isin(["value", "flow_trigger"])]
    keys = ["site", "year", "event_id"]
    paired = e.pivot(index=keys, columns="policy", values="relative_error").dropna().reset_index()
    paired["delta_absRE_value_minus_flow"] = paired.value.abs() - paired.flow_trigger.abs()
    paired = paired.sort_values(keys).reset_index(drop=True)
    assert len(paired) >= 3
    delta = paired.delta_absRE_value_minus_flow
    chosen = [("largest_improvement", delta.idxmin()), ("largest_harm", delta.idxmax())]
    candidates = (delta-delta.median()).abs().sort_values(kind="stable")
    chosen.append(("nearest_median_difference", next(i for i in candidates.index if i not in [x[1] for x in chosen])))
    attempt_file = run / "attempts.csv" if (run / "attempts.csv").exists() else run / "sampling_attempts.csv"
    attempts = pd.read_csv(attempt_file, dtype={"site": str})
    attempts["sample_time"] = pd.to_datetime(attempts.sample_time, utc=True)
    attempts["arrival_time"] = pd.to_datetime(attempts.arrival_time, utc=True)
    selections, all_hours, all_attempts = [], [], []
    for label, idx in chosen:
        s = paired.loc[idx]
        source_event = e.loc[(e.site == s.site) & (e.year == s.year) & (e.event_id == s.event_id)].iloc[0]
        start, end = pd.Timestamp(source_event.start_time), pd.Timestamp(source_event.end_time)
        left, right = start-pd.Timedelta(hours=48), end+pd.Timedelta(hours=72)
        f = hourly.loc[(hourly.site == s.site) & (hourly.time_utc >= left)
                       & (hourly.time_utc < right) & (hourly.time_utc.dt.year == s.year)].copy().reset_index(drop=True)
        case_id = f"{label}_{s.site}_{int(s.year)}_{int(s.event_id)}"
        f["case_id"] = case_id
        f["within_event"] = (f.time_utc >= start) & (f.time_utc < end)
        f["reference_point_mg_l"] = f.nox_at_time_mg_l.where(qualified(f))
        ok = valid_reference(f)
        f["reference_hour_load_kg"] = f.load_kg.where(ok)
        in_support = ok & f.within_event.to_numpy()
        f["cumulative_event_reference_load_kg"] = np.where(in_support, f.load_kg, 0).cumsum()
        predictions = pd.read_parquet(run / "predictions.parquet", filters=[("site", "==", str(s.site)),
                                      ("year", "==", int(s.year)), ("seed", "==", seed), ("mode", "==", "online")])
        for policy in ["uniform", "flow_trigger", "deadline_only", "value"]:
            pred = predictions.loc[(predictions.policy == policy) & (predictions.budget == budget)]
            assert not pred.time_utc.duplicated().any()
            values = f.time_utc.map(pred.set_index("time_utc").prediction)
            assert values.notna().all()
            f[f"prediction_{policy}_mg_l"] = values
            f[f"predicted_hour_load_{policy}_kg"] = (values * f.observed_volume_m3 * .001).where(ok)
            f[f"cumulative_event_predicted_load_{policy}_kg"] = np.where(in_support, values*f.observed_volume_m3*.001, 0).cumsum()
            expected = events.loc[(events.source_run == run.name) & (events.site == s.site)
                                  & (events.year == s.year) & (events.event_id == s.event_id)
                                  & (events.seed == seed) & (events.budget == budget)
                                  & (events.policy == policy) & (events["mode"] == "online")].iloc[0]
            np.testing.assert_allclose(f.loc[in_support, f"predicted_hour_load_{policy}_kg"].sum(),
                                       expected.predicted_valid_window_load_kg, rtol=1e-10, atol=1e-5)
            a = attempts.loc[(attempts.site == s.site) & (attempts.year == s.year) & (attempts.seed == seed)
                             & (attempts.budget == budget) & (attempts.policy == policy)
                             & (((attempts.sample_time >= left) & (attempts.sample_time < right))
                                | ((attempts.arrival_time >= left) & (attempts.arrival_time < right)))].copy()
            a["case_id"] = case_id
            all_attempts.append(a)
            for timefield, suffix in [("sample_time", "samples"), ("arrival_time", "arrivals")]:
                f[f"{policy}_{suffix}"] = f.time_utc.map(a.groupby(timefield).size()).fillna(0).astype(int)
            f[f"{policy}_usable_arrivals"] = f.time_utc.map(a.loc[a.label_success].groupby("arrival_time").size()).fillna(0).astype(int)
            f[f"{policy}_fallback_samples"] = f.time_utc.map(a.loc[a.reason == "block_deadline"].groupby("sample_time").size()).fillna(0).astype(int)
        base = predictions.drop_duplicates("time_utc").set_index("time_utc").base_prediction
        f["zero_label_prediction_mg_l"] = f.time_utc.map(base)
        f["cumulative_event_predicted_load_zero_labels_kg"] = np.where(in_support, f.zero_label_prediction_mg_l*f.observed_volume_m3*.001, 0).cumsum()
        keep = ["case_id", "site", "time_utc", "within_event", "valid_hour", "q_at_time_cms", "reference_point_mg_l",
                "observed_volume_m3", "reference_hour_load_kg", "cumulative_event_reference_load_kg"]
        keep += [c for c in f.columns if c.startswith(("prediction_", "predicted_hour_", "cumulative_event_predicted_", "zero_label_"))
                 or c.endswith(("_samples", "_arrivals"))]
        all_hours.append(f[keep])
        selections.append({"case_id": case_id, "selection": label, "site": s.site, "year": int(s.year),
                           "event_id": int(s.event_id), "seed": seed, "budget": budget,
                           "delta_absRE_value_minus_flow": float(s.delta_absRE_value_minus_flow),
                           "value_relative_error": float(s.value), "flow_relative_error": float(s.flow_trigger),
                           "start_time": str(start), "end_time_exclusive": str(end),
                           "source_run": run.name,
                           "status": "revised_post_result_closed_loop" if "revision_20261009" in str(run) else "old_frozen_run_provisional_pending_revision_cases"})
    pd.DataFrame(selections).to_csv(out / "context_case_selection.csv", index=False)
    paired.to_csv(out / "context_case_selection_population.csv", index=False)
    pd.concat(all_hours, ignore_index=True).to_csv(out / "context_case_hourly.csv", index=False)
    pd.concat(all_attempts, ignore_index=True).to_csv(out / "context_case_attempts.csv", index=False)
    return selections


def export_policy_event_timing(hourly, events, run, out):
    """Actual usable arrivals are separate from the fixed event-onset delay shares."""
    p = run / "attempts.csv" if (run / "attempts.csv").exists() else run / "sampling_attempts.csv"
    attempts = pd.read_csv(p, dtype={"site": str})
    attempts["sample_time"] = pd.to_datetime(attempts.sample_time, utc=True)
    attempts["arrival_time"] = pd.to_datetime(attempts.arrival_time, utc=True)
    events = events.loc[events.eligible & (events["mode"] == "online") & (events.budget > 0)]
    keys = ["site", "year", "seed", "policy", "budget", "delay_hours"]
    if "scenario" in attempts:
        keys.append("scenario")
    groups = {k: g for k, g in attempts.groupby(keys)}
    frames = {(s, int(y)): f for (s, y), f in hourly.groupby(["site", hourly.time_utc.dt.year])}
    rows = []
    for e in events.itertuples(index=False):
        a = groups[tuple(getattr(e, k) for k in keys)]
        start, end = pd.Timestamp(e.start_time), pd.Timestamp(e.end_time)
        f = frames[(e.site, e.year)]
        f = f.loc[(f.time_utc >= start) & (f.time_utc < end)]
        ok = valid_reference(f)
        total = float(f.loc[ok, "load_kg"].sum())
        returns = a.loc[a.label_success & (a.arrival_time >= start) & (a.arrival_time < end)]
        first = returns.arrival_time.min() if len(returns) else pd.NaT
        before = np.ones(len(f), bool) if pd.isna(first) else f.time_utc.lt(first).to_numpy()
        earlier = a.loc[a.label_success & (a.arrival_time < start)]
        row = {k: getattr(e, k) for k in keys}
        row.update(source_run=run.name, event_id=e.event_id, start_time=str(start), end_time_exclusive=str(end),
                   event_hours=len(f), reference_load_kg=total,
                   first_usable_arrival_time=None if pd.isna(first) else str(first),
                   first_usable_arrival_hours_since_onset=np.nan if pd.isna(first) else (first-start).total_seconds()/3600,
                   no_usable_arrival_within_event=not len(returns), usable_arrivals_within_event=len(returns),
                   reference_load_before_first_usable_arrival_kg=float(f.loc[ok & before, "load_kg"].sum()),
                   fraction_load_before_first_usable_arrival=fraction(f.loc[ok & before, "load_kg"].sum(), total),
                   latest_pre_event_usable_arrival=None if not len(earlier) else str(earlier.arrival_time.max()),
                   post_result_timing_diagnostic_not_error_bound=True)
        rows.append(row)
    result = pd.DataFrame(rows)
    result.to_csv(out / "context_policy_event_timing.csv", index=False)
    return result


def summarize_actual_arrivals(out):
    source = out / "context_policy_event_timing.csv"
    raw = pd.read_csv(source, dtype={"site": str})
    settings = ["source_run", "policy", "budget", "delay_hours", "scenario"]
    values = ["fraction_load_before_first_usable_arrival", "no_usable_arrival_within_event"]
    event = raw.groupby(settings+["site", "year", "event_id"], as_index=False)[values].mean()
    counts = raw.groupby(settings+["site", "year", "event_id"]).seed.nunique()
    event["seeds_averaged"] = counts.to_numpy()
    event.to_csv(out / "context_arrival_event_seedmeans.csv", index=False)
    site_year = event.groupby(settings+["site", "year"], as_index=False)[values].mean()
    station = site_year.groupby(settings+["site"], as_index=False)[values].mean()
    station.to_csv(out / "context_arrival_station_means.csv", index=False)
    summary = station.groupby(settings, as_index=False)[values].mean()
    nsites = station.groupby(settings).site.nunique().rename("sites")
    nevents = event.groupby(settings).size().rename("unique_events")
    summary = summary.merge(nsites.reset_index(), on=settings).merge(nevents.reset_index(), on=settings)
    event_summary = event.groupby(settings, as_index=False)[values].mean().rename(columns={c: "event_equal_mean_"+c for c in values})
    summary = summary.merge(event_summary, on=settings)
    summary["aggregation"] = "seed_mean_within_event_then_event_mean_within_site_year_then_year_mean_within_site_then_equal_site_mean"
    summary.to_csv(out / "context_arrival_summary.csv", index=False)
    write_json(out / "context_arrival_summary_manifest.json", {
        "source_sha256": digest(source), "script_sha256": digest(Path(__file__)),
        "primary_aggregation": "Seed means within each event; event means within station-year; available-year means within station; equal station mean.",
        "event_scatter": "Use context_arrival_event_seedmeans.csv, one row per physical event/policy/budget, not the seed-repeated raw table.",
        "no_arrival": "This value is a fraction of seeds at an event after averaging, not a binary event label. No new result during event does not mean no earlier useful result.",
        "scope": "Descriptive temporal revised replay. No new tests, p-values, CIs, or grouping.",
        "outputs": {p.name: {"sha256": digest(p), "rows": len(pd.read_csv(p))} for p in out.glob("context_arrival_*.csv")}})
    manifest_path = out / "context_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["script_sha256"] = digest(Path(__file__))
        for path in out.glob("context_arrival_*"):
            manifest["outputs"][path.name] = {"bytes": path.stat().st_size, "sha256": digest(path)}
        write_json(manifest_path, manifest)
    return summary


def summarize(site_year, ev, persistence, base):
    summaries = {}
    groups = []
    for stage in sorted(ev.stage.unique()):
        e = ev.loc[ev.stage == stage]
        s = site_year.loc[site_year.stage == stage]
        retained = e.loc[e.scorable]
        summary = {"station_years": len(s), "sites": s.site.nunique(), "events_all": len(e),
                   "events_eligible_positive_load": len(retained), "event_sites": retained.site.nunique(),
                   "median_top10pct_reference_load_fraction": s.top10pct_reference_load_fraction.median(),
                   "median_load_fraction_q_ge_historical_q90": s.load_fraction_q_ge_historical_q90.median(),
                   "median_reference_volume_fraction_observed_q": s.reference_volume_fraction_observed_q.median(),
                   "pooled_reference_volume_fraction_observed_q": fraction(s.reference_volume_m3.sum(), s.all_numeric_observed_q_volume_m3.sum()),
                   "equal_event_median_load_fraction_first24h": retained.load_fraction_occurred_first24h.median(),
                   "equal_event_median_load_fraction_first72h": retained.load_fraction_occurred_first72h.median(),
                   "load_weighted_fraction_first24h": fraction(retained.load_occurred_first24h_kg.sum(), retained.reference_load_kg.sum()),
                   "load_weighted_fraction_first72h": fraction(retained.load_occurred_first72h_kg.sum(), retained.reference_load_kg.sum())}
        summaries[stage] = summary
        for kept, g in e.groupby("scorable"):
            groups.append({"stage": stage, "scorable": bool(kept), "events": len(g), "sites": g.site.nunique(),
                           "median_q_peak_cms": g.q_peak_cms.median(), "median_duration_hours": g.hours.median(),
                           "median_reference_hour_coverage": g.reference_hour_coverage.median(),
                           "median_reference_volume_fraction_observed_q": g.reference_volume_fraction_observed_q.median(),
                           "q_peak_reference_valid_fraction": g.q_peak_hour_reference_valid.mean(),
                           "DJF_events": (g.start_season == "DJF").sum(), "MAM_events": (g.start_season == "MAM").sum(),
                           "JJA_events": (g.start_season == "JJA").sum(), "SON_events": (g.start_season == "SON").sum()})
    return summaries, pd.DataFrame(groups)


def export_plot_contract(out, site_year, ev, persistence, base):
    """Long tables retain sampling units; figures must not count seeds as sites."""
    sy = site_year.loc[site_year.included_in_original_data_gate]
    site_values = ["top10pct_reference_load_fraction", "load_fraction_q_ge_historical_q90",
                   "reference_volume_fraction_observed_q", "reference_volume_fraction_qualified_q", "hour_coverage"]
    site_long = sy.melt(id_vars=["site", "year", "stage", "huc4_group"], value_vars=site_values,
                        var_name="metric", value_name="value")
    site_long["unit_of_replication"] = "station_year_descriptive"
    site_long.to_csv(out / "context_plot_site_year_long.csv", index=False)
    event_values = ["hours", "q_peak_cms", "reference_hour_coverage", "reference_volume_fraction_observed_q",
                    "load_fraction_occurred_first24h", "load_fraction_occurred_first72h", "longest_missing_reference_run_hours"]
    event_long = ev.melt(id_vars=["site", "year", "stage", "event_id", "scorable", "start_season"], value_vars=event_values,
                         var_name="metric", value_name="value")
    event_long["unit_of_replication"] = "event_nested_in_station"
    event_long.to_csv(out / "context_plot_event_long.csv", index=False)
    baseline_values = ["event_mean_absolute_relative_error", "valid_window_relative_bias", "concentration_mae_mg_l",
                       "hourly_load_normalized_absolute_error", "zero_label_signed_load_error_kg"]
    base.melt(id_vars=["site", "year", "stage", "seeds"], value_vars=baseline_values,
              var_name="metric", value_name="value").to_csv(out / "context_plot_zero_label_long.csv", index=False)
    definitions = {
        "top10pct_reference_load_fraction": "Sum of the largest ceil(0.10*N) complete-hour observed loads divided by all N complete-hour observed loads in that station/calendar year. No imputation; ties do not expand the selected count.",
        "load_fraction_q_ge_historical_q90": "Complete-hour observed load at instants whose exact-hour Q>=90th percentile of approved nonestimated uncensored Q from the preceding three calendar years, divided by complete-hour observed load. Hourly concentration labels are not used in the historical threshold.",
        "reference_volume_fraction_observed_q": "Sum of Q*900 on all four joint-qualified quarters of complete reference hours divided by sum of Q*900 on every numeric finite nonnegative observed quarter-grid Q, including provisional/estimated Q. Does not cover unobserved Q intervals.",
        "reference_volume_fraction_qualified_q": "Same numerator; denominator uses only Q_reference_ok quarter-grid Q and is independent of NOx availability.",
        "load_fraction_occurred_first24h": "Within-event complete-hour observed load with hour start < event_start+24 h divided by complete-hour observed load of that event; interval capped at event end. Timing coverage, not unavoidable forecast error or the actual sampling schedule.",
        "load_fraction_occurred_first72h": "Same definition at 72 h. A sample hypothetically taken at event onset would arrive at the cutoff; no claim is made that the policies sampled at onset.",
        "pearson_residual_autocorrelation": "Pearson correlation of independent forward historical residuals at exact lags 6/24/72/168 h. Primary support requires every intervening hour plus both endpoints to have joint-qualified labels. Endpoints-only support is a missingness sensitivity. No significance testing or optimal memory estimation.",
        "target_minus_historical_forward_bias_mg_l": "Post hoc difference in concentration residual means: target year with final historical RF minus latest qualifying historical year predicted from earlier years. Different fitted RFs and selected observed support prevent identifying pure environmental concept drift.",
        "q_peak_hour_reference_valid": "Whether the first exact-hour maximum Q within the detected event is a complete reference hour; a valid event can still miss up to 5% of its hours.",
        "missing_reference_position": "Invalid complete-reference hours in first or last24h are edge gaps; remaining hours are interior. Edges overlap in events shorter than48h. For exact chronology use thirds/counts and timestamps.",
        "event_endpoint": "Event end_time_exclusive is first hour after final high-Q hour; bridging permits24 lower-Q hours and disallows any missing exact-hour Q. Minimum span12h. Retention requires>=95% complete references and24h fully observed Q on each outer boundary.",
        "context_zero_label_station_year": "Original no_new_labels metrics averaged over seeds inside each station/year. Event means already average eligible positive-reference-load events; subsequent station summaries must average years then stations, not pool events.",
    }
    write_json(out / "context_variable_definitions.json", definitions)
    write_json(out / "context_figure_source_manifest.json", {
        "identity": "post_review_context_figures_not_confirmatory_tests",
        "source_files": ["context_plot_site_year_long.csv", "context_plot_event_long.csv", "context_residual_persistence.csv", "context_plot_zero_label_long.csv"],
        "station_year_selection": "All original data-gate included station years, no performance filtering; explicit stage column.",
        "event_selection": "All unique detected events retained for missingness comparison. Timing shares should use scorable=True only; all excluded events remain in the file.",
        "persistence_selection": "One seed(41) per original included station/year; all four lags and both support rules reported. Historical calibration audits exactly reproduced.",
        "grouping": "Temporal2025, external2023/24, and development2023/24 kept separate. Nearby stations and repeated years are not independent replications.",
        "distributions": "Raw descriptive points/medians only; no nine-station fitted mechanism model and no inferred optimal lag.",
        "case_state": "Await revised closed-loop results; old-run cases are not used as final figure inputs."})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="+", default=["development_full_v1", "external_main_v1", "temporal_main_v1"])
    parser.add_argument("--history-seed", type=int, default=41)
    parser.add_argument("--case-run", default="temporal_main_v1")
    parser.add_argument("--case-budget", type=int, default=96)
    parser.add_argument("--skip-forward", action="store_true", help="Reuse this script's existing context_forward files only")
    parser.add_argument("--skip-cases", action="store_true", help="Wait for revised run before case selection")
    parser.add_argument("--cases-only", action="store_true", help="Export cases and actual arrival timing from completed --case-run only")
    parser.add_argument("--arrival-summary-only", action="store_true", help="Aggregate completed actual-arrival table with equal-site weighting")
    args = parser.parse_args()
    start = time.perf_counter()
    out = REVISION / "results"
    out.mkdir(parents=True, exist_ok=True)
    if args.arrival_summary_only:
        print(summarize_actual_arrivals(out).to_string(index=False), flush=True)
        return
    if args.cases_only:
        run = Path(args.case_run)
        if not run.is_absolute():
            run = PROJECT / "results/paper_runs" / run
        _, case_events, case_sources = load_runs([str(run)])
        hourly = pd.read_parquet(DATA)
        hourly["site"] = hourly.site.astype(str)
        cases = select_and_export_cases(hourly, case_events, run, out, args.case_budget, args.history_seed)
        timing = export_policy_event_timing(hourly, case_events, run, out)
        write_json(out / "context_case_manifest.json", {"status": "complete", "elapsed_seconds": time.perf_counter()-start,
                   "analysis_identity": "post_result_revised_closed_loop_illustration", "source": case_sources,
                   "data_sha256": digest(DATA), "script_sha256": digest(Path(__file__)), "case_selection": cases,
                   "selection_rule": "At budget96 seed41 online: extrema and nearest median of abs(value RE)-abs(flow RE) among all jointly scorable temporal events; stable ties by site/year/event; distinct cases.",
                   "case_prediction_loads_independently_matched_event_records": True,
                   "timing_rows": len(timing), "timing_definition": "Within-event common-support load strictly before the first actual usable arrival from any acquired sample, including pre-event samples. If no usable arrival occurs during the event, fraction=1 and an explicit no-arrival flag is set. Previous useful labels and historical predictions still exist; not an error lower bound.",
                   "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(out.glob("context_case*.csv"))}
                   | {"actual_arrival_timing_sha256": digest(out / "context_policy_event_timing.csv")}})
        summary_path = out / "context_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary.update(case_selection=cases, case_source_run=run.name, case_status="complete_revised_closed_loop")
            write_json(summary_path, summary)
        figure_path = out / "context_figure_source_manifest.json"
        if figure_path.exists():
            figure_manifest = json.loads(figure_path.read_text(encoding="utf-8"))
            figure_manifest.update(case_state="Complete; revised closed-loop run, explicitly post-result",
                                   case_source_run=run.name, case_manifest="context_case_manifest.json",
                                   case_source_files=["context_case_selection.csv", "context_case_selection_population.csv",
                                                      "context_case_hourly.csv", "context_case_attempts.csv", "context_policy_event_timing.csv"])
            write_json(figure_path, figure_manifest)
        manifest_path = out / "context_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update(script_sha256=digest(Path(__file__)), case_completion_source=case_sources,
                            case_status="complete_revised_closed_loop",
                            outputs={p.name: {"bytes": p.stat().st_size, "sha256": digest(p)}
                                     for p in sorted(out.glob("context_*")) if p.name != "context_manifest.json"})
            write_json(manifest_path, manifest)
        print(json.dumps(clean_json(cases), ensure_ascii=False, indent=2), flush=True)
        return
    plan = {"analysis_identity": "post_review_descriptive_diagnostics_20261009", "history_seed": args.history_seed,
            "residual_lags_hours": LAGS, "no_target_labels_in_history_forward_fit": True,
            "case_rule": "Among temporal run eligible events at budget96 seed41 online, rank abs(value RE)-abs(flow RE); show minimum, maximum and nearest median, ties by site/year/event. Cases are illustrative extrema, not independent confirmation.",
            "case_run": args.case_run, "case_budget": args.case_budget,
            "do_not_interpret_as": ["unavoidable error lower bounds", "unobserved total transport", "causal environmental change", "independent river replications"]}
    write_json(out / "context_analysis_plan.json", plan)
    hourly = pd.read_parquet(DATA)
    hourly["site"] = hourly.site.astype(str)
    assert not hourly.duplicated(["site", "time_utc"]).any()
    metrics, events, sources = load_runs(args.runs)
    memberships = metrics[["site", "year", "stage"]].drop_duplicates()
    assert not memberships.duplicated(["site", "year"]).any()
    native = native_volume_audit()
    sy = site_year_context(hourly, native, memberships)
    sy.to_csv(out / "context_site_year.csv", index=False)
    ev = event_context(hourly, events, sy)
    ev.to_csv(out / "context_events.csv", index=False)
    code = hashlib.sha256((PROJECT / "scripts/paper_context.py").read_bytes() + (PROJECT / "scripts/replay.py").read_bytes()).hexdigest()[:12]
    cache = PROJECT / "cache/paper_contexts" / f"{digest(DATA)[:12]}_{code}"
    if args.skip_forward:
        forward = pd.read_csv(out / "context_forward_model.csv", dtype={"site": str})
        persistence = pd.read_csv(out / "context_residual_persistence.csv", dtype={"site": str})
    else:
        forward, persistence = forward_context(memberships, cache, args.history_seed, out)
        forward.to_csv(out / "context_forward_model.csv", index=False)
        persistence.to_csv(out / "context_residual_persistence.csv", index=False)
    base = baseline_context(metrics)
    base.to_csv(out / "context_zero_label_station_year.csv", index=False)
    merged = sy.loc[sy.included_in_original_data_gate].merge(forward, on=["site", "year", "stage"], validate="one_to_one")
    merged = merged.merge(base, on=["site", "year", "stage"], suffixes=("", "_zero_label"), validate="one_to_one")
    merged.to_csv(out / "context_station_year_diagnostics.csv", index=False)
    unit = independent_unit_example(hourly)
    write_json(out / "context_unit_audit.json", unit)
    case_run = Path(args.case_run)
    if not case_run.is_absolute():
        case_run = PROJECT / "results/paper_runs" / case_run
    cases = [] if args.skip_cases else select_and_export_cases(hourly, events, case_run, out, args.case_budget, args.history_seed)
    summary, event_groups = summarize(sy, ev, persistence, base)
    event_groups.to_csv(out / "context_event_retention_summary.csv", index=False)
    export_plot_contract(out, sy, ev, persistence, base)
    write_json(out / "context_summary.json", {"stages": summary, "case_selection": cases,
                                               "unit_audit": unit["status"], "historical_forward_models": len(forward),
                                               "all_forward_calibration_audits_reproduced": bool(forward.forward_audit_reproduced.all()),
                                               "no_cross_station_explanatory_model_fitted": True})
    manifest = {"status": "complete", "elapsed_seconds": time.perf_counter()-start,
                "data_sha256": digest(DATA), "native_sha256": digest(NATIVE), "context_cache": str(cache),
                "script_sha256": digest(Path(__file__)), "sources": sources, "arguments": vars(args),
                "checks": ["native volume sums match independent hourly Q-only sums", "all event reference loads and coverages match original events", "forward calibration audit reproduced", "historical model training ends before calibration and target", "exact continuous-hour residual pairs", "independent raw unit conversion matches 4 native quarters and full-hour load", "case prediction loads match event metrics"],
                "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": digest(p)} for p in sorted(out.glob("context_*")) if p.name != "context_manifest.json"}}
    write_json(out / "context_manifest.json", manifest)
    print(json.dumps(clean_json(summary), ensure_ascii=False, indent=2), flush=True)
    print(f"COMPLETE {time.perf_counter()-start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
