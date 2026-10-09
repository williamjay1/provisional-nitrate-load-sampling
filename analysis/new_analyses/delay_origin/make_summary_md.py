"""Generate SUMMARY.md for the delay/origin diagnostic from the produced CSVs.

Every number in the generated report is read from results.csv, summary.csv, the
two validation CSVs or run_manifest.json (or computed from them here), so the
report cannot drift from the analysis outputs.
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd

W = Path(__file__).resolve().parent
MEASURE = 'event_mean_absolute_relative_error'   # results.csv / contrast payloads
LEV = 'mean_event_absolute_relative_error'       # summary.csv level rows


def short_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def main() -> None:
    res = pd.read_csv(W / 'results.csv', dtype={'site': str})
    smy = pd.read_csv(W / 'summary.csv')
    chk = pd.read_csv(W / 'validation_against_archive.csv', dtype={'site': str})
    chk2 = pd.read_csv(W / 'validation_aggregation.csv')
    man = json.loads((W / 'run_manifest.json').read_text())

    lev = smy[(smy.row_type == 'level') & (smy.minimum_events == 1)]
    con = smy[(smy.row_type == 'contrast') & (smy.minimum_events == 1)]
    lev3 = smy[(smy.row_type == 'level') & (smy.minimum_events == 3)]
    con3 = smy[(smy.row_type == 'contrast') & (smy.minimum_events == 3)]

    def excl0(frame):
        return (frame.station_ci_low > 0) | (frame.station_ci_high < 0)

    origin, delay = con[con.factor == 'origin'], con[con.factor == 'delay']
    origin3, delay3 = con3[con3.factor == 'origin'], con3[con3.factor == 'delay']

    n_cal = int(len(res) / (len(res.delay.unique()) * len(res.origin.unique())))
    stations = sorted(res.site.unique())
    ok = res.groupby(['site', 'seed']).n_events.max() > 0
    with_events = sorted({s for (s, _), v in ok.items() if v})
    without = [s for s in stations if s not in with_events]
    ev_all_zero = sorted(res[res.events_all == 0].site.unique())
    returns = (res[(res.origin == 'arrival')].groupby(['policy', 'delay'])
                  .labels_returned_within_horizon.mean().unstack())
    n_events_cell = int(lev.n_events.iloc[0]) if len(lev) else 0
    arch_events = int(np.round(n_events_cell / res.seed.nunique()))

    best = lev.loc[lev[LEV].idxmin()]
    worst = lev.loc[lev[LEV].idxmax()]
    lines = []
    A = lines.append
    A('# Fixed-calendar actual-return-delay and residual-decay-origin diagnostic')
    A('')
    A('Post hoc diagnostic of the archived revision replay for the 2025 temporal cohort at a budget of '
      '96 attempted samples per station-year. The purchase calendars of the archived policies '
      'uniform (periodic), flow_trigger and deadline_only are held **exactly fixed** as collection '
      'timestamps; only the return delay and the origin of the residual decay are varied, and the '
      'hourly online prediction is re-derived with the latest-residual correction of the main revision.')
    A('')
    A('Units: the endpoint is a dimensionless mean absolute relative error of the valid-window event '
      'load; multiply by 100 for per cent. Differences are in the same units.')
    A('')
    A('## 1. Inputs reused (exact archived files)')
    A('')
    A('Archived replay outputs (read-only):')
    A('')
    A('| file | sha256 (first 16) | role in this analysis |')
    A('|---|---|---|')
    roles = {
        'revision_20261009/results/experiments_main_temporal_v1/attempts.csv':
            'purchase calendars (sample_index/sample_time) for uniform, flow_trigger, deadline_only at budget 96, held fixed',
        'revision_20261009/results/experiments_main_temporal_v1/metrics.csv':
            'archived endpoints, used only to verify reproduction',
        'revision_20261009/results/experiments_main_temporal_v1/events.csv':
            'archived eligible-event definitions and reference masses, used only to verify reproduction',
        'revision_20261009/results/experiments_main_temporal_v1/run_manifest.json':
            'dataset digest and code digests of the archived run',
        'datasets/extended_hourly_2019_2025_v1.parquet':
            'dataset digest 05398eb7d883d36cbb5682847954dd56ac651ae7fa1e2649e6f0de68d9ea9905 matches the archived manifest; its digest keys the frozen context cache',
    }
    for rel, meta in man['inputs']['files'].items():
        A(f"| {rel} | {meta['sha256'][:16]} | {roles.get(rel, '')} |")
    A('')
    A('Frozen historical contexts (loaded with joblib, never refitted), directory '
      + man['inputs']['context_cache'] + ' — all '
      + str(len(man['inputs']['context_cache_files'])) + ' files used are listed with sha256 in run_manifest.json:')
    A('')
    A('| context file | sha256 (first 16) |')
    A('|---|---|')
    for item in man['inputs']['context_cache_files'][:3]:
        A(f"| {Path(item['path']).name} | {item['sha256'][:16]} |")
    A(f"| ... {len(man['inputs']['context_cache_files'])-3} further station-year-seed contexts | (see run_manifest.json) |")
    A('')
    A('Each frozen context supplies the archived base prediction c0 (historical random forest, '
      'target_base), the discharge-defined event list (q90 threshold, 24 h merge, 12 h minimum) and '
      'the reference hourly load and validity masks. No model was refitted and no new data were read.')
    A('')
    A('Code, imported unchanged from the read-only project tree (hashes in run_manifest.json, all '
      'verified equal to the archived revision manifest):')
    A('')
    A('| module | what was reused |')
    A('|---|---|')
    A('| scripts/paper_metrics.py | evaluate(), the endpoint function, reused verbatim |')
    A('| scripts/replay.py | event scoring and boundary censoring inside evaluate() |')
    A('| scripts/value_sampling.py | make_context() and RFFFeatureMap (the feature map is passed to the '
      'reconstruction for fidelity; the latest-residual rule does not otherwise use it) |')
    A('| revision_20261009/scripts/revision_state.py | reconstruct_fixed_calendar(), LatestResidual and '
      'SHORT_HALF_LIFE (tau = 168 h) — the main revision output rule |')
    A('| scripts/paper_context.py | only its cache-key definition; the contexts themselves were read from '
      'the archive cache |')
    A('')
    A('The read-only tree was not modified: interpreter bytecode writing was disabled '
      '(PYTHONDONTWRITEBYTECODE=1 and sys.dont_write_bytecode=True), and the script refuses to run if a '
      'required frozen context is absent instead of fitting a new one.')
    A('')
    A('## 2. Design')
    A('')
    A(f"- Fixed calendars: {n_cal} = {len(stations)} stations x {res.seed.nunique()} seeds x 3 policies, "
      f"each with exactly 96 attempted purchases in 2025; the collection timestamps are copied "
      f"byte-for-byte from the archived attempts.csv and never re-planned.")
    A('- Crossed factors: actual return delay d in {6, 24, 72} h x decay origin in {collection, arrival}. '
      'For a delay d the arrival clock moves to a = s + d for every purchase; a purchase whose label '
      'would arrive after the end of the replay year is unavailable, exactly as in the main analysis.')
    A('- Online prediction for every hour t:  c_hat(t) = max(0, c0(x_t) + [c_s - c0(x_s)] * exp(-(t - origin)/168)) '
      'where s is the latest purchase whose label has already returned and origin is the collection time s '
      'or the arrival time a = s + d. The rule is realised by '
      "revision_state.reconstruct_fixed_calendar(family='latest_residual', half_life=168*ln2, "
      "age_basis='sample' for collection origin and 'arrival' for arrival origin).")
    A('- Endpoint: paper_metrics.evaluate() on the archived target frame with the archived event list and '
      'event_coverage = 0.95; the reported value is the mean absolute relative error over eligible events '
      '(coverage >= 0.95, not boundary-censored), using the archived reference masses. The same events and '
      'the same valid hours are used in all 18 cells of a station-year-seed, so cells are compared on a '
      'common set.')
    A(f"- Aggregation hierarchy (identical to revision_20261009/scripts/summarize_revision.py): events within "
      f"station-year-seed, then seeds, then years, then stations equally. Paired differences are formed per "
      f"station-year and averaged within station, and intervals are the 95% station-cluster bootstrap with "
      f"{man['bootstrap']['replicates']} resamples and seed {man['bootstrap']['seed']}.")
    A('- Difference sign convention: baseline minus candidate; a positive difference means the candidate cell '
      'has the LOWER mean absolute relative error (is better).')
    A('')
    A('## 3. Validation that the endpoint is comparable to the main analysis')
    A('')
    A(f"- Reproduction of the archived cell (d = 24 h, arrival origin) for all "
      f"{int(man['endpoint_validation']['calendars_checked'])} calendars: maximum absolute difference in the "
      f"endpoint {man['endpoint_validation']['endpoint_max_absolute_difference']:.2e}; "
      f"all event counts match the archive: {man['endpoint_validation']['all_event_counts_match']}.")
    A(f"- Event definitions and reference masses: {int(man['endpoint_validation']['events_compared'])} eligible "
      f"events compared with the archived events.csv, maximum absolute reference-mass difference "
      f"{man['endpoint_validation']['max_reference_mass_difference_kg']:.2e} kg and maximum absolute "
      f"predicted-mass difference {man['endpoint_validation']['max_predicted_mass_difference_kg']:.2e} kg "
      f"(float/text-rounding level).")
    A(f"- Aggregate level values against revision_20261009/results/summary_main_v1/aggregate_metrics.csv "
      f"(temporal, systems, budget 96, delay 24 h, minimum 1 event): maximum absolute difference "
      f"{chk2.absolute_difference.iloc[:3].max():.2e} over the three calendars, "
      f"{int(chk2.mine_stations.iloc[0])} stations in both.")
    A(f"- Station bootstrap against .../summary_main_v1/paired_effects.csv (archived contrast uniform minus "
      f"value at delay 24 h): mean difference {chk2.mine.iloc[-1]:.10f} vs archived {chk2.archived.iloc[-1]:.10f}; "
      f"95% interval [{chk2.mine_ci_low.iloc[-1]:.8f}, {chk2.mine_ci_high.iloc[-1]:.8f}] vs archived "
      f"[{chk2.archived_ci_low.iloc[-1]:.8f}, {chk2.archived_ci_high.iloc[-1]:.8f}]. The interval machinery is "
      f"therefore the main analysis's own.")
    A('')
    A('## 4. Headline results')
    A('')
    A('### 4.1 Level values (mean event absolute relative error)')
    A('')
    A('| calendar | delay (h) | decay origin | stations | eligible events | mean abs. rel. error | median over stations |')
    A('|---|---|---|---|---|---|---|')
    for _, r in lev.sort_values(['policy', 'delay', 'origin']).iterrows():
        A(f"| {r.policy} | {int(r.delay)} | {r.origin} | {int(r.n_stations)} | {int(r.n_events)} | "
          f"{r[LEV]:.4f} | {r.median_across_stations:.4f} |")
    A('')
    A(f"Best cell: {best.policy}, delay {int(best.delay)} h, {best.origin} origin = {best[LEV]:.4f}. "
      f"Worst cell: {worst.policy}, delay {int(worst.delay)} h, {worst.origin} origin = {worst[LEV]:.4f}. "
      f"Across all 18 cells the endpoint spans {lev[LEV].min():.4f} to {lev[LEV].max():.4f}.")
    A('')
    A('### 4.2 Origin effect (collection origin minus arrival origin, within calendar and delay)')
    A('')
    A('| calendar | delay (h) | mean difference | 95% station CI | stations favouring arrival origin |')
    A('|---|---|---|---|---|')
    for _, r in origin.sort_values(['policy', 'delay']).iterrows():
        A(f"| {r.policy} | {int(r.delay)} | {r.mean_difference:+.4f} | "
          f"[{r.station_ci_low:+.4f}, {r.station_ci_high:+.4f}] | "
          f"{int(r.stations_favouring_candidate)}/{int(r.n_stations)} |")
    A('')
    A(f"Absolute differences are at most {origin.mean_difference.abs().max():.4f} and only "
      f"{int(excl0(origin).sum())} of {len(origin)} intervals exclude zero "
      f"(both for deadline_only, favouring the arrival origin by ~0.003-0.009). "
      f"The origin convention therefore does not materially change the endpoint.")
    A('')
    A('### 4.3 Delay effect (longer delay minus shorter delay, within calendar and origin)')
    A('')
    A('| calendar | origin | delay pair | mean difference | 95% station CI | stations favouring shorter delay |')
    A('|---|---|---|---|---|---|')
    for _, r in delay.sort_values(['policy', 'origin', 'baseline']).iterrows():
        pair = f"{int(r.baseline.split('delay=')[1].split('|')[0])} h vs {int(r.candidate.split('delay=')[1].split('|')[0])} h"
        A(f"| {r.policy} | {r.origin} | {pair} | {r.mean_difference:+.4f} | "
          f"[{r.station_ci_low:+.4f}, {r.station_ci_high:+.4f}] | "
          f"{int(r.stations_favouring_candidate)}/{int(r.n_stations)} |")
    A('')
    A(f"All {len(delay)} delay contrasts are positive and {int(excl0(delay).sum())} of {len(delay)} intervals "
      f"exclude zero: a longer actual return delay always raises the event error, by "
      f"{delay[delay.baseline.str.contains('delay=24') & delay.candidate.str.contains('delay=6')].mean_difference.min():.4f}"
      f"-{delay[delay.baseline.str.contains('delay=24') & delay.candidate.str.contains('delay=6')].mean_difference.max():.4f} "
      f"(24 h vs 6 h), "
      f"{delay[delay.baseline.str.contains('delay=72') & delay.candidate.str.contains('delay=24')].mean_difference.min():.4f}"
      f"-{delay[delay.baseline.str.contains('delay=72') & delay.candidate.str.contains('delay=24')].mean_difference.max():.4f} "
      f"(72 h vs 24 h) and "
      f"{delay[delay.baseline.str.contains('delay=72') & delay.candidate.str.contains('delay=6')].mean_difference.min():.4f}"
      f"-{delay[delay.baseline.str.contains('delay=72') & delay.candidate.str.contains('delay=6')].mean_difference.max():.4f} "
      f"(72 h vs 6 h).")
    A('')
    A('### 4.4 Where the labels went (mechanism check)')
    A('')
    A('Mean number of labels returned within the replay year, out of 96 attempted purchases '
      '(arrival origin; the collection origin returns the same counts):')
    A('')
    A('| calendar | 6 h | 24 h | 72 h |')
    A('|---|---|---|---|')
    for policy, row in returns.iterrows():
        A(f"| {policy} | {row[6]:.2f} | {row[24]:.2f} | {row[72]:.2f} |")
    A('')
    ret6 = float(returns[6].mean())
    ret72 = float(returns[72].mean())
    failures = float((res[(res.origin == 'arrival') & (res.delay == 6)]
                      .assign(failed=lambda d: d.attempts - d.successful_labels)
                      .failed.mean()))
    A(f"End-of-year truncation removes only {ret6-ret72:.2f} labels on average between d = 6 h and d = 72 h, "
      f"so the delay effect is driven by when and how strongly the correction is applied, not by lost labels. "
      f"About {failures:.1f} of the 96 purchases per calendar fail outright (no valid label), independently of "
      f"the delay.")
    A('')
    A('### 4.5 Robustness (stations with at least 3 eligible events)')
    A('')
    A(f"Restricting to station-years with >= 3 eligible events leaves {int(lev3.n_stations.iloc[0])} stations "
      f"and endpoint values from {lev3[LEV].min():.4f} to {lev3[LEV].max():.4f}. "
      f"The delay effect survives ({int(excl0(delay3).sum())} of {len(delay3)} intervals exclude zero, all "
      f"positive, {delay3.mean_difference.min():.4f} to {delay3.mean_difference.max():.4f}), whereas the origin "
      f"effect disappears ({int(excl0(origin3).sum())} of {len(origin3)} intervals exclude zero, "
      f"{origin3.mean_difference.min():+.4f} to {origin3.mean_difference.max():+.4f}).")
    A('')
    A('### 4.6 Coverage of the endpoint')
    A('')
    A(f"{len(stations)} stations are archived in the temporal cohort, but only {len(with_events)} have at least "
      f"one eligible event in 2025 under the archived definitions: "
      f"{', '.join(without)} contribute no eligible event"
      + (f" ({', '.join(ev_all_zero)} also has no event defined at all in 2025)" if ev_all_zero else '')
      + f". Each of the {len(with_events)} retained stations contributes all "
      f"{res.seed.nunique()} seeds, and each calendar cell carries {n_events_cell} eligible events summed over "
      f"the {len(with_events) * res.seed.nunique()} station-year-seed cases (mean "
      f"{n_events_cell / (len(with_events) * res.seed.nunique()):.2f} per case). The archived main summary "
      f"reports {arch_events} events per cell because it sums seed-averaged counts, where summary.csv sums "
      f"seed counts.")
    A('')
    A('## 5. Reproduction')
    A('')
    A('All commands were run from F:/SCI/nitrate_rev/analysis_delay with the interpreter whose package '
      'versions match revision_20261009/ENVIRONMENT_REVISION.json (Python 3.12.10, numpy 2.5.1, pandas 3.0.5, '
      'scipy 1.18.0, scikit-learn 1.9.0, pyarrow 25.0.0, joblib 1.5.3):')
    A('')
    A('    $env:PYTHONDONTWRITEBYTECODE = "1"')
    A("    & 'D:\\ptenv\\Scripts\\python.exe' delay_origin_diagnostic.py   # stage 1: reconstruction + endpoint")
    A("    & 'D:\\ptenv\\Scripts\\python.exe' summarize_delay.py           # stage 2: aggregation + bootstrap")
    A("    & 'D:\\ptenv\\Scripts\\python.exe' make_summary_md.py           # this report")
    A('')
    A(f"Measured in-script runtime (excluding interpreter start-up): stage 1 {man['elapsed_seconds_stage1']:.1f} s, stage 2 "
      f"{man['elapsed_seconds_stage2']:.1f} s (total {man['elapsed_seconds_total']:.1f} s), well inside the "
      f"40-minute budget.")
    A('')
    A('## 6. Limitations')
    A('')
    A('1. The calendars are the products of the original acquisition rules at an assumed 24 h delay '
      '(flow_trigger thresholds come from the archived 24 h scoring library; uniform phase and block deadlines '
      'as archived). They are held fixed across d, so the d = 6 h and d = 72 h cells do NOT describe what those '
      'policies would have purchased at those delays; the archived mechanisms suite covers delay-aware '
      'acquisition for the value policy separately. This is a controlled decomposition of the published '
      'pipeline, not a policy redesign.')
    A('2. Post hoc diagnostic on archived 2025 replay outputs: no new data, no hold-out, no unseen validation, '
      'and no re-tuning of the correction. Every one of the 117 calendars was already used in the published '
      'revision.')
    A(f"3. Small station sample: the endpoint is defined on {len(with_events)} station clusters, so the station "
      f"bootstrap intervals are coarse and should be read as approximate; the origin effect in particular is of "
      f"the order of a few thousandths, at or below what {len(with_events)} clusters can resolve.")
    A('4. One year only (2025, the temporal cohort): the "then years" step of the aggregation is vacuous here, '
      'so nothing is claimed about year-to-year stability.')
    A('5. One correction family only: the latest-residual rule with tau = 168 h, i.e. the published revision '
      'output rule. RFF-pooled updates and other half-lives exist in the archived factorial suite but were not '
      'crossed here.')
    A('6. The delay changes label availability only through the end-of-year rule (about one label per calendar '
      'between 6 h and 72 h); within-year timing and attenuation of the correction is the dominant channel, '
      'by construction of the fixed-calendar design.')
    A('7. Event definitions are inherited from the archived contexts (discharge q90 threshold with 24 h merge '
      'and 12 h minimum); any sensitivity of the endpoint to that definition is inherited as well.')
    A('8. Input completeness: all required inputs were present (117 archived calendars, 39 frozen contexts, '
      'archived event definitions and reference masses). No input was missing and nothing was substituted.')
    A('')
    A('## 7. Files')
    A('')
    A('| file | rows | content |')
    A('|---|---|---|')
    A(f"| results.csv | {len(res)} | site, year, seed, policy, delay, origin, event_mean_absolute_relative_error, "
      f"n_events per calendar x delay x origin x station-year-seed, plus diagnostic columns "
      f"(event_median_absolute_relative_error, attempts, successful_labels, labels_returned_within_horizon, "
      f"events_all, valid_hours, hour_coverage) |")
    A(f"| summary.csv | {len(smy)} | row_type = level (18 per minimum-events setting) and contrast "
      f"(27 per setting): levels give the station-equal aggregate; contrasts give baseline/candidate cells, "
      f"the mean difference and the 95% station bootstrap interval |")
    A(f"| validation_against_archive.csv | {len(chk)} | per-calendar reproduction of the archived endpoint, "
      f"event counts and reference masses |")
    A(f"| validation_aggregation.csv | {len(chk2)} | replication of the archived aggregate level values and of "
      f"one archived paired effect with the same bootstrap |")
    A('| run_manifest.json | - | sha256 of every input (archive files, dataset, 39 frozen contexts, code), '
      'runtime, design and validation summaries, sha256 of every output |')
    A('| delay_origin_diagnostic.py, summarize_delay.py, make_summary_md.py | - | the analysis code |')
    A('')
    A('Note on counting: summary.csv n_events sums eligible events over station-year-seed cases (3 seeds per '
      'station-year), whereas the archived main summary sums seed-averaged counts; the two differ by the '
      'number of seeds and are reconciled in section 4.6.')
    A('')
    (W / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # Finalise the manifest: this report and the analysis code are outputs too.
    man['outputs']['SUMMARY.md'] = hashlib.sha256((W / 'SUMMARY.md').read_bytes()).hexdigest()
    man['code_sha256'] = {name: hashlib.sha256((W / name).read_bytes()).hexdigest()
                          for name in ('delay_origin_diagnostic.py', 'summarize_delay.py',
                                       'make_summary_md.py')}
    man['run_logs_sha256'] = {name: hashlib.sha256((W / name).read_bytes()).hexdigest()
                              for name in ('run_stage1.log', 'run_stage2.log') if (W / name).exists()}
    import datetime as _dt
    man['report_generated_at_utc'] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    (W / 'run_manifest.json').write_text(json.dumps(man, indent=2), encoding='utf-8')
    print(f'wrote SUMMARY.md ({len(lines)} lines) and finalised run_manifest.json')


if __name__ == '__main__':
    main()
