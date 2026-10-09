"""Strictly causal sampling replay. Hidden concentrations live only in the environment.

This is an exploratory pilot, not a physical sampler or a calibrated uncertainty model.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from scipy.linalg import qr


POLICIES = ("uniform", "flow_trigger", "rf_disagreement", "rf_load_disagreement", "historical_design", "historical_qr", "historical_dopt")


def seasonal_day(stamp) -> np.ndarray:
    """Align month/day to leap reference year, avoiding leap-year phase shifts."""
    return pd.DatetimeIndex(pd.to_datetime("2000-" + pd.DatetimeIndex(stamp).strftime("%m-%d"))).dayofyear.to_numpy() - 1


def causal_features(frame: pd.DataFrame, q_scale: float) -> pd.DataFrame:
    """Only current/past discharge and calendar; no concentration or future masks."""
    q_raw = frame["q_at_time_cms"].astype(float).where(lambda s: s >= 0)
    q = q_raw.ffill(limit=24).fillna(q_scale)
    logq = np.log1p(q / max(q_scale, 1e-6))
    stamp = pd.DatetimeIndex(frame["time_utc"])
    angle = 2 * np.pi * (stamp.dayofyear.to_numpy() - 1) / 365.25
    out = pd.DataFrame(index=frame.index)
    out["log_q"] = logq
    for lag in (1, 6, 24, 72):
        old = logq.shift(lag).fillna(logq.iloc[0])
        out[f"log_q_lag{lag}"] = old
        out[f"change_{lag}"] = logq - old
    out["q_ewm24"] = logq.ewm(span=24, adjust=False).mean()
    out["q_missing"] = q_raw.isna().astype(float)
    out["sin_doy"] = np.sin(angle)
    out["cos_doy"] = np.cos(angle)
    return out.astype(float)


def tree_predictions(model, features: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    values = features.to_numpy()
    each = np.asarray([tree.predict(values) for tree in model.estimators_])
    return np.maximum(each.mean(axis=0), 0), each.std(axis=0)


def flow_query_score(features: pd.DataFrame, q_scale: float) -> np.ndarray:
    q_ratio = np.expm1(features["log_q"].to_numpy())
    rise = np.maximum(features["change_6"].to_numpy(), 0)
    return q_ratio * (1 + rise)


def historical_design_days(train: pd.DataFrame, max_rank: int = 8) -> tuple[np.ndarray, dict, dict]:
    """Past-only seasonal low-rank design, explicitly NOT original DSS reproduction.

    Daily standardized historical Q and NOx trajectories are columns. Training
    gaps are interpolated only to build a historical design basis, never labels.
    A regularized leverage score provides a preplanned calendar within quota blocks.
    """
    columns = []
    years = []
    for year, part in train.groupby(pd.DatetimeIndex(train.time_utc).year):
        days = seasonal_day(part.time_utc) + 1
        for variable, approved in (("q_at_time_cms", "q_sample_reference_ok"),
                                   ("nox_at_time_mg_l", "nox_sample_reference_ok")):
            x = part[variable].copy()
            if approved in part:
                x = x.where(part[approved].fillna(False))
            series = pd.Series(x.to_numpy(), index=days).groupby(level=0).mean().reindex(range(1, 367))
            if series.notna().sum() < 180:
                continue
            series = series.interpolate(limit_direction="both")
            scale = series.std()
            if not np.isfinite(scale) or scale < 1e-8:
                continue
            columns.append((series.to_numpy() - series.mean()) / scale)
            years.append(int(year))
    if not columns:
        return np.ones(366), {"status": "no_sufficient_history", "rank": 0}, {"historical_qr": np.arange(366), "historical_dopt": np.arange(366)}
    matrix = np.column_stack(columns)
    u, s, _ = np.linalg.svd(matrix, full_matrices=False)
    energy = np.cumsum(s**2) / np.sum(s**2)
    rank = min(int(np.searchsorted(energy, .85) + 1), max_rank, len(s))
    basis = u[:, :rank]
    leverage = np.sum(basis**2, axis=1)
    # Oversampling QR rule follows SSPOR (without its optional local refinement).
    _, _, pivot = qr(basis @ basis.T, pivoting=True, mode="economic")
    inverse = np.eye(rank) * 1e6
    chosen = []
    for _ in range(366):
        gains = np.einsum("ij,jk,ik->i", basis, inverse, basis)
        gains[chosen] = -np.inf
        k = int(np.argmax(gains))
        chosen.append(k)
        vector = basis[k]
        vv = inverse @ vector
        inverse -= np.outer(vv, vv) / (1 + vector @ vv)
    return leverage, {"status": "past_only_calendar_adaptation", "rank": rank,
                      "columns": matrix.shape[1], "years": sorted(set(years)),
                      "explained_training_energy": float(energy[rank-1])}, {"historical_qr": pivot, "historical_dopt": np.array(chosen)}


def planned_calendar_indices(time: pd.DatetimeIndex, ordered_days: np.ndarray, budget: int) -> np.ndarray:
    """Prior-year design plus target-year calendar, always at 12:00 UTC."""
    day = seasonal_day(time)
    available = {int(day[i]): int(i) for i in np.flatnonzero(time.hour == 12)}
    planned = [available[int(d)] for d in ordered_days if int(d) in available][:budget]
    return np.sort(planned)


@dataclass
class ReplayResult:
    attempts: pd.DataFrame
    online_prediction: np.ndarray
    retrospective_prediction: np.ndarray
    interpolation_prediction: np.ndarray


def replay_sampling(*, time: pd.DatetimeIndex, base_prediction: np.ndarray,
                    query_scores: np.ndarray, threshold: float, concentration_hidden: np.ndarray,
                    label_valid_hidden: np.ndarray, policy: str, budget: int,
                    delay_hours: int, min_spacing_hours: int,
                    historical_day_score: np.ndarray | None = None,
                    preplanned_indices: np.ndarray | None = None,
                    correction_decay_hours: int = 168) -> ReplayResult:
    """One budget token per predetermined calendar block; label failures cost tokens.

    Action order is: receive due labels -> predict -> choose -> environment records
    hidden result to be returned after delay. No target availability in decisions.
    Models/thresholds must be learned entirely before `time[0]`.
    """
    if policy not in POLICIES:
        raise ValueError(policy)
    n = len(time)
    if n < budget or budget <= 0 or delay_hours < 1:
        raise ValueError("Invalid replay horizon, budget, or delay")
    boundaries = np.linspace(0, n, budget + 1, dtype=int)
    block_of = np.searchsorted(boundaries[1:], np.arange(n), side="right")
    block_of = np.minimum(block_of, budget - 1)
    planned = {}
    global_calendar = set([] if preplanned_indices is None else map(int, preplanned_indices))
    is_global_calendar = policy in ("historical_qr", "historical_dopt")
    if is_global_calendar and len(global_calendar) != budget:
        raise ValueError("Global calendar must contain exactly budget dates")
    for b in range(budget):
        start, stop = boundaries[b:b+2]
        if policy == "uniform":
            planned[b] = (int(start) + int(stop) - 1) // 2
        elif policy == "historical_design":
            if historical_day_score is None:
                raise ValueError("Historical policy needs past-only day scores")
            score = historical_day_score[seasonal_day(time[start:stop])]
            # Past-derived day scores and calendar only; no target-year values.
            planned[b] = int(start + np.argmax(score))

    used = np.zeros(budget, dtype=bool)
    last_attempt = -10**9
    records = []
    arrivals: dict[int, list[tuple[int, float]]] = {}
    last_residual, last_arrival = 0., None
    online = np.empty(n)
    for i in range(n):
        for sample_i, observed in arrivals.get(i, []):
            last_residual = observed - base_prediction[sample_i]
            last_arrival = i
        correction = 0. if last_arrival is None else last_residual * np.exp(-(i - last_arrival) / correction_decay_hours)
        online[i] = max(0., float(base_prediction[i] + correction))
        b = int(block_of[i])
        if (not is_global_calendar and used[b]) or i - last_attempt < min_spacing_hours:
            continue
        if is_global_calendar and i not in global_calendar:
            continue
        deadline = i == boundaries[b+1] - 1
        if is_global_calendar:
            trigger = True
        elif policy in ("uniform", "historical_design"):
            trigger = i >= planned[b]
        else:
            trigger = bool(np.isfinite(query_scores[i]) and query_scores[i] >= threshold)
        if not (trigger or deadline):
            continue
        if not is_global_calendar:
            used[b] = True
        last_attempt = i
        observed = concentration_hidden[i]
        valid = bool(label_valid_hidden[i] and np.isfinite(observed) and observed >= 0)
        arrival_i = i + delay_hours
        if valid:
            arrivals.setdefault(arrival_i, []).append((i, float(observed)))
        records.append({"sample_index": i, "sample_time": time[i], "arrival_index": arrival_i,
                        "arrival_time": time[i] + pd.Timedelta(hours=delay_hours),
                        "block": b, "label_success": valid, "label_available_by_horizon": valid and arrival_i < n,
                        "observed_mg_l": float(observed) if valid else np.nan,
                        "reason": "threshold_or_calendar" if trigger else "block_deadline"})

    attempts = pd.DataFrame.from_records(records)
    returned = attempts.loc[attempts.label_available_by_horizon]
    retrospective = np.array(base_prediction, copy=True)
    interpolation = np.array(base_prediction, copy=True)
    if len(returned):
        idx = returned.sample_index.to_numpy(dtype=int)
        obs = returned.observed_mg_l.to_numpy(dtype=float)
        residual = obs - base_prediction[idx]
        retrospective = np.maximum(base_prediction + np.interp(np.arange(n), idx, residual), 0)
        interpolation = np.maximum(np.interp(np.arange(n), idx, obs), 0)
    return ReplayResult(attempts, online, retrospective, interpolation)


def define_events(q: np.ndarray, threshold: float, merge_gap: int = 24,
                  minimum_hours: int = 12) -> list[tuple[int, int]]:
    high = np.isfinite(q) & (q >= threshold)
    ix = np.flatnonzero(high)
    if len(ix) == 0:
        return []
    # An unobserved Q interval cannot establish hydrological continuity.
    missing_prefix = np.r_[0, np.cumsum(~np.isfinite(q))]
    gaps_have_missing = (missing_prefix[ix[1:]] - missing_prefix[ix[:-1]+1]) > 0
    cuts = np.flatnonzero((np.diff(ix) > merge_gap + 1) | gaps_have_missing) + 1
    groups = np.split(ix, cuts)
    return [(int(group[0]), int(group[-1] + 1)) for group in groups
            if group[-1] + 1 - group[0] >= minimum_hours]


def evaluate(frame: pd.DataFrame, prediction: np.ndarray, events: list[tuple[int, int]],
             attempts: pd.DataFrame, event_coverage: float) -> tuple[dict, list[dict]]:
    valid = frame.valid_hour.fillna(False).to_numpy(dtype=bool, copy=True)
    ref_load = frame.load_kg.to_numpy(dtype=float)
    volume = frame.observed_volume_m3.to_numpy(dtype=float)
    valid &= np.isfinite(ref_load) & np.isfinite(volume) & (volume >= 0)
    predicted_load = prediction * volume * .001
    if not np.isfinite(prediction).all():
        raise ValueError("Nonfinite prediction cannot silently disappear from scoring")
    truth_total = float(np.nansum(ref_load[valid]))
    pred_total = float(np.nansum(predicted_load[valid]))
    rows = []
    samples = attempts.sample_index.to_numpy(dtype=int)
    successful_samples = attempts.loc[attempts.label_success.astype(bool), "sample_index"].to_numpy(dtype=int)
    q = frame.q_at_time_cms.to_numpy(dtype=float)
    for j, (start, stop) in enumerate(events):
        coverage = float(valid[start:stop].mean())
        boundary_uncertain = (start == 0 or stop == len(frame)
                              or not np.isfinite(q[start-1]) or not np.isfinite(q[stop]))
        eligible = coverage >= event_coverage and not boundary_uncertain
        mask = valid[start:stop]
        ref = float(np.nansum(ref_load[start:stop][mask]))
        pred = float(np.nansum(predicted_load[start:stop][mask]))
        rows.append({"event_id": j, "start_time": frame.time_utc.iloc[start],
                     "end_time": frame.time_utc.iloc[stop-1] + pd.Timedelta(hours=1),
                     "hours": stop-start, "coverage": coverage, "eligible": eligible,
                     "boundary_uncertain": boundary_uncertain,
                     "reference_valid_window_load_kg": ref, "predicted_valid_window_load_kg": pred,
                     "relative_error": (pred-ref)/ref if eligible and ref > 1e-8 else np.nan,
                     "sample_attempts": int(((samples >= start) & (samples < stop)).sum()),
                     "successful_samples": int(((successful_samples >= start) & (successful_samples < stop)).sum()),
                     "q_peak_cms": float(np.nanmax(frame.q_at_time_cms.to_numpy()[start:stop]))})
    ev = pd.DataFrame(rows)
    abs_errors = ev.relative_error.abs().dropna().to_numpy() if len(ev) else np.array([])
    sample_truth = frame.nox_at_time_mg_l.to_numpy(dtype=float)
    sample_valid = frame.nox_sample_reference_ok.fillna(False).to_numpy(dtype=bool) & np.isfinite(sample_truth)
    stats = {"hours": len(frame), "valid_hours": int(valid.sum()), "hour_coverage": float(valid.mean()),
             "reference_valid_window_load_kg": truth_total, "predicted_valid_window_load_kg": pred_total,
             "valid_window_relative_bias": (pred_total-truth_total)/truth_total if truth_total > 0 else np.nan,
             "concentration_mae_mg_l": float(np.mean(np.abs(prediction[sample_valid]-sample_truth[sample_valid]))) if sample_valid.any() else np.nan,
             "events_all": len(events), "events_eligible": int(len(abs_errors)),
             "event_median_absolute_relative_error": float(np.median(abs_errors)) if len(abs_errors) else np.nan,
             "event_mean_absolute_relative_error": float(np.mean(abs_errors)) if len(abs_errors) else np.nan,
             "event_missed_fraction": float((ev.loc[ev.eligible, "sample_attempts"] == 0).mean()) if len(ev) and ev.eligible.any() else np.nan,
             "all_event_missed_fraction": float((ev.sample_attempts == 0).mean()) if len(ev) else np.nan,
             "all_event_no_usable_label_fraction": float((ev.successful_samples == 0).mean()) if len(ev) else np.nan,
             "events_boundary_uncertain": int(ev.boundary_uncertain.sum()) if len(ev) else 0,
             "attempts": len(attempts), "successful_samples": int(attempts.label_success.sum()),
             "returned_by_horizon": int(attempts.label_available_by_horizon.sum())}
    return stats, rows
