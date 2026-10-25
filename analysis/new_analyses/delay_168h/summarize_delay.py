"""Aggregation and paired station bootstrap for the delay/origin diagnostic.

Replicates the hierarchy and the station bootstrap of the main revision summary
(revision_20261009/scripts/summarize_revision.py): endpoint per station-year-seed
is the mean over eligible events, then seeds, then years, then stations equally;
paired contrasts are formed at station level and resampled over stations with
10,000 draws and seed 271828.
"""
from __future__ import annotations
import argparse, json, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd

OUTDIR = Path(__file__).resolve().parent
MEASURE = 'event_mean_absolute_relative_error'
DELAYS = (6, 24, 72, 168)
ORIGINS = ('collection', 'arrival')
POLICIES = ('uniform', 'flow_trigger', 'deadline_only')
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 271828
DIFFERENCE_DEFINITION = ('mean over stations of station-level (baseline minus candidate); '
                         'positive values mean the candidate cell has the LOWER mean '
                         'absolute relative error')


def sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2 ** 20), b''):
            h.update(block)
    return h.hexdigest()


def station_interval(differences: pd.DataFrame, cluster: str = 'site'):
    """Exact station-cluster bootstrap of summarize_revision.interval."""
    groups = [g.difference.to_numpy(float)
              for _, g in differences.dropna(subset=['difference', cluster]).groupby(cluster)]
    if len(groups) < 2:
        return np.nan, np.nan
    sums = np.array([g.sum() for g in groups])
    counts = np.array([len(g) for g in groups])
    draws = np.random.default_rng(BOOTSTRAP_SEED).integers(len(groups),
                                                           size=(BOOTSTRAP_REPLICATES, len(groups)))
    values = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    low, high = np.quantile(values, [.025, .975])
    return float(low), float(high)


