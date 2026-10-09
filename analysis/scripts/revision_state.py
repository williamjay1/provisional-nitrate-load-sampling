"""Post-result revision replay; frozen original implementations are imported, not edited.

Acquisition keeps an explicitly named RFF covariance model. Published predictions
may instead use a latest-returned-residual updater. Its sample-time prediction
is the innovation reference for acquisition noise adaptation, so this is a full
closed-loop system, not reconstruction of calendars produced by another system.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from value_sampling import (ValueSamplingConfig, DiscountedResidualModel, PublicPending,
    ReferenceLibrary, ValueReplayResult, make_context, _hourly_time, _load_prefix,
    _library_value_scores, variance_reduction, ATTEMPT_COLUMNS)

SHORT_HALF_LIFE = 168. * np.log(2.)


class AgeResidualModel(DiscountedResidualModel):
    """Same RFF model, with sample-age versus arrival-age discounting isolated."""
    def __init__(self, dimension, config, age_basis='sample'):
        if age_basis not in ('sample', 'arrival'):
            raise ValueError(age_basis)
        super().__init__(dimension, config)
        self.age_basis = age_basis

    def observe(self, pending, concentration):
        item = replace(pending, sample_index=pending.arrival_index) if self.age_basis == 'arrival' else pending
        super().observe(item, concentration)

    def projected_covariance(self, hours, pending=()):
        items = [replace(p, sample_index=p.arrival_index) for p in pending] if self.age_basis == 'arrival' else pending
        return super().projected_covariance(hours, items)


class LatestResidual:
    def __init__(self, half_life_hours=SHORT_HALF_LIFE, age_basis='arrival'):
        if half_life_hours <= 0 or age_basis not in ('sample', 'arrival'):
            raise ValueError('Invalid residual age specification')
        self.half_life = float(half_life_hours)
        self.age_basis = age_basis
        self.latest = None

    def observe(self, item, observed):
        origin = item.sample_index if self.age_basis == 'sample' else item.arrival_index
        self.latest = (origin, float(observed)-item.prior_prediction_at_sample)

    def correction(self, index):
        if self.latest is None:
            return 0.
        origin, residual = self.latest
        return float(residual * np.exp2(-(index-origin)/self.half_life))


@dataclass(frozen=True)
class RevisionSpec:
    output_family: str = 'latest_residual'
    output_half_life: float = SHORT_HALF_LIFE
    output_age_basis: str = 'arrival'
    scoring_delay_hours: int | None = None
    pending_aware: bool = True
    trace_counterfactual_scores: bool = True


def library_with_scoring_delay(library, feature_map, scoring_delay):
    """Recompute deterministic forecasts for the same historical context bank."""
    if scoring_delay == library.delay_hours:
        return library
    # The zero-delay bank needs the observed six-hour change during the first
    # six forecast hours. Original library contexts contain only delta_6; the
    # driver therefore attaches precomputed zero-delay prefixes from history.
    raise ValueError('Provide an explicitly built historical bank for this scoring delay')


def build_scoring_libraries(history_time, history_q, *, feature_map, q_scale,
                            actual_delay, lookahead=72, max_contexts=96, seed=41):
    """Use exactly the original context draw, allowing assumed delay zero."""
    from value_sampling import build_reference_library
    original = build_reference_library(history_time, history_q, feature_map=feature_map,
        q_scale=q_scale, delay_hours=actual_delay, lookahead_hours=lookahead,
        max_contexts=max_contexts, seed=seed)
    contexts = make_context(history_time, history_q, q_scale)
    ix = pd.DatetimeIndex(history_time).get_indexer(original.times)
    prefixes = np.stack([_load_prefix(original.times[j], contexts[max(0, i-6):i+1],
        feature_map=feature_map, q_scale=q_scale, delay_hours=0,
        lookahead_hours=lookahead) for j, i in enumerate(ix)])
    prefixes.setflags(write=False)
    return {actual_delay: original, 0: replace(original, load_prefix=prefixes, delay_hours=0)}


def _score(state, pending, delay, *, n, i, time, context, fmap, q_scale, z, library, cfg):
    horizon = max(0, min(cfg.lookahead_hours, n-i-delay))
    covariance = state.projected_covariance(delay, pending)
    effective_noise = state.noise_variance / state.decay(delay)
    prefix = _load_prefix(time[i], context[max(0, i-6):i+1], feature_map=fmap,
        q_scale=q_scale, delay_hours=delay, lookahead_hours=horizon)
    score = variance_reduction(covariance, z, prefix[-1], effective_noise)
    bank = _library_value_scores(covariance, library, horizon, effective_noise)
    threshold = float(np.quantile(bank, cfg.threshold_quantile))
    trigger = bool(np.isfinite(score) and score > 0 and score >= threshold)
    return score, threshold, trigger, horizon


def run_revision_replay(time, q_cms, base_prediction, concentration_hidden, label_valid_hidden,
                        *, feature_map, scoring_libraries, q_scale, policy, budget,
                        config=None, spec=None, seed=41):
    config = config or ValueSamplingConfig(half_life_hours=2160)
    spec = spec or RevisionSpec()
    config.validate()
    if policy not in ('uniform', 'flow_trigger', 'deadline_only', 'value'):
        raise ValueError(policy)
    if spec.output_family not in ('latest_residual', 'rff_pooled'):
        raise ValueError(spec.output_family)
    if spec.output_family == 'rff_pooled' and (spec.output_age_basis != 'sample' or
            spec.output_half_life != config.half_life_hours):
        raise ValueError('RFF output is the acquisition state; its clock must match config')
    delay = config.delay_hours if spec.scoring_delay_hours is None else spec.scoring_delay_hours
    if delay not in (0, config.delay_hours):
        raise ValueError('Revision comparison allows assumed zero or actual delay')
    time = _hourly_time(time)
    n = len(time)
    q, base, hidden = map(lambda a: np.asarray(a, dtype=float),
                          (q_cms, base_prediction, concentration_hidden))
    valid_hidden = np.asarray(label_valid_hidden, dtype=bool)
    if any(a.shape != (n,) for a in (q, base, hidden, valid_hidden)) or not np.isfinite(base).all():
        raise ValueError('Invalid aligned replay input')
    if not isinstance(budget, (int, np.integer)) or budget < 0:
        raise ValueError('Invalid budget')
    for d, bank in scoring_libraries.items():
        if (bank.training_end_utc >= time[0] or bank.delay_hours != d or
            bank.feature_signature != feature_map.signature or not np.isclose(bank.q_scale, q_scale)):
            raise ValueError('Historical score-bank provenance mismatch')
    context = make_context(time, q, q_scale)
    z = feature_map.transform(context)
    grid = np.arange(0, n, config.candidate_interval_hours)
    boundaries = np.linspace(0, n, budget+1, dtype=int) if budget else np.array([0, n])
    block_of = np.minimum(np.searchsorted(boundaries[1:], np.arange(n), side='right'), max(0,budget-1))
    deadlines, planned = {}, {}
    if budget:
        if n/budget < config.min_spacing_hours+config.candidate_interval_hours:
            raise ValueError('Blocks too short for shared spacing safeguards')
        phase = config.uniform_phase
        if phase is None:
            phase = {41:.25,73:.5,109:.75}.get(seed,.5)
        for block in range(budget):
            allowed = grid[(grid>=boundaries[block]) & (grid<boundaries[block+1])]
            deadlines[block] = int(allowed[-1])
            target = boundaries[block]+phase*(boundaries[block+1]-boundaries[block]-1)
            planned[block] = int(allowed[np.argmin(np.abs(allowed-target))])
    state = AgeResidualModel(feature_map.dimension, config, 'sample')
    local = LatestResidual(spec.output_half_life, spec.output_age_basis)
    pending, arrivals, used, records, trace = [], {}, set(), [], []
    online, variance = np.empty(n), np.empty(n)
    last = -10**12
    for i in range(n):
        state.advance_to(i)
        for item, observed, valid in arrivals.pop(i, []):
            if valid:
                state.observe(item, observed)
                local.observe(item, observed)
        pending = [p for p in pending if p.arrival_index > i]
        mean, latent = state.predict(z[i])
        correction = local.correction(i) if spec.output_family == 'latest_residual' else mean
        online[i], variance[i] = max(0., base[i]+correction), latent
        block = int(block_of[i])
        eligible = bool(budget and i % config.candidate_interval_hours == 0
                        and block not in used and i-last >= config.min_spacing_hours)
        if not eligible:
            continue
        deadline = i == deadlines[block]
        score, threshold, trigger = np.nan, np.nan, False
        row = dict(time_utc=time[i], time_index=i, is_candidate=True, eligible_candidate=True,
            block=block, pending_count=len(pending), received_labels=state.observations_received,
            noise_variance=state.noise_variance, acquisition_residual_mean=mean,
            output_residual_mean=correction, latent_variance=latent, deadline=deadline,
            actual_delay_hours=config.delay_hours, assumed_delay_hours=delay,
            pending_aware=spec.pending_aware)
        if policy == 'uniform':
            trigger = i >= planned[block]
        elif policy == 'flow_trigger':
            score = float(np.expm1(context[i,0])*(1+max(context[i,1],0)))
            threshold = float(np.quantile(scoring_libraries[config.delay_hours].flow_scores,
                                           config.threshold_quantile))
            trigger = bool(score > 0 and score >= threshold)
        elif policy == 'value':
            kwargs = dict(n=n,i=i,time=time,context=context,fmap=feature_map,q_scale=q_scale,z=z[i],cfg=config)
            keys = [('delay_aware_pending',config.delay_hours,True),
                    ('delay_zero',0,True),('delay_aware_omit',config.delay_hours,False)]
            outputs = {}
            for name,d,aware in keys:
                if spec.trace_counterfactual_scores or (d==delay and aware==spec.pending_aware):
                    outputs[(d,aware)] = _score(state,pending if aware else (),d,
                        library=scoring_libraries[d],**kwargs)
                    s,th,tr,h = outputs[(d,aware)]
                    row.update({name+'_score':s,name+'_threshold':th,name+'_trigger':tr,
                                name+'_horizon':h})
            if (delay,spec.pending_aware) not in outputs:
                outputs[(delay,spec.pending_aware)] = _score(state,pending if spec.pending_aware else (),
                    delay,library=scoring_libraries[delay],**kwargs)
            score,threshold,trigger,_ = outputs[(delay,spec.pending_aware)]
        action = bool(trigger or deadline)
        row.update(query_score=score,query_threshold=threshold,threshold_trigger=trigger,
                   action=action,forced_deadline=bool(deadline and not trigger))
        trace.append(row)
        if not action:
            continue
        used.add(block)
        last = i
        item = PublicPending(i,i+config.delay_hours,z[i].copy(),state.noise_variance,
                             float(base[i]),float(online[i]))
        # Environment inspects hidden concentration/quality only after purchase;
        # failures remain publicly pending until the scheduled response time.
        observed = float(hidden[i])
        valid = bool(valid_hidden[i] and np.isfinite(observed) and observed>=0)
        pending.append(item)
        arrivals.setdefault(item.arrival_index,[]).append((item,observed,valid))
        reason = ('calendar' if policy=='uniform' else 'threshold') if trigger else 'block_deadline'
        records.append(dict(sample_index=i,sample_time=time[i],arrival_index=item.arrival_index,
            arrival_time=time[i]+pd.Timedelta(hours=config.delay_hours),block=block,
            label_success=valid,label_available_by_horizon=valid and item.arrival_index<n,
            observed_mg_l=observed if valid else np.nan,reason=reason,
            measurement_variance_at_sample=item.measurement_variance,
            prediction_at_sample=item.online_prediction_at_sample,query_score=score,
            query_threshold=threshold,pending_count_at_sample=len(pending)-1,
            forced_deadline=bool(deadline and not trigger)))
    if len(records)!=budget:
        raise RuntimeError('Attempt budget not fully spent')
    attempts = pd.DataFrame(records,columns=list(ATTEMPT_COLUMNS)+['pending_count_at_sample','forced_deadline'])
    for col in ('label_success','label_available_by_horizon','forced_deadline'):
        attempts[col] = attempts[col].astype(bool)
    attempts['sample_index'] = attempts.sample_index.astype(int)
    return ValueReplayResult(attempts,online,variance,pd.DataFrame(trace))


def reconstruct_fixed_calendar(base, z, attempts, *, family, half_life, age_basis, noise_variance):
    """Matched clocks and constant noise; family remains an update-family contrast.

RFF pools/shrinks observations whereas latest residual retains one unshrunk
innovation. This contrast must not be called the pure effect of representation.
"""
    base = np.asarray(base,float)
    cfg = ValueSamplingConfig(half_life_hours=half_life,noise_variance=noise_variance,
                               prior_variance=noise_variance,noise_adaptation_rate=0)
    state = AgeResidualModel(z.shape[1],cfg,age_basis)
    local = LatestResidual(half_life,age_basis)
    returns = {}
    for r in attempts.itertuples():
        if r.label_available_by_horizon:
            s,a = int(r.sample_index),int(r.arrival_index)
            item = PublicPending(s,a,z[s],noise_variance,float(base[s]),float(base[s]))
            returns.setdefault(a,[]).append((item,float(r.observed_mg_l)))
    pred = np.array(base,copy=True)
    for i in range(len(base)):
        state.advance_to(i)
        for item,observed in returns.get(i,[]):
            if family=='rff_pooled':state.observe(item,observed)
            else:local.observe(item,observed)
        if family=='rff_pooled':correction=state.predict(z[i])[0]
        elif family=='latest_residual':correction=local.correction(i)
        else:raise ValueError(family)
        pred[i] = max(0.,base[i]+correction)
    return pred
