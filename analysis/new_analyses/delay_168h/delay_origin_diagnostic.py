"""Fixed-calendar, actual-return-delay and residual-decay-origin diagnostic.

Post hoc analysis of the archived temporal cohort (2025) at budget 96 attempted
samples per year. Purchase calendars (collection timestamps) for the archived
policies uniform / flow_trigger / deadline_only are held EXACTLY fixed; only the
return delay d and the decay origin are varied when the hourly online
prediction is re-derived with the latest-residual rule of the main revision

    c_hat(t) = max(0, c0(x_t) + [c_s - c0(x_s)] * exp(-(t - origin)/168))

with s the latest successfully returned purchase, origin = collection time s or
arrival time a = s + d, and c0 the frozen archived historical-forest base
prediction. No new data and no new calibration are used.

All archived inputs are read-only. Bytecode writing is disabled so that the
read-only project tree is not touched.
"""
from __future__ import annotations
import argparse, hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True

import numpy as np
import pandas as pd

ROOT = Path('D:/MLWork/NitrateAdaptiveSampling_20261005')
REV = ROOT / 'revision_20261009'
ARCHIVE = REV / 'results' / 'experiments_main_temporal_v1'
OUTDIR = Path(__file__).resolve().parent

sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(REV / 'scripts'))
from paper_metrics import evaluate                      # noqa: E402  (reused endpoint)
from value_sampling import RFFFeatureMap, make_context  # noqa: E402
from revision_state import (reconstruct_fixed_calendar, SHORT_HALF_LIFE)  # noqa: E402

import joblib  # noqa: E402

POLICIES = ('uniform', 'flow_trigger', 'deadline_only')
DELAYS = (6, 24, 72, 168)
ORIGINS = ('collection', 'arrival')
BUDGET = 96
AGE_BASIS = {'collection': 'sample', 'arrival': 'arrival'}
EVENT_COVERAGE = .95

REUSED_CODE = ['scripts/paper_context.py', 'scripts/replay.py', 'scripts/paper_metrics.py',
               'scripts/value_sampling.py', 'revision_20261009/scripts/revision_state.py']
REUSED_DATA = ['revision_20261009/results/experiments_main_temporal_v1/attempts.csv',
               'revision_20261009/results/experiments_main_temporal_v1/metrics.csv',
               'revision_20261009/results/experiments_main_temporal_v1/events.csv',
               'revision_20261009/results/experiments_main_temporal_v1/run_manifest.json',
               'datasets/extended_hourly_2019_2025_v1.parquet']


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(2 ** 20), b''):
            h.update(block)
    return h.hexdigest()


