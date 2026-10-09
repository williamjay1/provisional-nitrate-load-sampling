"""Run prespecified validation pilot, with locked test requiring explicit release."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import platform

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "cache" / "matplotlib"))
os.environ.setdefault("JOBLIB_TEMP_FOLDER", str(ROOT / "temp"))
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import sklearn
from replay import (POLICIES, causal_features, tree_predictions, flow_query_score,
                    historical_design_days, planned_calendar_indices, replay_sampling, define_events, evaluate)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=str(ROOT / "config" / "pilot_v1.json"))
    p.add_argument("--data", default=str(ROOT / "datasets" / "hourly_observations.parquet"))
    p.add_argument("--year", type=int, default=2023)
    p.add_argument("--release-locked-test", action="store_true")
    p.add_argument("--sites", nargs="*")
    p.add_argument("--seeds", type=int, nargs="*")
    p.add_argument("--run-name")
    args = p.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if args.year in config["locked_test_years"] and not args.release_locked_test:
        raise SystemExit("Locked test: complete independent code/protocol audit before explicit release.")
    if args.year not in config["validation_years"] + config["locked_test_years"]:
        raise SystemExit("Year not prespecified in protocol")
    start_clock = time.perf_counter()
    start_cpu = time.process_time()
    started_at = datetime.now(timezone.utc).isoformat()
    run_name = args.run_name or datetime.now(timezone.utc).strftime("validation_%Y%m%dT%H%M%SZ")
    output = ROOT / "results" / run_name
    output.mkdir(parents=True, exist_ok=False)
    data = pd.read_parquet(args.data)
    data["site"] = data.site.astype(str)
    data["time_utc"] = pd.to_datetime(data.time_utc, utc=True)
    if args.sites:
        data = data.loc[data.site.isin(args.sites)]
    seeds = args.seeds or config["seeds"]
    metrics, event_rows, attempt_rows, prediction_frames, model_audit = [], [], [], [], []
    for site, frame in data.groupby("site", sort=True):
        begin = pd.Timestamp(f"{min(config['train_years'])}-01-01", tz="UTC")
        end = pd.Timestamp(f"{args.year+1}-01-01", tz="UTC")
        full_time = pd.date_range(begin, end, freq="h", inclusive="left")
        frame = frame.sort_values("time_utc").drop_duplicates("time_utc").set_index("time_utc").reindex(full_time)
        frame.index.name = "time_utc"
        frame = frame.reset_index()
        frame["site"] = site
        # Data preparer may name Q instant flag q_at_time_approved; resolve explicitly.
        if "q_sample_approved" not in frame and "q_at_time_approved" in frame:
            frame["q_sample_approved"] = frame.q_at_time_approved
        if "q_sample_approved" not in frame and "q_sample_reference_ok" in frame:
            frame["q_sample_approved"] = frame.q_sample_reference_ok
        years = frame.time_utc.dt.year
        training = years.isin(config["train_years"])
        qscale = float(frame.loc[training, "q_at_time_cms"].median())
        if not np.isfinite(qscale) or qscale <= 0:
            model_audit.append({"site": site, "status": "skipped_no_training_discharge"})
            continue
        features = causal_features(frame, qscale)
        labels = frame.nox_at_time_mg_l.to_numpy(dtype=float)
        valid_train = training.to_numpy() & frame.nox_sample_reference_ok.fillna(False).to_numpy(dtype=bool)
        valid_train &= np.isfinite(labels) & (labels >= 0) & frame.q_at_time_cms.notna().to_numpy()
        if "q_sample_reference_ok" in frame:
            valid_train &= frame.q_sample_reference_ok.fillna(False).to_numpy(dtype=bool)
        if "nox_sample_estimated" in frame:
            valid_train &= ~frame.nox_sample_estimated.fillna(False).to_numpy(dtype=bool)
        target_mask = (years == args.year).to_numpy()
        target = frame.loc[target_mask].reset_index(drop=True)
        if valid_train.sum() < 500:
            model_audit.append({"site": site, "status": "skipped_too_few_training_labels", "n": int(valid_train.sum())})
            continue
        q90 = float(frame.loc[training, "q_at_time_cms"].quantile(config["event_flow_quantile"]))
        events = define_events(target.q_at_time_cms.to_numpy(), q90,
                               config["event_merge_gap_hours"], config["minimum_event_hours"])
        historical_score, historical_info, historical_order = historical_design_days(frame.loc[training])
        flowscore = flow_query_score(features, qscale)
        flow_threshold = float(np.quantile(flowscore[training.to_numpy()], .85))
        for seed in seeds:
            rfconfig = config["random_forest"]
            train_idx = np.flatnonzero(valid_train)
            if len(train_idx) > rfconfig["max_training_points_per_site"]:
                train_idx = np.sort(np.random.default_rng(seed).choice(train_idx, rfconfig["max_training_points_per_site"], replace=False))
            model = RandomForestRegressor(n_estimators=rfconfig["n_estimators"], max_depth=rfconfig["max_depth"],
                                          min_samples_leaf=rfconfig["min_samples_leaf"], random_state=seed, n_jobs=4)
            model.fit(features.iloc[train_idx], labels[train_idx])
            base, disagreement = tree_predictions(model, features)
            qratio = np.expm1(features.log_q.to_numpy())
            query = {"flow_trigger": flowscore, "rf_disagreement": disagreement,
                     "rf_load_disagreement": disagreement * qratio}
            thresholds = {k: float(np.quantile(v[valid_train], .85)) for k, v in query.items()}
            thresholds["flow_trigger"] = flow_threshold
            valid_hidden = target.nox_sample_reference_ok.fillna(False).to_numpy(dtype=bool, copy=True)
            target_time = pd.DatetimeIndex(target.time_utc)
            model_audit.append({"site": site, "seed": seed, "training_rows": len(train_idx),
                                "training_period_end": str(frame.time_utc[training].max()),
                                "q_scale_cms": qscale, "q90_cms": q90, "thresholds": thresholds,
                                "historical_design": historical_info})
            empty_attempts = pd.DataFrame({"sample_index": pd.Series(dtype=int), "label_success": pd.Series(dtype=bool),
                                           "label_available_by_horizon": pd.Series(dtype=bool)})
            no_label_stats, no_label_events = evaluate(target, base[target_mask], events, empty_attempts, config["minimum_event_coverage"])
            no_label_keys = {"site": site, "year": args.year, "seed": seed, "budget": 0, "policy": "no_new_labels", "mode": "online"}
            metrics.append({**no_label_keys, **no_label_stats})
            event_rows.extend({**no_label_keys, **r} for r in no_label_events)
            for budget in config["budgets_per_year"]:
                for policy in POLICIES:
                    scores = query.get(policy, np.zeros(len(frame)))[target_mask]
                    result = replay_sampling(time=target_time, base_prediction=base[target_mask], query_scores=scores,
                                             threshold=thresholds.get(policy, 0), concentration_hidden=target.nox_at_time_mg_l.to_numpy(),
                                             label_valid_hidden=valid_hidden, policy=policy, budget=budget,
                                             delay_hours=config["laboratory_delay_hours"],
                                             min_spacing_hours=config["minimum_spacing_hours"],
                                             historical_day_score=historical_score,
                                             preplanned_indices=planned_calendar_indices(target_time, historical_order[policy], budget) if policy in historical_order else None)
                    keys = {"site": site, "year": args.year, "seed": seed, "budget": budget, "policy": policy}
                    for row in result.attempts.to_dict("records"):
                        attempt_rows.append({**keys, **row})
                    modes = {"online": result.online_prediction, "retrospective_residual": result.retrospective_prediction,
                             "retrospective_linear": result.interpolation_prediction}
                    for mode, prediction in modes.items():
                        stats, rows = evaluate(target, prediction, events, result.attempts, config["minimum_event_coverage"])
                        metrics.append({**keys, "mode": mode, **stats})
                        event_rows.extend({**keys, "mode": mode, **r} for r in rows)
                    if seed == seeds[0]:
                        prediction_frames.append(pd.DataFrame({"time_utc": target_time, **keys,
                                                              "base": base[target_mask], **modes,
                                                              "reference_nox_at_time": target.nox_at_time_mg_l.to_numpy(),
                                                              "q_at_time_cms": target.q_at_time_cms.to_numpy(),
                                                              "valid_hour": target.valid_hour.fillna(False).to_numpy(),
                                                              "reference_load_kg": target.load_kg.to_numpy()}))
            print(json.dumps({"site": site, "seed": seed, "train_rows": len(train_idx),
                              "valid_target_hours": int(target.valid_hour.fillna(False).sum()),
                              "events": len(events), "elapsed_seconds": round(time.perf_counter()-start_clock, 1)}), flush=True)
    pd.DataFrame(metrics).to_csv(output / "metrics.csv", index=False)
    pd.DataFrame(event_rows).to_csv(output / "events.csv", index=False)
    pd.DataFrame(attempt_rows).to_csv(output / "sampling_attempts.csv", index=False)
    if prediction_frames:
        pd.concat(prediction_frames, ignore_index=True).to_parquet(output / "predictions.parquet", index=False)
    (output / "model_audit.json").write_text(json.dumps(model_audit, indent=2), encoding="utf-8")
    manifest = {"run_name": run_name, "year": args.year, "config": config, "seed_overrides": seeds,
                "started_at_utc": started_at, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                "elapsed_seconds": time.perf_counter()-start_clock, "cpu_seconds": time.process_time()-start_cpu,
                "data_sha256": digest(args.data), "config_sha256": digest(args.config),
                "code_sha256": {x.name: digest(x) for x in [Path(__file__), ROOT/'scripts'/'replay.py']},
                "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                "sklearn": sklearn.__version__, "test_released": args.release_locked_test}
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(str(output), flush=True)


if __name__ == "__main__":
    main()