def cell_label(policy: str, delay, origin: str) -> str:
    return f'{policy}|delay={delay}|origin={origin}'


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--outdir', type=Path, default=OUTDIR)
    a = p.parse_args()
    clock = time.perf_counter()

    res = pd.read_csv(a.outdir / 'results.csv', dtype={'site': str})
    res['cell'] = [cell_label(p_, d_, o_) for p_, d_, o_ in
                   zip(res.policy, res.delay, res.origin)]
    # Hierarchy step 2: seeds within station-year (results.csv already holds step 1).
    station_year = (res.groupby(['site', 'year', 'cell'], as_index=False)
                       .agg(**{MEASURE: (MEASURE, 'mean'),
                               'events_eligible': ('n_events', 'mean'),
                               'events_total': ('n_events', 'sum'),
                               'seeds': ('seed', 'nunique')}))
    if not (station_year.seeds == res.seed.nunique()).all():
        raise RuntimeError('A station-year-cell is missing seeds')

    summary, tables = [], []
    level_rows = []
    for minimum_events in (1, 3):
        primary = station_year.loc[station_year.events_eligible >= minimum_events].copy()
        for policy in POLICIES:
            for delay in DELAYS:
                for origin in ORIGINS:
                    cell = cell_label(policy, delay, origin)
                    f = primary.loc[primary.cell == cell]
                    if not len(f):
                        continue
                    # Hierarchy step 3 (years) then step 4 (equal stations).
                    stations = f.groupby('site')[MEASURE].mean()
                    level_rows.append(dict(
                        row_type='level', minimum_events=minimum_events, policy=policy,
                        delay=delay, origin=origin, factor='', baseline='', candidate='',
                        n_stations=int(len(stations)),
                        n_station_years=int(len(f)),
                        n_events=int(f.events_total.sum()),
                        mean_event_absolute_relative_error=float(stations.mean()),
                        median_across_stations=float(stations.median()),
                        sd_across_stations=float(stations.std(ddof=1)) if len(stations) > 1 else np.nan,
                        mean_over_station_year_cells=float(f[MEASURE].mean()),
                        mean_difference=np.nan, station_ci_low=np.nan, station_ci_high=np.nan,
                        stations_favouring_candidate=np.nan,
                        bootstrap_replicates=BOOTSTRAP_REPLICATES, bootstrap_seed=BOOTSTRAP_SEED,
                        difference_definition=''))
        wide = primary.pivot_table(index=['site', 'year'], columns='cell', values=MEASURE)
        contrasts = []
        for policy in POLICIES:
            for delay in DELAYS:  # origin effect at fixed calendar and delay
                contrasts.append(dict(factor='origin', policy=policy, delay=delay, origin='',
                                      baseline=cell_label(policy, delay, 'collection'),
                                      candidate=cell_label(policy, delay, 'arrival'),
                                      contrast=f'origin: collection vs arrival at delay={delay}h'))
            for origin in ORIGINS:  # delay effect at fixed calendar and origin
                for longer, shorter in ((72, 6), (72, 24), (24, 6)):
                    contrasts.append(dict(factor='delay', policy=policy, delay='', origin=origin,
                                          baseline=cell_label(policy, longer, origin),
                                          candidate=cell_label(policy, shorter, origin),
                                          contrast=f'delay: {longer}h vs {shorter}h at origin={origin}'))
        for c in contrasts:
            if c['baseline'] not in wide.columns or c['candidate'] not in wide.columns:
                continue
            w = wide[[c['baseline'], c['candidate']]].dropna()
            if not len(w):
                continue
            delta = (w[c['baseline']] - w[c['candidate']]).rename('difference').reset_index()
            z = delta.groupby('site', as_index=False).difference.mean()
            low, high = station_interval(z)
            summary.append(dict(row_type='contrast', minimum_events=minimum_events, **c,
                                n_stations=int(len(z)), n_station_years=int(len(delta)),
                                n_events=int(primary.loc[primary.cell.isin([c['baseline'], c['candidate']])]
                                             .events_total.sum()),
                                mean_event_absolute_relative_error=np.nan,
                                median_across_stations=np.nan, sd_across_stations=np.nan,
                                mean_over_station_year_cells=np.nan,
                                mean_difference=float(z.difference.mean()),
                                station_ci_low=low, station_ci_high=high,
                                stations_favouring_candidate=int((z.difference > 0).sum()),
                                bootstrap_replicates=BOOTSTRAP_REPLICATES,
                                bootstrap_seed=BOOTSTRAP_SEED,
                                difference_definition=DIFFERENCE_DEFINITION))
    summary = level_rows + summary
    out = pd.DataFrame(summary)
    columns = ['row_type', 'minimum_events', 'policy', 'delay', 'origin', 'factor', 'contrast',
               'baseline', 'candidate', 'n_stations', 'n_station_years', 'n_events',
               'mean_event_absolute_relative_error', 'median_across_stations',
               'sd_across_stations', 'mean_over_station_year_cells', 'mean_difference',
               'station_ci_low', 'station_ci_high', 'stations_favouring_candidate',
               'bootstrap_replicates', 'bootstrap_seed', 'difference_definition']
    out = out[columns]
    out.to_csv(a.outdir / 'summary.csv', index=False)

    # ---- markdown tables and machine-readable headline numbers -----------------
    lev = out[(out.row_type == 'level') & (out.minimum_events == 1)]
    con = out[(out.row_type == 'contrast') & (out.minimum_events == 1)]
    lines = ['### Level values (primary: minimum 1 eligible event)', '',
             '| calendar | delay (h) | decay origin | stations | station-years | events | mean event abs. rel. error | median over stations |',
             '|---|---|---|---|---|---|---|---|']
    for _, r in lev.sort_values(['policy', 'delay', 'origin']).iterrows():
        lines.append(f"| {r.policy} | {r.delay} | {r.origin} | {r.n_stations} | {r.n_station_years} | "
                     f"{r.n_events} | {r.mean_event_absolute_relative_error:.4f} | {r.median_across_stations:.4f} |")
    lines += ['', '### Paired station-bootstrap contrasts (primary)', '',
              '| factor | calendar | stratum | baseline | candidate | stations | mean difference | 95% station CI | stations favouring candidate |',
              '|---|---|---|---|---|---|---|---|---|']
    for _, r in con.sort_values(['factor', 'policy', 'delay', 'origin']).iterrows():
        stratum = f"delay={r.delay}h" if r.factor == 'origin' else f"origin={r.origin}"
        lines.append(f"| {r.factor} | {r.policy} | {stratum} | {r.baseline} | {r.candidate} | "
                     f"{r.n_stations} | {r.mean_difference:+.4f} | "
                     f"[{r.station_ci_low:+.4f}, {r.station_ci_high:+.4f}] | "
                     f"{r.stations_favouring_candidate}/{r.n_stations} |")
    (a.outdir / '_summary_tables.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

    numbers = {
        'primary_minimum_events': 1,
        'calendar_count': int(lev.policy.nunique()),
        'station_count': int(lev.n_stations.max()),
        'station_year_count': int(lev.n_station_years.max()),
        'cells': int(len(lev)),
        'level_mean_error_min': float(lev.mean_event_absolute_relative_error.min()),
        'level_mean_error_max': float(lev.mean_event_absolute_relative_error.max()),
        'origin_contrasts_total': int(len(con[con.factor == 'origin'])),
        'origin_contrasts_ci_excluding_zero': int(((con.factor == 'origin')
                                                   & ((con.station_ci_low > 0) | (con.station_ci_high < 0))).sum()),
        'delay_contrasts_total': int(len(con[con.factor == 'delay'])),
        'delay_contrasts_ci_excluding_zero': int(((con.factor == 'delay')
                                                  & ((con.station_ci_low > 0) | (con.station_ci_high < 0))).sum()),
        'origin_mean_difference_abs_max': float(con[con.factor == 'origin'].mean_difference.abs().max()),
        'delay_mean_difference_abs_max': float(con[con.factor == 'delay'].mean_difference.abs().max()),
        'minimum_events_3_levels': out[(out.row_type == 'level')
                                       & (out.minimum_events == 3)].shape[0],
    }
    (a.outdir / '_numbers.json').write_text(json.dumps(numbers, indent=2), encoding='utf-8')

    # ---- independent replication of the archived main-analysis aggregation -----
    # (a) level values for the archived delay-24 arrival-origin cell, and
    # (b) one archived paired contrast, to prove that the station bootstrap used
    #     here reproduces the main analysis.
    arch_dir = Path('D:/MLWork/NitrateAdaptiveSampling_20261005/revision_20261009/results')
    agg = pd.read_csv(arch_dir / 'summary_main_v1' / 'aggregate_metrics.csv')
    pe = pd.read_csv(arch_dir / 'summary_main_v1' / 'paired_effects.csv')
    mets = pd.read_csv(arch_dir / 'experiments_main_temporal_v1' / 'metrics.csv', dtype={'site': str})
    checks2 = []
    arch_level = agg[(agg.stage == 'temporal') & (agg.experiment == 'systems') & (agg.budget == BUDGET_)
                     & (agg.minimum_events == 1) & (agg.delay_hours == 24)
                     & (agg.scenario == 'delay_aware_pending')
                     & (agg.reconstructor == 'latest_residual_tau168_arrival')]
    mine_level = lev[(lev.delay == 24) & (lev.origin == 'arrival')]
    for policy in POLICIES:
        r1 = arch_level.loc[arch_level.policy == policy]
        r2 = mine_level.loc[mine_level.policy == policy]
        if len(r1) != 1 or len(r2) != 1:
            raise RuntimeError(f'Archived aggregation check not unique for {policy}')
        r1, r2 = r1.iloc[0], r2.iloc[0]
        checks2.append(dict(check='level_value_vs_archived_main_summary', subject=policy,
                            mine=float(r2.mean_event_absolute_relative_error),
                            archived=float(r1.event_mean_absolute_relative_error),
                            absolute_difference=abs(float(r2.mean_event_absolute_relative_error)
                                                    - float(r1.event_mean_absolute_relative_error)),
                            mine_stations=int(r2.n_stations), archived_stations=int(r1.stations),
                            note='archived events column sums seed-averaged counts; '
                                 'summary.csv n_events sums seed counts'))
    def archived_cells(frame, policy, budget, scenario):
        f = frame[(frame.stage == 'temporal') & (frame.policy == policy) & (frame.budget == budget)
                  & (frame.scenario == scenario) & (frame.delay_hours == 24)]
        if policy != 'no_new_labels':
            f = f[f.reconstructor == 'latest_residual_tau168_arrival']
        return f
    parts = []
    for policy, budget, scenario in [('uniform', BUDGET_, 'delay_aware_pending'),
                                     ('value', BUDGET_, 'delay_aware_pending'),
                                     ('no_new_labels', 0, 'historical_only')]:
        parts.append(archived_cells(mets, policy, budget, scenario))
    mm2 = pd.concat(parts, ignore_index=True)
    sy2 = (mm2.groupby(['site', 'year', 'policy'], as_index=False)
              .agg(**{MEASURE: (MEASURE, 'mean'), 'events_eligible': ('events_eligible', 'mean')}))
    sy2 = sy2[sy2.events_eligible >= 1]
    w2 = sy2.pivot_table(index=['site', 'year'], columns='policy', values=MEASURE)
    d2 = (w2['uniform'] - w2['value']).rename('difference').reset_index()
    z2 = d2.groupby('site', as_index=False).difference.mean()
    lo2, hi2 = station_interval(z2)
    arch_pe = pe[(pe.stage == 'temporal') & (pe.experiment == 'systems') & (pe.budget == BUDGET_)
                 & (pe.minimum_events == 1) & (pe.delay_hours == 24)
                 & (pe.measure == MEASURE) & (pe.baseline == 'uniform')
                 & (pe.scenario == 'delay_aware_pending')]
    if len(arch_pe) != 1:
        raise RuntimeError('Archived paired-effect row not unique')
    arch_pe = arch_pe.iloc[0]
    checks2.append(dict(check='station_bootstrap_vs_archived_paired_effect',
                        subject='uniform minus value (delay 24 h, budget 96)',
                        mine=float(z2.difference.mean()), archived=float(arch_pe.mean_difference),
                        absolute_difference=abs(float(z2.difference.mean()) - float(arch_pe.mean_difference)),
                        mine_stations=int(len(z2)), archived_stations=int(arch_pe.stations),
                        mine_ci_low=lo2, mine_ci_high=hi2,
                        archived_ci_low=float(arch_pe.station_ci_low),
                        archived_ci_high=float(arch_pe.station_ci_high),
                        ci_absolute_differences=[abs(lo2 - float(arch_pe.station_ci_low)),
                                                 abs(hi2 - float(arch_pe.station_ci_high))],
                        note='same estimator, seed and replicate count as summarize_revision.py'))
    checks2 = pd.DataFrame(checks2)
    checks2.to_csv(a.outdir / 'validation_aggregation.csv', index=False)
    agg_ok = bool((checks2.absolute_difference < 1e-12).all())
    ci_flat = [v for item in checks2.ci_absolute_differences.dropna() for v in item]
    boot_ok = bool((max(ci_flat) if ci_flat else 0.0) < 1e-12)
    if not agg_ok or not boot_ok:
        raise RuntimeError('Aggregation or bootstrap does not reproduce the archived main analysis')

    stage1 = json.loads((a.outdir / '_stage1_meta.json').read_text())
    manifest = dict(
        analysis='fixed-calendar actual-return-delay and residual-decay-origin diagnostic (budget 96)',
        analysis_status='post hoc diagnostic on archived replay outputs; not unseen validation',
        started_at_utc=stage1['started_at_utc'],
        completed_at_utc=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds_stage1=stage1['elapsed_seconds'],
        elapsed_seconds_stage2=time.perf_counter() - clock,
        elapsed_seconds_total=(stage1['elapsed_seconds'] + time.perf_counter() - clock),
        python=sys.version,
        inputs=dict(archive=stage1['archive'], context_cache=stage1['context_cache'],
                    dataset_sha256=stage1['data_sha256'],
                    files=stage1['input_sha256'], code=stage1['code_sha256']),
        design=dict(calendars=list(POLICIES), delays_hours=list(DELAYS), decay_origins=list(ORIGINS),
                    budget=BUDGET_, correction='latest_residual tau=168 h (half-life 168*ln2)',
                    base_prediction='archived frozen historical-forest target_base'),
        endpoint=dict(name=MEASURE, aggregation='events within station-year-seed, then seeds, '
                      'then years, then stations equally',
                      event_eligibility='paper_metrics.evaluate, coverage>=0.95, boundary-censored'),
        bootstrap=dict(replicates=BOOTSTRAP_REPLICATES, seed=BOOTSTRAP_SEED, cluster='station',
                       statistic='ratio of summed station differences to summed station counts',
                       difference=DIFFERENCE_DEFINITION),
        endpoint_validation=stage1['endpoint_validation'],
        outputs={},
    )
    if set(res.year) != {2025}:
        raise RuntimeError('This diagnostic is defined for the archived 2025 temporal cohort only')
    ctx_dir = Path(stage1['context_cache'])
    cache_files = []
    for site, seed in sorted({(s, int(sd)) for s, sd in zip(res.site, res.seed)}):
        f = ctx_dir / f'{site}_2025_{seed}.joblib'
        cache_files.append({'path': str(f), 'sha256': sha256(f), 'bytes': f.stat().st_size})
    if len(cache_files) != res.groupby(['site', 'seed']).ngroups:
        raise RuntimeError('Context cache listing incomplete')
    manifest['inputs']['context_cache_files'] = cache_files
    manifest['aggregation_validation'] = dict(
        archived_main_summary='revision_20261009/results/summary_main_v1',
        level_values_match=agg_ok, station_bootstrap_matches=boot_ok,
        checks=checks2.to_dict('records'))
    for name in ('results.csv', 'validation_against_archive.csv', 'validation_aggregation.csv',
                 'summary.csv', '_summary_tables.md', '_numbers.json'):
        manifest['outputs'][name] = sha256(a.outdir / name)
    (a.outdir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(numbers, indent=2), flush=True)
    print(out[(out.minimum_events == 1)].to_string(index=False), flush=True)


BUDGET_ = 96
if __name__ == '__main__':
    main()