def build_delayed_attempts(cal: pd.DataFrame, delay: int, n_hours: int) -> pd.DataFrame:
    """Hold collection timestamps fixed; move only the return (arrival) clock.

    Failed purchases never return, and a label that would arrive after the end
    of the replay year is unavailable, exactly as in the main analysis.
    """
    out = cal.copy()
    out['arrival_index'] = out.sample_index.to_numpy(int) + delay
    out['arrival_time'] = out.sample_time + pd.Timedelta(hours=delay)
    out['delay_hours'] = delay
    out['label_available_by_horizon'] = (out.label_success.astype(bool)
                                         & (out.arrival_index < n_hours))
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--archive', type=Path, default=ARCHIVE)
    p.add_argument('--outdir', type=Path, default=OUTDIR)
    p.add_argument('--data-sha', default=None,
                   help='dataset sha256 recorded by the archived manifest')
    a = p.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()

    manifest = json.loads((a.archive / 'run_manifest.json').read_text())
    data_sha = a.data_sha or manifest['data_sha256']
    # The historical-context cache directory is keyed by data digest and by the
    # digest of paper_context.py + replay.py; the latter must still match.
    code_digest = hashlib.sha256((ROOT / 'scripts/paper_context.py').read_bytes()
                                 + (ROOT / 'scripts/replay.py').read_bytes()).hexdigest()[:12]
    CTX = ROOT / 'cache' / 'paper_contexts' / f'{data_sha[:12]}_{code_digest}'

    code_hashes = {}
    for rel in REUSED_CODE:
        h = sha256(ROOT / rel)
        code_hashes[rel] = {'sha256': h,
                            'matches_archived_manifest': manifest['code_sha256'].get(rel) == h
                            if rel in manifest['code_sha256'] else None}
    data_hashes = {}
    for rel in REUSED_DATA:
        f = ROOT / rel
        data_hashes[rel] = {'sha256': sha256(f), 'bytes': f.stat().st_size,
                            'exists': True}

    attempts = pd.read_csv(a.archive / 'attempts.csv', dtype={'site': str})
    metrics = pd.read_csv(a.archive / 'metrics.csv', dtype={'site': str})
    events_arch = pd.read_csv(a.archive / 'events.csv', dtype={'site': str})
    attempts['time_utc'] = pd.to_datetime(attempts.sample_time, utc=True)
    attempts['sample_time'] = attempts.time_utc

    sel = attempts[(attempts.budget == BUDGET) & (attempts.policy.isin(POLICIES))]
    groups = (sel.groupby(['site', 'year', 'seed', 'policy'], sort=True)
                 .size().reset_index(name='rows'))
    if not (groups.rows == BUDGET).all():
        raise RuntimeError('An archived calendar does not contain exactly 96 attempts')
    print(f'[stage1] calendars: {len(groups)} (site-year-seed-policy), '
          f'{sel.site.nunique()} stations, years {sorted(sel.year.unique())}, '
          f'seeds {sorted(sel.seed.unique())}', flush=True)

    rows, checks = [], []
    for gi, key in enumerate(groups.to_dict('records'), start=1):
        site, year, seed, policy = key['site'], int(key['year']), int(key['seed']), key['policy']
        cal = (sel[(sel.site == site) & (sel.year == year) & (sel.seed == seed)
                   & (sel.policy == policy)].sort_values('sample_index').reset_index(drop=True))
        cal = cal[['sample_index', 'sample_time', 'block', 'label_success', 'observed_mg_l',
                   'reason', 'forced_deadline']]
        if len(set(cal.sample_index)) != BUDGET or np.any(np.diff(cal.sample_index.to_numpy(int)) < 24):
            raise RuntimeError(f'Archived calendar invariant violated: {key}')

        ctx_path = CTX / f'{site}_{year}_{seed}.joblib'
        if not ctx_path.exists():
            raise FileNotFoundError(f'Archived historical context missing: {ctx_path}')
        ctx = joblib.load(ctx_path)
        if ctx.get('status') != 'ready':
            raise RuntimeError(f'Context not ready: {ctx_path} ({ctx.get("status")})')
        target = ctx['target']
        hist = ctx['history']
        n_hours = len(target)
        base = np.asarray(ctx['target_base'], dtype=float)
        noise_variance = float(ctx['audit']['noise_variance_forward_mse'])

        ht = pd.DatetimeIndex(hist.time_utc)
        tt = pd.DatetimeIndex(target.time_utc)
        qh = hist.q_at_time_cms.to_numpy(float)
        qt = target.q_at_time_cms.to_numpy(float)
        xh = make_context(ht, qh, ctx['q_scale'])
        fmap = RFFFeatureMap.fit(xh[np.isfinite(qh) & (qh >= 0)], n_frequencies=4, seed=seed)
        z = fmap.transform(make_context(tt, qt, ctx['q_scale']))

        arch_ev = events_arch[(events_arch.site == site) & (events_arch.seed == seed)
                              & (events_arch.policy == policy) & (events_arch.budget == BUDGET)
                              & (events_arch.delay_hours == 24)]
        for delay in DELAYS:
            delayed = build_delayed_attempts(cal, delay, n_hours)
            for origin in ORIGINS:
                pred = reconstruct_fixed_calendar(base, z, delayed, family='latest_residual',
                                                  half_life=SHORT_HALF_LIFE,
                                                  age_basis=AGE_BASIS[origin],
                                                  noise_variance=noise_variance)
                stats, ev_rows = evaluate(target, pred, ctx['events'], delayed, EVENT_COVERAGE)
                rows.append(dict(site=site, year=year, seed=seed, policy=policy, delay=delay,
                                 origin=origin,
                                 event_mean_absolute_relative_error=stats['event_mean_absolute_relative_error'],
                                 n_events=stats['events_eligible'],
                                 event_median_absolute_relative_error=stats['event_median_absolute_relative_error'],
                                 attempts=stats['attempts'],
                                 successful_labels=stats['successful_samples'],
                                 labels_returned_within_horizon=stats['returned_by_horizon'],
                                 events_all=stats['events_all'],
                                 valid_hours=stats['valid_hours'],
                                 hour_coverage=stats['hour_coverage']))
                if delay == 24 and origin == 'arrival':
                    ref = metrics[(metrics.site == site) & (metrics.seed == seed)
                                  & (metrics.policy == policy) & (metrics.budget == BUDGET)
                                  & (metrics.delay_hours == 24)
                                  & (metrics.scenario == 'delay_aware_pending')
                                  & (metrics.reconstructor == 'latest_residual_tau168_arrival')]
                    if len(ref) != 1:
                        raise RuntimeError(f'Archived metric row not unique: {key}')
                    ref = ref.iloc[0]
                    mine = stats['event_mean_absolute_relative_error']
                    both_nan = not (np.isfinite(mine) or np.isfinite(ref.event_mean_absolute_relative_error))
                    diff = 0.0 if both_nan else abs(mine - ref.event_mean_absolute_relative_error)
                    ev = pd.DataFrame(ev_rows)
                    if not len(ev):
                        # A station-year-seed with no defined events has no rows to compare.
                        ev = pd.DataFrame(columns=['event_id', 'eligible',
                                                   'reference_valid_window_load_kg',
                                                   'predicted_valid_window_load_kg',
                                                   'relative_error'])
                    ev['eligible'] = ev.eligible.astype(bool)
                    mine_ev = ev.loc[ev.eligible, ['event_id', 'reference_valid_window_load_kg',
                                                   'predicted_valid_window_load_kg', 'relative_error']]
                    aa = arch_ev.copy()
                    aa = aa[aa.eligible.astype(str).str.lower().isin(['true', '1'])]
                    mm = mine_ev.merge(aa, on='event_id', how='outer', suffixes=('_mine', '_arch'))
                    if len(mm):
                        mass = float(np.nanmax(np.abs(mm.reference_valid_window_load_kg_mine
                                                      - mm.reference_valid_window_load_kg_arch)))
                        pred_d = float(np.nanmax(np.abs(mm.predicted_valid_window_load_kg_mine
                                                        - mm.predicted_valid_window_load_kg_arch)))
                    else:
                        # A station-year-seed without eligible events has nothing to
                        # compare; the count check below still requires agreement.
                        mass, pred_d = np.nan, np.nan
                    checks.append(dict(site=site, year=year, seed=seed, policy=policy,
                                       archived_events_eligible=int(ref.events_eligible),
                                       recomputed_events_eligible=int(stats['events_eligible']),
                                       archived_endpoint=float(ref.event_mean_absolute_relative_error),
                                       recomputed_endpoint=float(mine),
                                       absolute_difference=float(diff),
                                       endpoint_matches_archive=bool(diff < 1e-12
                                                                     or (np.isnan(mine) and np.isnan(ref.event_mean_absolute_relative_error))),
                                       matched_events=len(mm),
                                       every_archived_event_matched=bool(len(mm) == int(stats['events_eligible'])
                                                                         == int(ref.events_eligible)),
                                       max_reference_mass_difference_kg=mass,
                                       max_predicted_mass_difference_kg=pred_d,
                                       reference_masses_match=bool(np.isnan(mass) or mass < 1e-9),
                                       predictions_match=bool(np.isnan(pred_d) or pred_d < 1e-9),
                                       calendar_attempts=int(len(cal)),
                                       minimum_spacing_hours=int(np.diff(cal.sample_index.to_numpy(int)).min())))
        if gi % 5 == 0 or gi == len(groups):
            print(f'[stage1] {gi}/{len(groups)} calendars done '
                  f'({time.perf_counter()-clock:.1f}s)', flush=True)

    res = pd.DataFrame(rows).sort_values(['policy', 'delay', 'origin', 'site', 'seed']).reset_index(drop=True)
    chk = pd.DataFrame(checks)
    res.to_csv(a.outdir / 'results.csv', index=False)
    chk.to_csv(a.outdir / 'validation_against_archive.csv', index=False)

    failures = int((~chk.endpoint_matches_archive).sum())
    if failures:
        raise RuntimeError(f'{failures} calendars do not reproduce the archived endpoint')
    if not bool(chk.reference_masses_match.all()) or not bool(chk.predictions_match.all()):
        raise RuntimeError('Event definitions / reference masses do not match the archive')
    if not bool(chk.every_archived_event_matched.all()):
        raise RuntimeError('Event bookkeeping differs from the archived events.csv')

    stage1 = dict(started_at_utc=started, completed_at_utc=datetime.now(timezone.utc).isoformat(),
                  elapsed_seconds=time.perf_counter() - clock,
                  archive=str(a.archive), context_cache=str(CTX),
                  data_sha256=data_sha, code_sha256=code_hashes, input_sha256=data_hashes,
                  calendars=int(len(groups)), result_rows=int(len(res)),
                  endpoint_validation=dict(
                      calendars_checked=int(len(chk)),
                      endpoint_max_absolute_difference=float(chk.absolute_difference.max()),
                      all_event_counts_match=bool(chk.every_archived_event_matched.all()),
                      all_endpoints_match_archive=bool(chk.endpoint_matches_archive.all()),
                      max_reference_mass_difference_kg=float(chk.max_reference_mass_difference_kg.max()),
                      max_predicted_mass_difference_kg=float(chk.max_predicted_mass_difference_kg.max()),
                      events_compared=int(chk.matched_events.sum())),
                  outputs={'results.csv': sha256(a.outdir / 'results.csv'),
                           'validation_against_archive.csv': sha256(a.outdir / 'validation_against_archive.csv')})
    (a.outdir / '_stage1_meta.json').write_text(json.dumps(stage1, indent=2), encoding='utf-8')
    print(json.dumps({k: stage1[k] for k in ('calendars', 'result_rows', 'elapsed_seconds',
                                             'endpoint_validation')}, indent=2), flush=True)


if __name__ == '__main__':
    main()

