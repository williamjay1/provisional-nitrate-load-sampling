"""Deterministic, site-balanced summaries; reads only explicitly named completed runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "results" / "analysis_v2"
KEY = ["site", "year", "seed", "budget", "policy", "mode"]
SITE_KEY = ["run", "year", "site", "budget", "policy", "mode"]
METHOD_KEY = ["run", "year", "budget", "policy", "mode"]
METRICS = ["event_mean_absolute_relative_error", "absolute_valid_window_relative_bias"]
MODES = ["online", "retrospective_residual", "retrospective_linear"]
POLICIES = ["uniform", "flow_trigger", "rf_disagreement", "rf_load_disagreement",
            "historical_design", "historical_qr", "historical_dopt"]
ISSUE_COLUMNS = ["run", "check", "detail"]


def read_csv(path):
    return pd.read_csv(path, dtype={"site": str})


def bool_column(frame, name):
    values = frame[name].astype(str).str.lower()
    if not values.isin(["true", "false"]).all():
        raise ValueError(f"Invalid boolean in {name}")
    return values.eq("true")


def audit_run(path, m, events, attempts, manifest):
    issues, audit = [], []
    run = path.name

    def check(ok, name, detail):
        if not bool(ok):
            issues.append({"run": run, "check": name, "detail": str(detail)})

    cfg = manifest["config"]
    seeds = sorted(manifest.get("seed_overrides", cfg["seeds"]))
    check(len(seeds) == 3, "three_seeds", seeds)
    check(not m.duplicated(KEY).any(), "unique_metric_keys", int(m.duplicated(KEY).sum()))
    check(set([24, 48, 96]).issubset(set(m.budget)), "all_budgets_present", sorted(m.budget.unique()))
    check(set(POLICIES).issubset(set(m.policy)), "all_policies_present", sorted(m.policy.unique()))
    for site, year in m[["site", "year"]].drop_duplicates().itertuples(index=False):
        part = m.loc[(m.site == site) & (m.year == year)]
        for policy in sorted(set(m.policy) - {"no_new_labels"}):
            expected = {(seed, budget, policy, mode) for seed in seeds
                        for budget in cfg["budgets_per_year"] for mode in MODES}
            got = set(part.loc[part.policy == policy, ["seed", "budget", "policy", "mode"]].itertuples(index=False, name=None))
            check(got == expected, "complete_design", f"{site}/{year}/{policy}: missing={sorted(expected-got)} extra={sorted(got-expected)}")
        nl = part.loc[part.policy == "no_new_labels"]
        check(set(nl.seed) == set(seeds) and (nl.budget == 0).all() and (nl["mode"] == "online").all(),
              "no_label_design", f"{site}/{year}")
        for field in ["hours", "valid_hours", "events_all", "events_eligible", "events_boundary_uncertain", "reference_valid_window_load_kg"]:
            check(part[field].nunique(dropna=False) == 1, "common_reference_support", f"{site}/{year}/{field}")

    events = events.copy()
    events["eligible"] = bool_column(events, "eligible")
    check(not events.duplicated(KEY + ["event_id"]).any(), "unique_event_keys", len(events))
    event_map = {k: v for k, v in events.groupby(KEY, sort=True)}
    for row in m.itertuples(index=False):
        key = tuple(getattr(row, x) for x in KEY)
        ev = event_map.get(key, pd.DataFrame())
        eligible_errors = ev.loc[ev.eligible, "relative_error"].abs().dropna() if len(ev) else pd.Series(dtype=float)
        check(len(ev) == row.events_all and len(eligible_errors) == row.events_eligible, "event_count_consistency", key)
        mean_error = eligible_errors.mean()
        check(np.isclose(mean_error, row.event_mean_absolute_relative_error, equal_nan=True), "event_metric_recomputed", key)
        check(np.isclose((row.predicted_valid_window_load_kg-row.reference_valid_window_load_kg)/row.reference_valid_window_load_kg,
                         row.valid_window_relative_bias, equal_nan=True), "bias_recomputed", key)

    attempts = attempts.copy()
    attempts["label_success"] = bool_column(attempts, "label_success")
    attempts["label_available_by_horizon"] = bool_column(attempts, "label_available_by_horizon")
    for col in ["sample_time", "arrival_time"]:
        attempts[col] = pd.to_datetime(attempts[col], utc=True)
    akeys = KEY[:-1]
    attempt_map = {k: v.sort_values("sample_time") for k, v in attempts.groupby(akeys, sort=True)}
    metric_keys = set(m[akeys].itertuples(index=False, name=None))
    check(set(attempt_map).issubset(metric_keys), "orphan_attempt_groups", sorted(set(attempt_map)-metric_keys))
    for key, rows in m.groupby(akeys, sort=True):
        a = attempt_map.get(key, attempts.iloc[:0])
        site, year, seed, budget, policy = key
        hours = int(rows.hours.iloc[0])
        spacing = a.sample_time.diff().dt.total_seconds().div(3600).dropna()
        gap = float(spacing.min()) if len(spacing) else np.nan
        n, success, returned = len(a), int(a.label_success.sum()), int(a.label_available_by_horizon.sum())
        before = len(issues)
        check(n <= budget, "budget_not_exceeded", key)
        check(not a.sample_index.duplicated().any(), "unique_attempt_times", key)
        check(len(spacing) == 0 or gap >= max(24, cfg["minimum_spacing_hours"]), "minimum_spacing", (key, gap))
        check(((a.sample_index >= 0) & (a.sample_index < hours)).all(), "sample_in_horizon", key)
        check(((a.arrival_time-a.sample_time).dt.total_seconds()/3600 == cfg["laboratory_delay_hours"]).all(), "arrival_delay_time", key)
        check((a.arrival_index-a.sample_index == cfg["laboratory_delay_hours"]).all(), "arrival_delay_index", key)
        origin = pd.Timestamp(f"{year}-01-01", tz="UTC")
        check((a.sample_time == origin + pd.to_timedelta(a.sample_index, unit="h")).all(), "sample_time_index", key)
        expected_return = a.label_success & (a.arrival_index < hours)
        check((a.label_available_by_horizon == expected_return).all(), "return_flag", key)
        check((np.isfinite(a.observed_mg_l) == a.label_success).all(), "observed_label_success", key)
        check((a.loc[a.label_success, "observed_mg_l"] >= 0).all(), "nonnegative_success_label", key)
        for field, count in [("attempts", n), ("successful_samples", success), ("returned_by_horizon", returned)]:
            check((rows[field] == count).all(), "count_consistency", (key, field, count))
        audit.append(dict(zip(["run"] + akeys, [run] + list(key)), attempts=n, successful_samples=success,
                          returned_by_horizon=returned, failed_samples=n-success, pending_at_horizon=success-returned,
                          budget_shortfall=budget-n, minimum_spacing_hours=gap, constraints_passed=len(issues) == before))
    return issues, audit


def summarize(paths):
    all_metrics, all_issues, all_audits, sources = [], [], [], []
    for path in sorted(paths, key=lambda p: str(p).lower()):
        manifest = json.loads((path / "run_manifest.json").read_text(encoding="utf-8"))
        if not manifest.get("completed_at_utc"):
            raise ValueError(f"Run is not complete: {path}")
        m = read_csv(path / "metrics.csv")
        ev = read_csv(path / "events.csv")
        attempts = read_csv(path / "sampling_attempts.csv")
        issues, audit = audit_run(path, m, ev, attempts, manifest)
        all_issues.extend(issues)
        all_audits.extend(audit)
        m["run"] = path.name
        m[METRICS[1]] = m.valid_window_relative_bias.abs()  # Absolute BEFORE seed mean.
        all_metrics.append(m)
        sources.append({"run": path.name, "path": str(path), "year": manifest["year"],
                        "sha256": {name: hashlib.sha256((path / name).read_bytes()).hexdigest()
                                   for name in ["metrics.csv", "events.csv", "sampling_attempts.csv", "run_manifest.json"]}})
    m = pd.concat(all_metrics, ignore_index=True)
    numeric = [col for col in m.select_dtypes(include=[np.number]).columns if col not in SITE_KEY + ["seed"]]
    grouped = m.groupby(SITE_KEY, sort=True, dropna=False)
    site = grouped[numeric].mean().reset_index()
    site["n_seed"] = grouped.seed.nunique().to_numpy()
    for metric in METRICS:
        site[metric + "_n_seed"] = grouped[metric].count().to_numpy()
    aggregate = []
    for key, g in site.groupby(METHOD_KEY, sort=True):
        for metric in METRICS:
            valid = g.loc[np.isfinite(g[metric])]
            aggregate.append(dict(zip(METHOD_KEY, key), metric=metric, median=valid[metric].median(),
                                  n_site=len(valid), n_site_total=len(g),
                                  eligible_events_by_site=json.dumps(dict(zip(g.site, g.events_eligible.astype(int))), sort_keys=True),
                                  evaluable_sites="|".join(valid.site)))
    pair_rows = []
    for row in site.loc[site.budget > 0].to_dict("records"):
        for baseline in ["uniform", "flow_trigger", "no_new_labels"]:
            source_budget = 0 if baseline == "no_new_labels" else row["budget"]
            source_mode = "online" if baseline == "no_new_labels" else row["mode"]
            found = site.loc[(site.run == row["run"]) & (site.year == row["year"]) & (site.site == row["site"])
                             & (site.budget == source_budget) & (site.policy == baseline) & (site["mode"] == source_mode)]
            if len(found) != 1:
                all_issues.append({"run": row["run"], "check": "paired_baseline_missing", "detail": str((row["site"], row["budget"], row["policy"], row["mode"], baseline))})
            for metric in METRICS:
                base = float(found.iloc[0][metric]) if len(found) == 1 else np.nan
                value = row[metric]
                delta = value - base
                evaluable = bool(np.isfinite(value) and np.isfinite(base))
                pair_rows.append({**{k: row[k] for k in SITE_KEY}, "baseline": baseline,
                                  "baseline_source_budget": source_budget, "baseline_source_mode": source_mode,
                                  "metric": metric, "policy_value": value, "baseline_value": base,
                                  "paired_difference": delta, "pair_evaluable": evaluable,
                                  "win": evaluable and delta < -1e-12, "tie": evaluable and abs(delta) <= 1e-12,
                                  "events_eligible": row["events_eligible"], "n_seed": row["n_seed"]})
    pairs = pd.DataFrame(pair_rows)
    paired_summary = []
    for key, g in pairs.groupby(METHOD_KEY + ["baseline", "metric"], sort=True):
        valid = g.loc[g.pair_evaluable]
        paired_summary.append(dict(zip(METHOD_KEY + ["baseline", "metric"], key), n_site=len(valid),
                                   n_site_total=len(g), wins=int(valid.win.sum()), ties=int(valid.tie.sum()),
                                   losses=int(len(valid)-valid.win.sum()-valid.tie.sum()),
                                   median_paired_difference=valid.paired_difference.median(),
                                   paired_policy_median=valid.policy_value.median(), paired_baseline_median=valid.baseline_value.median()))
    counts = site[["run", "year", "site", "events_all", "events_eligible", "events_boundary_uncertain", "valid_hours", "hours", "hour_coverage"]].drop_duplicates()
    frames = {"site_summary": site, "aggregate_summary": pd.DataFrame(aggregate), "site_event_counts": counts,
              "paired_sites": pairs, "paired_summary": pd.DataFrame(paired_summary),
              "sampling_audit": pd.DataFrame(all_audits), "check_issues": pd.DataFrame(all_issues, columns=ISSUE_COLUMNS)}
    report = {"sources": sources, "all_checks_passed": not all_issues, "n_check_issues": len(all_issues),
              "aggregation": "Mean across the 3 seeds within site/budget/policy/mode; then median across evaluable sites, separately by run/year. Absolute bias is taken before averaging seeds.",
              "comparison": "Difference = policy minus baseline; lower is better. no_new_labels source budget=0 and mode=online is explicitly reused across target budgets/modes.",
              "boundary": "Event errors concern valid observation windows within high-coverage (>=95%), boundary-determinate events, not complete event totals. Window bias is not necessarily full-year load bias. No statistical significance or deployment benefit is implied. Event-ineligible sites remain in other evaluable metrics.",
              "records": {name: json.loads(frame.to_json(orient="records", double_precision=15)) for name, frame in frames.items()}}
    return frames, report


def plot_heterogeneity(out):
    """Read published CSV, so plotted values share the exact tabular source."""
    os.environ.setdefault("MPLCONFIGDIR", str(out / ".matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"svg.hashsalt": "nitrate-pilot-v2", "font.size": 10,
                         "pdf.fonttype": 42, "ps.fonttype": 42})
    p = read_csv(out / "paired_sites.csv")
    p = p.loc[(p.policy == "rf_load_disagreement") & (p["mode"] == "online")
              & (p.metric == METRICS[0]) & p.baseline.isin(["uniform", "flow_trigger"])
              & bool_column(p, "pair_evaluable")].copy()
    if p.empty:
        return
    years = sorted(p.year.unique())
    if p.duplicated(["year", "site", "budget", "baseline"]).any():
        raise ValueError("Plot requires only one run per year; CSVs preserve all runs")
    limit = max(float(p.paired_difference.abs().max() * 100), 1e-6)
    fig, axes = plt.subplots(len(years), 2, figsize=(11, 3.9 * len(years) + 1.4), squeeze=False)
    for row, year in enumerate(years):
        for col, baseline in enumerate(["uniform", "flow_trigger"]):
            ax = axes[row, col]
            sub = p.loc[(p.year == year) & (p.baseline == baseline)]
            values = sub.pivot(index="site", columns="budget", values="paired_difference").reindex(columns=[24, 48, 96]).sort_index() * 100
            picture = ax.imshow(values.to_numpy(), cmap="RdBu_r", vmin=-limit, vmax=limit, aspect="auto")
            ax.set_xticks(range(3), [24, 48, 96])
            ax.set_yticks(range(len(values)), values.index)
            ax.set_xlabel("Annual sample budget")
            ax.set_ylabel("USGS site")
            ax.set_title(f"{year} vs {'uniform' if baseline == 'uniform' else 'flow trigger'}")
            for i in range(len(values)):
                for j in range(3):
                    value = values.iloc[i, j]
                    label = f"{value:+.1f}" if np.isfinite(value) else "NA"
                    ax.text(j, i, label, ha="center", va="center", color="white" if abs(value) > .55 * limit else "black")
    fig.suptitle("Online sampling: site-level event-error differences", fontsize=15, y=.985)
    fig.text(.5, .949, "RF load-weighted disagreement minus baseline; negative values favor the RF policy", ha="center", fontsize=10)
    fig.subplots_adjust(left=.12, right=.87, top=.89, bottom=.17, hspace=.35, wspace=.45)
    bar = fig.colorbar(picture, cax=fig.add_axes([.91, .27, .02, .51]))
    bar.set_label("Difference in percentage points")
    fig.text(.06, .095, "Each cell: site mean over 3 seeds; sites receive equal weight (no pooling of events).\n"
             "Metric: mean absolute relative load error over valid observation windows within eligible events\n"
             "(coverage >=95%; boundaries determinate). Site 05465500 has 0 eligible events and is not scored.\n"
             "Source: paired_sites.csv. All budgets, policies and reconstruction modes remain in the CSV outputs.",
             fontsize=9, va="top")
    stem = out / "online_site_heterogeneity"
    fig.savefig(stem.with_suffix(".svg"), metadata={"Date": None})
    fig.savefig(stem.with_suffix(".pdf"), metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(stem.with_suffix(".png"), dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=OUT_ROOT)
    parser.add_argument("--no-plot", action="store_true", help="Write tables and JSON only")
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(OUT_ROOT.resolve()):
        parser.error(f"Outputs must stay within {OUT_ROOT}")
    if len({p.resolve() for p in args.run_dirs}) != len(args.run_dirs) or len({p.name for p in args.run_dirs}) != len(args.run_dirs):
        parser.error("Duplicate run directory or run name")
    frames, report = summarize([p.resolve() for p in args.run_dirs])
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_csv(out / f"{name}.csv", index=False, float_format="%.15g", lineterminator="\n")
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if not args.no_plot:
        plot_heterogeneity(out)
    print(json.dumps({"output": str(out), "all_checks_passed": report["all_checks_passed"],
                      "n_check_issues": report["n_check_issues"], "runs": [p.name for p in args.run_dirs]}, ensure_ascii=False))
    return 0 if report["all_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
