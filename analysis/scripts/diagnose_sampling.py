"""Fixed descriptive sampling diagnostics; no subgroup search or significance tests.

Read existing run outputs only. This script does not load sensor datasets, model
objects, or unobserved target labels. CSV associations are descriptive, not causal.
Usage: python -B scripts/diagnose_sampling.py --run-dir RESULTS/RUN
       python -B scripts/diagnose_sampling.py --self-check
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd


CONTEXT = ["site", "year", "stage", "config_id", "delay_hours", "noise_adaptation_rate"]
ACTION_KEYS = CONTEXT + ["seed", "budget", "policy"]
RUN_KEYS = ACTION_KEYS + ["mode"]
STATION_KEYS = CONTEXT + ["budget", "policy", "mode"]
TRIGGER_POLICIES = {"value", "flow_trigger", "q_uncertainty", "rf_disagreement", "rf_load_disagreement"}
QUOTA_POLICIES = TRIGGER_POLICIES | {"uniform", "stratified_random", "historical_design"}
DEFAULT_BASELINES = ["uniform", "flow_trigger", "q_uncertainty", "stratified_random",
                     "historical_qr", "historical_dopt", "no_new_labels"]


def _bool(values):
    return values.astype(str).str.lower().map({"true": True, "1": True, "false": False, "0": False}).fillna(False).astype(bool)


def _normalize(frame: pd.DataFrame, defaults: dict) -> pd.DataFrame:
    frame = frame.copy()
    for name, default in defaults.items():
        if name not in frame:
            frame[name] = default
    for name in ("site", "stage", "config_id", "policy", "mode"):
        if name in frame:
            frame[name] = frame[name].fillna("unspecified").astype(str)
    for name in ("year", "seed", "budget"):
        if name in frame:
            frame[name] = pd.to_numeric(frame[name], errors="raise").astype(int)
    for name in ("delay_hours", "noise_adaptation_rate"):
        if name in frame:
            frame[name] = pd.to_numeric(frame[name], errors="raise")
    for name in ("sample_time", "arrival_time", "time_utc", "start_time", "end_time"):
        if name in frame:
            frame[name] = pd.to_datetime(frame[name], utc=True)
    for name in ("eligible", "boundary_uncertain", "label_success", "label_available_by_horizon", "is_candidate"):
        if name in frame:
            frame[name] = _bool(frame[name])
    return frame


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype={"site": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _group_lookup(frame: pd.DataFrame, keys: list[str]) -> dict:
    if frame.empty:
        return {}
    return {tuple(key): group.copy() for key, group in frame.groupby(keys, dropna=False, sort=False)}


def _key(row, columns):
    return tuple(row[c] for c in columns)


def _mean(values):
    x = np.asarray(list(values), dtype=float)
    return float(np.nanmean(x)) if np.isfinite(x).any() else np.nan


def _fraction(numerator: int | float, denominator: int | float) -> float:
    return float(numerator/denominator) if denominator else np.nan


def temporal_overlap(focal: pd.DataFrame, baseline: pd.DataFrame, tolerance_hours: float = 6.) -> dict:
    a = sorted(set(pd.Timestamp(x).value for x in focal.get("sample_time", [])))
    b = sorted(set(pd.Timestamp(x).value for x in baseline.get("sample_time", [])))
    exact = len(set(a) & set(b)); union = len(set(a) | set(b))
    tolerance = pd.Timedelta(hours=tolerance_hours).value
    i = j = matched = 0
    while i < len(a) and j < len(b):
        if abs(a[i]-b[j]) <= tolerance:
            matched += 1; i += 1; j += 1
        elif a[i] < b[j]:
            i += 1
        else:
            j += 1
    return {"focal_attempts": len(a), "baseline_attempts": len(b),
            "exact_shared_attempts": exact, "exact_calendar_jaccard": _fraction(exact, union),
            "matched_within_6h": matched,
            "within_6h_symmetric_match_fraction": _fraction(2*matched, len(a)+len(b))}


def _event_detail(event: dict, attempts: pd.DataFrame, total_hours: int) -> dict:
    start, end = pd.Timestamp(event["start_time"]), pd.Timestamp(event["end_time"])
    duration = (end-start).total_seconds()/3600
    delay = float(event["delay_hours"])
    if attempts.empty:
        inside = usable_inside = returned_inside = prior_arrivals = attempts
        first_sample_lag = first_return_lag = np.nan
    else:
        inside = attempts[(attempts.sample_time >= start) & (attempts.sample_time < end)]
        usable_inside = inside.loc[inside.label_success]
        returned_inside = usable_inside[usable_inside.arrival_time < end]
        prior_arrivals = attempts[attempts.label_success & (attempts.sample_time < start)
                                 & (attempts.arrival_time >= start) & (attempts.arrival_time < end)]
        first_sample_lag = (inside.sample_time.min()-start).total_seconds()/3600 if len(inside) else np.nan
        first_return_lag = (usable_inside.arrival_time.min()-start).total_seconds()/3600 if len(usable_inside) else np.nan
    onset_block, spent = np.nan, np.nan
    budget = int(event["budget"])
    if budget > 0 and event["policy"] in QUOTA_POLICIES:
        origin = pd.Timestamp(f"{int(event['year'])}-01-01", tz="UTC")
        index = int((start-origin).total_seconds()//3600)
        boundaries = np.linspace(0, total_hours, budget+1, dtype=int)
        onset_block = min(budget-1, max(0, int(np.searchsorted(boundaries[1:], index, side="right"))))
        spent = bool(len(attempts[(attempts.block == onset_block) & (attempts.sample_time < start)])) if len(attempts) else False
    result = dict(event)
    result.update({"duration_hours": duration, "duration_over_delay": duration/delay if delay > 0 else np.nan,
        "duration_le_delay": duration <= delay,
        "in_event_attempts": len(inside), "in_event_usable_labels": len(usable_inside),
        "in_event_labels_returned_before_end": len(returned_inside),
        "pre_event_samples_returned_during_event": len(prior_arrivals),
        "captured_by_attempt": bool(len(inside)), "captured_by_usable_label": bool(len(usable_inside)),
        "in_event_feedback_available": bool(len(returned_inside)),
        "any_label_feedback_during_event": bool(len(returned_inside)+len(prior_arrivals)),
        "first_in_event_sample_lag_hours": first_sample_lag,
        "first_in_event_label_return_lag_hours": first_return_lag,
        "hours_remaining_after_first_in_event_return": max(0., duration-first_return_lag) if np.isfinite(first_return_lag) else 0.,
        "onset_quota_block": onset_block, "onset_quota_already_spent": spent,
        "absolute_relative_error": abs(float(event["relative_error"])) if pd.notna(event["relative_error"]) else np.nan,
        "absolute_valid_window_load_error_kg": abs(float(event["predicted_valid_window_load_kg"])-float(event["reference_valid_window_load_kg"]))})
    return result


def _station_mean(rows: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=keys+["seed_count"])
    numeric = [c for c in rows.select_dtypes(include=["number", "bool"]).columns if c not in keys+["seed"]]
    records=[]
    for key, group in rows.groupby(keys,dropna=False,sort=True):
        rec=dict(zip(keys,key if isinstance(key,tuple) else (key,)))
        rec["seed_count"]=int(group.seed.nunique())
        for name in numeric:
            rec[name]=_mean(group[name])
        if "trace_available" in group:
            rec["trace_seed_count"]=int(group.loc[group.trace_available.astype(bool),"seed"].nunique())
        if "event_error_improvement" in group:
            rec["finite_paired_event_error_seed_count"]=int(group.loc[np.isfinite(group.event_error_improvement),"seed"].nunique())
        records.append(rec)
    return pd.DataFrame(records)


def diagnose(metrics: pd.DataFrame, attempts: pd.DataFrame, events: pd.DataFrame,
             trace: pd.DataFrame, *, focal_policy: str, baselines: list[str]) -> dict[str,pd.DataFrame]:
    if metrics.duplicated(RUN_KEYS).any():
        raise ValueError("Duplicate metric keys: separate runs/configurations before diagnosis")
    if len(attempts) and attempts.duplicated(ACTION_KEYS+["sample_index"]).any():
        # A shared action list can be repeated verbatim across reconstruction modes.
        uniq=attempts.drop(columns=["mode"],errors="ignore").drop_duplicates()
        if uniq.duplicated(ACTION_KEYS+["sample_index"]).any():
            raise ValueError("Conflicting duplicate action records")
        attempts=uniq
    attempt_groups=_group_lookup(attempts,ACTION_KEYS)
    trace_groups=_group_lookup(trace,ACTION_KEYS)
    metric_groups={_key(r,RUN_KEYS):r for r in metrics.to_dict("records")}
    empty_attempts=pd.DataFrame(columns=["sample_index","sample_time","arrival_time","block","label_success"])
    details=[]
    for event in events.to_dict("records"):
        mk=_key(event,RUN_KEYS)
        if mk not in metric_groups:
            raise ValueError("Event without matching metric record")
        details.append(_event_detail(event,attempt_groups.get(_key(event,ACTION_KEYS),empty_attempts),
                                     int(metric_groups[mk]["hours"])))
    event_details=pd.DataFrame(details)
    detail_groups=_group_lookup(event_details,RUN_KEYS)
    policy_rows=[]
    keep_metrics=["hours","valid_hours","hour_coverage","events_all","events_eligible",
                  "event_mean_absolute_relative_error","valid_window_relative_bias",
                  "concentration_mae_mg_l","hourly_load_normalized_absolute_error"]
    for row in metrics.to_dict("records"):
        rec={c:row[c] for c in RUN_KEYS}
        rec.update({c:row[c] for c in keep_metrics if c in row})
        a=attempt_groups.get(_key(row,ACTION_KEYS),empty_attempts)
        e=detail_groups.get(_key(row,RUN_KEYS),pd.DataFrame())
        t=trace_groups.get(_key(row,ACTION_KEYS),pd.DataFrame())
        reasons=a.reason if len(a) and "reason" in a else pd.Series(dtype=str)
        deadline=int(reasons.eq("block_deadline").sum())
        trigger=int((~reasons.eq("block_deadline")).sum()) if row["policy"] in TRIGGER_POLICIES else 0
        rec.update({"actual_attempts":len(a),"successful_attempts":int(a.label_success.sum()) if len(a) else 0,
            "deadline_attempts":deadline,"deadline_fraction":_fraction(deadline,len(a)),
            "threshold_trigger_attempts":trigger,"threshold_trigger_fraction":_fraction(trigger,len(a)),
            "calendar_planned_attempts":len(a)-deadline-trigger,
            "label_failure_fraction":_fraction(int((~a.label_success).sum()),len(a)) if len(a) else np.nan,
            "trace_available":bool(len(t))})
        if len(a):
            actual_delay=(a.arrival_time-a.sample_time).dt.total_seconds()/3600
            if not np.allclose(actual_delay,float(row["delay_hours"])):
                raise ValueError("Declared delay disagrees with attempt timestamps")
        if len(e):
            rec.update({"defined_event_duration_median_hours":float(e.duration_hours.median()),
                "event_duration_over_delay_median":float(e.duration_over_delay.median()),
                "events_duration_le_delay_fraction":float(e.duration_le_delay.mean()),
                "event_attempt_capture_fraction":float(e.captured_by_attempt.mean()),
                "event_in_time_feedback_fraction":float(e.in_event_feedback_available.mean()),
                "event_any_label_feedback_fraction":float(e.any_label_feedback_during_event.mean()),
                "event_usable_label_capture_fraction":float(e.captured_by_usable_label.mean()),
                "onset_quota_already_spent_fraction":_mean(e.onset_quota_already_spent),
                "in_event_sample_median_lag_hours":float(e.first_in_event_sample_lag_hours.median()),
                "in_event_label_median_return_lag_hours":float(e.first_in_event_label_return_lag_hours.median())})
        if len(t):
            candidates=t.loc[t.is_candidate] if "is_candidate" in t else t
            usable=candidates[np.isfinite(candidates.query_score)&np.isfinite(candidates.query_threshold)]
            positive_threshold=usable[usable.query_threshold>0]
            rec.update({"trace_candidate_grid_hours":len(candidates),"trace_scored_candidates":len(usable),
                "score_exceedance_fraction_all_scored_grid_times":float(((usable.query_score>0)&(usable.query_score>=usable.query_threshold)).mean()) if len(usable) else np.nan,
                "score_threshold_ratio_median":float((positive_threshold.query_score/positive_threshold.query_threshold).median()) if len(positive_threshold) else np.nan,
                "noise_variance_first":float(t.noise_variance.iloc[0]) if "noise_variance" in t else np.nan,
                "noise_variance_last":float(t.noise_variance.iloc[-1]) if "noise_variance" in t else np.nan})
        policy_rows.append(rec)

    pair_rows=[];event_pair_rows=[]
    focal_rows=metrics[(metrics.policy==focal_policy)&(metrics.budget>0)]
    if focal_rows.empty:
        raise ValueError(f"Focal policy {focal_policy!r} absent")
    available=set(metrics.policy)
    for focal in focal_rows.to_dict("records"):
        for baseline_policy in baselines:
            if baseline_policy not in available or baseline_policy==focal_policy:
                continue
            baseline_key=dict(focal,policy=baseline_policy)
            if baseline_policy=="no_new_labels":baseline_key["budget"]=0
            b=metric_groups.get(_key(baseline_key,RUN_KEYS))
            if b is None:continue
            keys={c:focal[c] for c in CONTEXT+["seed","budget","mode"]}
            keys.update(focal_policy=focal_policy,baseline_policy=baseline_policy,
                        baseline_budget=int(b["budget"]),same_annual_budget=bool(focal["budget"]==b["budget"]))
            f_event=float(focal.get("event_mean_absolute_relative_error",np.nan));b_event=float(b.get("event_mean_absolute_relative_error",np.nan))
            rec={**keys,"focal_event_error":f_event,"baseline_event_error":b_event,
                 "event_error_improvement":b_event-f_event,
                 "valid_window_abs_bias_improvement":abs(float(b["valid_window_relative_bias"]))-abs(float(focal["valid_window_relative_bias"])),
                 "concentration_mae_improvement":float(b["concentration_mae_mg_l"])-float(focal["concentration_mae_mg_l"])}
            rec.update(temporal_overlap(attempt_groups.get(_key(focal,ACTION_KEYS),empty_attempts),
                                        attempt_groups.get(_key(b,ACTION_KEYS),empty_attempts)))
            pair_rows.append(rec)
            fe=detail_groups.get(_key(focal,RUN_KEYS),pd.DataFrame())
            be=detail_groups.get(_key(b,RUN_KEYS),pd.DataFrame())
            if fe.empty or be.empty:continue
            event_keys=["event_id","start_time","end_time"]
            if fe.duplicated(event_keys).any() or be.duplicated(event_keys).any():
                raise ValueError("Duplicate event identifiers")
            merged=fe.merge(be,on=event_keys,suffixes=("_focal","_baseline"),validate="one_to_one")
            if len(merged)!=len(fe) or len(merged)!=len(be):
                raise ValueError("Policy event sets differ; common-event comparison invalid")
            for event in merged.to_dict("records"):
                if (event["eligible_focal"]!=event["eligible_baseline"]
                    or not np.isclose(event["reference_valid_window_load_kg_focal"],event["reference_valid_window_load_kg_baseline"],equal_nan=True)):
                    raise ValueError("Compared policies have different event references")
                out={**keys,**{c:event[c] for c in event_keys},
                     "reference_eligible":bool(event["eligible_focal"]),
                     "duration_hours":event["duration_hours_focal"],
                     "duration_over_delay":event["duration_over_delay_focal"],
                     "duration_le_delay":event["duration_le_delay_focal"],
                     "focal_absolute_relative_error":event["absolute_relative_error_focal"],
                     "baseline_absolute_relative_error":event["absolute_relative_error_baseline"],
                     "event_error_improvement":event["absolute_relative_error_baseline"]-event["absolute_relative_error_focal"]}
                for name in ("captured_by_attempt","in_event_feedback_available","onset_quota_already_spent",
                             "first_in_event_sample_lag_hours","first_in_event_label_return_lag_hours"):
                    out["focal_"+name]=event[name+"_focal"];out["baseline_"+name]=event[name+"_baseline"]
                for state_name,source in (("attempt_capture_state","captured_by_attempt"),("feedback_state","in_event_feedback_available")):
                    f=bool(event[source+"_focal"]);bb=bool(event[source+"_baseline"])
                    out[state_name]="both" if f and bb else "focal_only" if f else "baseline_only" if bb else "neither"
                event_pair_rows.append(out)
    pairs=pd.DataFrame(pair_rows);event_pairs=pd.DataFrame(event_pair_rows)
    pair_station_keys=CONTEXT+["budget","mode","focal_policy","baseline_policy","baseline_budget","same_annual_budget"]
    associations=[]
    if len(event_pairs):
        valid=event_pairs[event_pairs.reference_eligible & np.isfinite(event_pairs.event_error_improvement)]
        for diagnostic in ("attempt_capture_state","feedback_state"):
            keys=pair_station_keys+[diagnostic]
            for key,g in valid.groupby(keys,dropna=False,sort=True):
                rec=dict(zip(keys,key));state=rec.pop(diagnostic)
                # Average within seed first: events/seeds are not independent sites.
                by_seed=g.groupby("seed").agg(improvement=("event_error_improvement","mean"),
                     focal_error=("focal_absolute_relative_error","mean"),
                     baseline_error=("baseline_absolute_relative_error","mean"))
                rec.update(diagnostic=diagnostic,capture_state=state,
                    event_seed_pairs=len(g),unique_events=g.start_time.nunique(),seed_count=g.seed.nunique(),
                    mean_event_error_improvement=float(by_seed.improvement.mean()),
                    mean_focal_event_error=float(by_seed.focal_error.mean()),
                    mean_baseline_event_error=float(by_seed.baseline_error.mean()),
                    median_duration_over_delay=float(g.duration_over_delay.median()))
                associations.append(rec)
    return {"station_policy_diagnostics":_station_mean(pd.DataFrame(policy_rows),STATION_KEYS),
            "station_pair_diagnostics":_station_mean(pairs,pair_station_keys),
            "event_diagnostics":event_details,"paired_event_diagnostics":event_pairs,
            "capture_error_associations":pd.DataFrame(associations)}


def _self_check():
    t=pd.Timestamp("2023-01-01",tz="UTC")
    a=pd.DataFrame({"sample_time":[t,t+pd.Timedelta(hours=6)]})
    b=pd.DataFrame({"sample_time":[t+pd.Timedelta(hours=3)]})
    overlap=temporal_overlap(a,b)
    assert overlap["matched_within_6h"]==1  # No many-to-one matching inflation.
    event=dict(start_time=t,end_time=t+pd.Timedelta(hours=12),delay_hours=24,budget=24,
               policy="value",year=2023,relative_error=.2,predicted_valid_window_load_kg=12.,
               reference_valid_window_load_kg=10.)
    attempts=pd.DataFrame({"sample_time":[t+pd.Timedelta(hours=1)],
                           "arrival_time":[t+pd.Timedelta(hours=25)],"label_success":[True],"block":[0]})
    detail=_event_detail(event,attempts,8760)
    assert detail["captured_by_attempt"] and not detail["in_event_feedback_available"]
    assert detail["duration_over_delay"]==.5
    assert detail["hours_remaining_after_first_in_event_return"]==0
    assert not detail["onset_quota_already_spent"]
    attempts.loc[0,"sample_time"]=t-pd.Timedelta(hours=2)
    attempts.loc[0,"arrival_time"]=t+pd.Timedelta(hours=22)
    detail=_event_detail(event,attempts,8760)
    assert detail["onset_quota_already_spent"]
    print("6 diagnostic assertions passed")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir",type=Path)
    p.add_argument("--output-dir",type=Path)
    p.add_argument("--focal-policy",default="value")
    p.add_argument("--baselines",nargs="+",default=DEFAULT_BASELINES)
    p.add_argument("--overwrite",action="store_true")
    p.add_argument("--allow-incomplete",action="store_true")
    p.add_argument("--self-check",action="store_true")
    args=p.parse_args()
    if args.self_check:_self_check();return
    if args.run_dir is None:p.error("--run-dir is required unless --self-check")
    root=args.run_dir.resolve();out=(args.output_dir or root/"sampling_diagnostics").resolve()
    manifest_path=root/"run_manifest.json"
    if not manifest_path.exists() and not args.allow_incomplete:
        raise SystemExit("Run is incomplete: no run_manifest.json. Do not diagnose a moving experiment.")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    arguments=manifest.get("arguments",{})
    defaults={"stage":arguments.get("stage","unspecified"),"config_id":arguments.get("config_id","unspecified"),
              "delay_hours":arguments.get("delay_hours",manifest.get("config",{}).get("laboratory_delay_hours",24)),
              "noise_adaptation_rate":arguments.get("noise_adaptation_rate",0.),"mode":"online"}
    sources={"metrics":root/"metrics.csv","events":root/"events.csv"}
    sources["attempts"]=next((root/name for name in ("sampling_attempts.csv","attempts.csv") if (root/name).exists()),root/"sampling_attempts.csv")
    for name,path in sources.items():
        if not path.exists():raise SystemExit(f"Required {name} file missing: {path}")
    metrics=_normalize(_read_csv(sources["metrics"]),defaults)
    events=_normalize(_read_csv(sources["events"]),defaults)
    attempts=_normalize(_read_csv(sources["attempts"]),defaults)
    trace=pd.DataFrame()
    for filename in ("query_trace.parquet","query_trace.csv","trace.parquet","trace.csv"):
        path=root/filename
        if path.exists():
            trace=_normalize(pd.read_parquet(path) if path.suffix==".parquet" else _read_csv(path),defaults)
            sources["trace"]=path;break
    tables=diagnose(metrics,attempts,events,trace,focal_policy=args.focal_policy,baselines=args.baselines)
    filenames=[name+".csv" for name in tables]+["diagnostic_manifest.json"]
    if not args.overwrite and any((out/name).exists() for name in filenames):
        raise SystemExit("Diagnostic outputs already exist; use a new --output-dir or explicit --overwrite")
    out.mkdir(parents=True,exist_ok=True)
    for name,table in tables.items():table.to_csv(out/(name+".csv"),index=False)
    audit={"created_utc":datetime.now(timezone.utc).isoformat(),"source_run":str(root),
       "focal_policy":args.focal_policy,"requested_baselines":args.baselines,
       "years_read":sorted(metrics.year.unique().tolist()),"row_counts":{k:len(v) for k,v in tables.items()},
       "input_sha256":{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in sources.items()},
       "script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       "python":platform.python_version(),"pandas":pd.__version__,
       "interpretation":["Positive error_improvement means lower focal error; negative means worse.",
           "Station tables average seeds within site-year; events and seeds are not independent sites.",
           "Trace may include only one seed; trace_seed_count explicitly records availability.",
           "Score exceedance includes already-spent quota times and is not an eligible-action frequency.",
           "Captured in an event does not imply its label arrived before the event ended.",
           "Quota-spent diagnostics apply only to quota-constrained policies; global calendars are not relabelled as quotas.",
           "Zero-label baseline has a different cost; same_annual_budget is false.",
           "Capture/error associations are descriptive. No p-values, cut-point search or causal effects are computed."]}
    (out/"diagnostic_manifest.json").write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps({"output_dir":str(out),"years_read":audit["years_read"],"row_counts":audit["row_counts"]},ensure_ascii=False))


if __name__=="__main__":
    main()
