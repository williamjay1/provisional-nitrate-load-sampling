"""Delayed, label-responsive sampling under a discounted Gaussian surrogate.

The RF prior and random-feature map are frozen before replay. Purchased labels
update a small residual model at arrival using their SAMPLE-TIME features. VOI
uses persistence forecasts of flow and known calendar only. Its variances are
uncalibrated design scores, not physical uncertainty or optimality guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Sequence
import numpy as np
import pandas as pd


VALUE_POLICIES = ("uniform", "flow_trigger", "q_uncertainty", "stratified_random",
                  "value", "fixed_calendar")
CONTEXT_NAMES = ("log_q", "change_6", "sin_doy", "cos_doy")
ATTEMPT_COLUMNS = ("sample_index", "sample_time", "arrival_index", "arrival_time",
                   "block", "label_success", "label_available_by_horizon",
                   "observed_mg_l", "reason", "measurement_variance_at_sample",
                   "prediction_at_sample", "query_score", "query_threshold")


def _hourly_time(time: pd.DatetimeIndex) -> pd.DatetimeIndex:
    time = pd.DatetimeIndex(time)
    if len(time) == 0 or time.tz is None:
        raise ValueError("A nonempty timezone-aware hourly calendar is required")
    time = time.tz_convert("UTC")
    if len(time) > 1 and not np.all((time[1:] - time[:-1]) == pd.Timedelta(hours=1)):
        raise ValueError("Calendar must be unique, complete and strictly hourly")
    return time


def _calendar(time: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    angle = 2 * np.pi * (time.dayofyear.to_numpy() - 1) / 365.25
    return np.sin(angle), np.cos(angle)


def make_context(time: pd.DatetimeIndex, q_cms: np.ndarray, q_scale: float) -> np.ndarray:
    """Four causal covariates; missing Q uses <=24 h forward fill then training median.

    Each replay starts with a common cold feature state. No concentration or
    concentration-validity column is accepted. Inputs are never modified.
    """
    time = _hourly_time(time)
    q = np.asarray(q_cms, dtype=float)
    if q.shape != (len(time),) or not np.isfinite(q_scale) or q_scale <= 0:
        raise ValueError("Invalid flow array or training-only q_scale")
    s = pd.Series(np.where(np.isfinite(q) & (q >= 0), q, np.nan))
    filled = s.ffill(limit=24).fillna(q_scale).to_numpy()
    log_q = np.log1p(filled / q_scale)
    old = np.r_[np.repeat(log_q[0], 6), log_q][0:len(log_q)]
    sin_day, cos_day = _calendar(time)
    return np.column_stack((log_q, log_q - old, sin_day, cos_day))


@dataclass(frozen=True)
class RFFFeatureMap:
    mean: np.ndarray
    scale: np.ndarray
    frequencies: np.ndarray

    @classmethod
    def fit(cls, contexts_train: np.ndarray, n_frequencies: int = 4,
            length_scale: float = 1.0, seed: int = 41) -> "RFFFeatureMap":
        x = np.asarray(contexts_train, dtype=float)
        if x.ndim != 2 or x.shape[1] != 4 or len(x) < 2 or not np.isfinite(x).all():
            raise ValueError("Finite training contexts with shape (n,4) required")
        if n_frequencies < 1 or not np.isfinite(length_scale) or length_scale <= 0:
            raise ValueError("Invalid random-feature specification")
        mean = x.mean(axis=0)
        scale = np.maximum(x.std(axis=0), 1e-6)
        w = np.random.default_rng(seed).normal(size=(4, n_frequencies)) / length_scale
        for a in (mean, scale, w):
            a.setflags(write=False)
        return cls(mean, scale, w)

    @property
    def dimension(self) -> int:
        return 1 + 2 * self.frequencies.shape[1]

    @property
    def signature(self) -> str:
        payload = b"".join(np.asarray(a, dtype="<f8").tobytes()
                           for a in (self.mean, self.scale, self.frequencies))
        return hashlib.sha256(payload).hexdigest()

    def transform(self, contexts: np.ndarray) -> np.ndarray:
        x = np.asarray(contexts, dtype=float)
        if x.ndim == 1:
            x = x[None, :]
        if x.ndim != 2 or x.shape[1] != 4 or not np.isfinite(x).all():
            raise ValueError("Finite contexts with shape (n,4) required")
        phase = ((x - self.mean) / self.scale) @ self.frequencies
        normalization = np.sqrt(self.frequencies.shape[1])
        return np.column_stack((np.ones(len(x)), np.cos(phase) / normalization,
                                np.sin(phase) / normalization))


def _load_prefix(current_time: pd.Timestamp, context_history: np.ndarray, *,
                 feature_map: RFFFeatureMap, q_scale: float, delay_hours: int,
                 lookahead_hours: int) -> np.ndarray:
    """Persistence-Q future load vectors; history must end at current_time.

    Row h is sum over h target hours beginning at current_time + delay.
    Only the last seven supplied observations and deterministic future calendar
    are used. No measured future flow enters the forecast.
    """
    history = np.asarray(context_history, dtype=float)[-7:]
    if len(history) == 0:
        raise ValueError("At least one observed context is required")
    offsets = np.arange(delay_hours, delay_hours + lookahead_hours)
    future = pd.DatetimeIndex(current_time + pd.to_timedelta(offsets, unit="h"))
    log_q = float(history[-1, 0])
    changes = np.zeros(lookahead_hours)
    for k, offset in enumerate(offsets):
        if offset < 6:
            historic_index = max(0, len(history) - 1 + int(offset) - 6)
            changes[k] = log_q - history[historic_index, 0]
    sin_day, cos_day = _calendar(future)
    context = np.column_stack((np.full(lookahead_hours, log_q), changes, sin_day, cos_day))
    q_forecast = q_scale * np.expm1(log_q)
    weighted_z = feature_map.transform(context) * (q_forecast * 3600.0 / 1000.0)
    return np.vstack((np.zeros(feature_map.dimension), np.cumsum(weighted_z, axis=0)))


@dataclass(frozen=True)
class ReferenceLibrary:
    z_query: np.ndarray
    load_prefix: np.ndarray
    q_cms: np.ndarray
    flow_scores: np.ndarray
    contexts: np.ndarray
    times: pd.DatetimeIndex
    training_end_utc: pd.Timestamp
    q_scale: float
    delay_hours: int
    lookahead_hours: int
    feature_signature: str


def build_reference_library(time_train: pd.DatetimeIndex, q_train: np.ndarray, *,
                            feature_map: RFFFeatureMap, q_scale: float,
                            delay_hours: int = 24, lookahead_hours: int = 72,
                            max_contexts: int = 96, seed: int = 41) -> ReferenceLibrary:
    """Draw a fixed training-only context bank; never select by target-year scores."""
    time = _hourly_time(time_train)
    q = np.asarray(q_train, dtype=float)
    contexts = make_context(time, q, q_scale)
    good = np.flatnonzero(np.isfinite(q) & (q >= 0))
    if max_contexts < 1 or len(good) == 0 or delay_hours < 1 or lookahead_hours < 1:
        raise ValueError("Invalid or empty reference library")
    if len(good) > max_contexts:
        good = np.sort(np.random.default_rng(seed).choice(good, max_contexts, replace=False))
    x = contexts[good]
    z = feature_map.transform(x)
    prefixes = np.stack([_load_prefix(time[i], contexts[max(0, i-6):i+1],
                       feature_map=feature_map, q_scale=q_scale, delay_hours=delay_hours,
                       lookahead_hours=lookahead_hours) for i in good])
    flow = np.expm1(x[:, 0]) * (1 + np.maximum(x[:, 1], 0))
    arrays = (z, prefixes, q[good].copy(), flow, x.copy())
    for a in arrays:
        a.setflags(write=False)
    return ReferenceLibrary(*arrays, time[good], time[-1], float(q_scale),
                            int(delay_hours), int(lookahead_hours), feature_map.signature)


@dataclass(frozen=True)
class ValueSamplingConfig:
    noise_variance: float = 1.0
    prior_variance: float = 1.0
    delay_hours: int = 24
    min_spacing_hours: int = 24
    candidate_interval_hours: int = 6
    lookahead_hours: int = 72
    half_life_hours: float = 720.0
    noise_adaptation_rate: float = 0.1
    noise_min_factor: float = 0.1
    noise_max_factor: float = 10.0
    threshold_quantile: float = 0.85
    uniform_phase: float | None = None

    def validate(self) -> None:
        for v in (self.noise_variance, self.prior_variance, self.half_life_hours):
            if not np.isfinite(v) or v <= 0:
                raise ValueError("Noise, prior variance and half-life must be positive")
        for v in (self.delay_hours, self.min_spacing_hours, self.candidate_interval_hours,
                  self.lookahead_hours):
            if not isinstance(v, (int, np.integer)) or v < 1:
                raise ValueError("Hour intervals must be positive integers")
        if not 0 <= self.noise_adaptation_rate <= 1 or not 0 <= self.threshold_quantile <= 1:
            raise ValueError("Adaptation rate and quantile must lie in [0,1]")
        if not 0 < self.noise_min_factor <= 1 <= self.noise_max_factor:
            raise ValueError("Noise bounds must contain the initial variance")
        if self.uniform_phase is not None and not 0 <= self.uniform_phase <= 1:
            raise ValueError("Uniform phase must lie in [0,1]")


@dataclass(frozen=True)
class PublicPending:
    sample_index: int
    arrival_index: int
    z_sample: np.ndarray
    measurement_variance: float
    prior_prediction_at_sample: float
    online_prediction_at_sample: float


class DiscountedResidualModel:
    """Low-dimensional precision update with immutable sample-time provenance."""
    def __init__(self, dimension: int, config: ValueSamplingConfig):
        config.validate()
        self.config = config
        self.prior_precision = np.eye(dimension) / config.prior_variance
        self.precision = self.prior_precision.copy()
        self.information = np.zeros(dimension)
        self.noise_variance = float(config.noise_variance)
        self.time_index = 0
        self.observations_received = 0
        self._covariance = None

    def decay(self, hours: int | float) -> float:
        if hours < 0:
            raise ValueError("Cannot propagate backward")
        return float(np.exp2(-hours / self.config.half_life_hours))

    def advance_to(self, index: int) -> None:
        if index < self.time_index:
            raise ValueError("Cannot rewrite past residual state")
        if index != self.time_index:
            discount = self.decay(index - self.time_index)
            self.precision = self.prior_precision + discount * (self.precision - self.prior_precision)
            self.information *= discount
            self.time_index = index
            self._covariance = None

    @property
    def covariance(self) -> np.ndarray:
        if self._covariance is None:
            self._covariance = np.linalg.inv(self.precision)
            self._covariance = (self._covariance + self._covariance.T) * 0.5
        return self._covariance

    def predict(self, z: np.ndarray) -> tuple[float, float]:
        pz = self.covariance @ z
        return float(pz @ self.information), max(0., float(z @ pz))

    def observe(self, pending: PublicPending, concentration: float) -> None:
        if self.time_index < pending.arrival_index:
            raise ValueError("Unreleased label cannot update the model")
        if not np.isfinite(concentration):
            raise ValueError("Nonfinite label")
        weight = self.decay(self.time_index - pending.sample_index) / pending.measurement_variance
        residual = float(concentration) - pending.prior_prediction_at_sample
        self.precision += weight * np.outer(pending.z_sample, pending.z_sample)
        self.information += weight * pending.z_sample * residual
        self._covariance = None
        self.observations_received += 1
        innovation = float(concentration) - pending.online_prediction_at_sample
        rate = self.config.noise_adaptation_rate
        updated = (1 - rate) * self.noise_variance + rate * innovation**2
        self.noise_variance = float(np.clip(updated,
            self.config.noise_variance * self.config.noise_min_factor,
            self.config.noise_variance * self.config.noise_max_factor))

    def projected_covariance(self, hours: int, pending: Sequence[PublicPending] = ()) -> np.ndarray:
        end = self.time_index + hours
        a = self.prior_precision + self.decay(hours) * (self.precision - self.prior_precision)
        for item in pending:
            if item.arrival_index <= self.time_index:
                raise ValueError("Pending list must not include already returned labels")
            if item.arrival_index <= end:
                weight = self.decay(end - item.sample_index) / item.measurement_variance
                a += weight * np.outer(item.z_sample, item.z_sample)
        p = np.linalg.inv(a)
        return (p + p.T) * 0.5


def variance_reduction(covariance: np.ndarray, z_query: np.ndarray,
                       load_vector: np.ndarray, effective_noise_variance: float) -> float:
    """Sherman-Morrison score for one discounted Gaussian pseudo-observation."""
    pz = covariance @ z_query
    denominator = effective_noise_variance + float(z_query @ pz)
    if denominator <= 0 or not np.isfinite(denominator):
        raise ValueError("Invalid information denominator")
    return max(0., float(load_vector @ pz)**2 / denominator)


def _library_value_scores(p: np.ndarray, library: ReferenceLibrary,
                          horizon: int, effective_noise: float) -> np.ndarray:
    pz = library.z_query @ p
    numerator = np.sum(library.load_prefix[:, horizon, :] * pz, axis=1)**2
    denominator = effective_noise + np.sum(library.z_query * pz, axis=1)
    return np.maximum(numerator / denominator, 0)


@dataclass
class ValueReplayResult:
    attempts: pd.DataFrame
    online_prediction: np.ndarray
    latent_variance: np.ndarray
    query_trace: pd.DataFrame


def run_value_replay(time: pd.DatetimeIndex, q_cms: np.ndarray,
                     base_prediction: np.ndarray, concentration_hidden: np.ndarray,
                     label_valid_hidden: np.ndarray, *, feature_map: RFFFeatureMap,
                     reference_library: ReferenceLibrary, q_scale: float, policy: str,
                     budget: int, config: ValueSamplingConfig | None = None, seed: int = 41,
                     preplanned_indices: np.ndarray | None = None) -> ValueReplayResult:
    """Replay one policy with a shared causal residual reconstruction model.

    Trigger thresholds compare current risk with TRAINING contexts evaluated
    under the SAME current covariance, avoiding a stale absolute-score cutoff.
    All policies use the same candidate grid and spacing. fixed_calendar permits
    a predeclared global schedule; others use one attempt per calendar quota.
    At budget=0, return the unchanged RF prior and empty attempt records.
    """
    config = config or ValueSamplingConfig()
    config.validate()
    time = _hourly_time(time)
    n = len(time)
    if policy not in VALUE_POLICIES or not isinstance(budget, (int, np.integer)) or budget < 0:
        raise ValueError("Unknown policy or invalid budget")
    q = np.asarray(q_cms, dtype=float)
    base = np.asarray(base_prediction, dtype=float)
    hidden = np.asarray(concentration_hidden, dtype=float)
    hidden_valid = np.asarray(label_valid_hidden, dtype=bool)
    if any(a.shape != (n,) for a in (q, base, hidden, hidden_valid)) or not np.isfinite(base).all():
        raise ValueError("Aligned arrays and finite RF predictions required")
    if reference_library.training_end_utc >= time[0]:
        raise ValueError("Reference library must end before the replay horizon")
    if reference_library.delay_hours != config.delay_hours or reference_library.lookahead_hours < config.lookahead_hours:
        raise ValueError("Reference library delay/lookahead does not match config")
    if (not np.isclose(reference_library.q_scale, q_scale)
            or reference_library.z_query.shape[1] != feature_map.dimension
            or reference_library.feature_signature != feature_map.signature):
        raise ValueError("Reference library scale/features do not match replay")
    context = make_context(time, q, q_scale)
    z_all = feature_map.transform(context)
    candidate_grid = np.arange(0, n, config.candidate_interval_hours)
    candidate_mask = np.zeros(n, dtype=bool)
    candidate_mask[candidate_grid] = True
    rng = np.random.default_rng(seed)
    fixed = set()
    planned, deadlines = {}, {}
    if budget:
        if budget > len(candidate_grid):
            raise ValueError("Budget exceeds candidate capacity")
        boundaries = np.linspace(0, n, budget + 1, dtype=int)
        block_of = np.minimum(np.searchsorted(boundaries[1:], np.arange(n), side="right"), budget-1)
        if policy == "fixed_calendar":
            raw_plan = np.asarray([] if preplanned_indices is None else preplanned_indices)
            if raw_plan.ndim != 1 or len(raw_plan) != budget or not np.issubdtype(raw_plan.dtype, np.integer):
                raise ValueError("fixed_calendar requires exactly budget integer indices")
            plan = np.sort(raw_plan.astype(int))
            if (len(np.unique(plan)) != budget or plan[0] < 0 or plan[-1] >= n
                    or np.any(plan % config.candidate_interval_hours)
                    or np.any(np.diff(plan) < config.min_spacing_hours)):
                raise ValueError("Fixed calendar violates grid, uniqueness, horizon or spacing")
            fixed = set(map(int, plan))
        else:
            if n / budget < config.min_spacing_hours + config.candidate_interval_hours:
                raise ValueError("Quota blocks too short to guarantee spacing and equal budget")
            phase = config.uniform_phase
            if phase is None:
                phase = {41: .25, 73: .5, 109: .75}.get(seed, .5)
            for block in range(budget):
                eligible = candidate_grid[(candidate_grid >= boundaries[block]) & (candidate_grid < boundaries[block+1])]
                if len(eligible) == 0:
                    raise ValueError("Quota block without a candidate")
                deadlines[block] = int(eligible[-1])
                if policy == "uniform":
                    target = boundaries[block] + phase * (boundaries[block+1] - boundaries[block] - 1)
                    planned[block] = int(eligible[np.argmin(np.abs(eligible-target))])
                elif policy == "stratified_random":
                    planned[block] = int(rng.choice(eligible))
    else:
        block_of = np.zeros(n, dtype=int)

    used = set()
    last_attempt = -10**12
    state = DiscountedResidualModel(feature_map.dimension, config)
    pending_public: list[PublicPending] = []
    oracle_arrivals: dict[int, list[tuple[PublicPending, float, bool]]] = {}
    records, trace = [], []
    online, variance = np.empty(n), np.empty(n)
    for i in range(n):
        state.advance_to(i)
        arrived = oracle_arrivals.pop(i, [])
        for item, observed, valid in arrived:
            if valid:
                state.observe(item, observed)
        pending_public = [item for item in pending_public if item.arrival_index > i]
        mean, latent = state.predict(z_all[i])
        online[i] = max(0., float(base[i] + mean))
        variance[i] = latent
        score, threshold = np.nan, np.nan
        horizon = max(0, min(config.lookahead_hours, n-i-config.delay_hours))
        is_candidate = bool(candidate_mask[i] and budget > 0)
        if is_candidate:
            if policy == "flow_trigger":
                score = float(np.expm1(context[i, 0]) * (1 + max(context[i, 1], 0)))
                threshold = float(np.quantile(reference_library.flow_scores, config.threshold_quantile))
            elif policy == "q_uncertainty":
                score = float(q_scale * np.expm1(context[i, 0]) * np.sqrt(latent))
                lib_variance = np.einsum("ij,jk,ik->i", reference_library.z_query,
                                         state.covariance, reference_library.z_query)
                lib_scores = reference_library.q_cms * np.sqrt(np.maximum(lib_variance, 0))
                threshold = float(np.quantile(lib_scores, config.threshold_quantile))
            elif policy == "value":
                p = state.projected_covariance(config.delay_hours, pending_public)
                effective_noise = state.noise_variance / state.decay(config.delay_hours)
                prefix = _load_prefix(time[i], context[max(0, i-6):i+1],
                    feature_map=feature_map, q_scale=q_scale, delay_hours=config.delay_hours,
                    lookahead_hours=horizon)
                score = variance_reduction(p, z_all[i], prefix[-1], effective_noise)
                library_scores = _library_value_scores(p, reference_library, horizon, effective_noise)
                threshold = float(np.quantile(library_scores, config.threshold_quantile))
        trace.append({"time_utc": time[i], "is_candidate": is_candidate,
                      "query_score": score, "query_threshold": threshold,
                      "noise_variance": state.noise_variance, "latent_variance": latent,
                      "residual_mean": mean, "received_labels": state.observations_received,
                      "pending_labels": len(pending_public), "lookahead_effective_hours": horizon})
        if not is_candidate or i-last_attempt < config.min_spacing_hours:
            continue
        block = int(block_of[i])
        if policy == "fixed_calendar":
            trigger, deadline = i in fixed, False
        else:
            if block in used:
                continue
            deadline = i == deadlines[block]
            if policy in ("uniform", "stratified_random"):
                trigger = i >= planned[block]
            else:
                trigger = bool(np.isfinite(score) and score > 0 and score >= threshold)
        if not (trigger or deadline):
            continue
        used.add(block)
        last_attempt = i
        item = PublicPending(i, i+config.delay_hours, z_all[i].copy(), state.noise_variance,
                             float(base[i]), float(online[i]))
        # Hidden quality/value are inspected by the environment only AFTER action.
        observed = float(hidden[i])
        valid = bool(hidden_valid[i] and np.isfinite(observed) and observed >= 0)
        pending_public.append(item)  # Includes failed labels until scheduled arrival.
        oracle_arrivals.setdefault(item.arrival_index, []).append((item, observed, valid))
        records.append({"sample_index": i, "sample_time": time[i], "arrival_index": item.arrival_index,
                        "arrival_time": time[i] + pd.Timedelta(hours=config.delay_hours),
                        "block": block, "label_success": valid,
                        "label_available_by_horizon": valid and item.arrival_index < n,
                        "observed_mg_l": observed if valid else np.nan,
                        "reason": "threshold_or_calendar" if trigger else "block_deadline",
                        "measurement_variance_at_sample": item.measurement_variance,
                        "prediction_at_sample": item.online_prediction_at_sample,
                        "query_score": score, "query_threshold": threshold})
    if len(records) != budget:
        raise RuntimeError("Schedule failed to spend its nominal attempt budget")
    attempts = pd.DataFrame.from_records(records, columns=ATTEMPT_COLUMNS)
    for name in ("label_success", "label_available_by_horizon"):
        attempts[name] = attempts[name].astype(bool)
    attempts["sample_index"] = attempts.sample_index.astype(int)
    return ValueReplayResult(attempts, online, variance, pd.DataFrame(trace))
