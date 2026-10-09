"""Conservative observed-window evaluation for the paper (pilot stays unchanged)."""
import numpy as np
import pandas as pd
from replay import evaluate as pilot_evaluate


def evaluate(frame, prediction, events, attempts, event_coverage=.95):
    stats, rows = pilot_evaluate(frame, prediction, events, attempts, event_coverage)
    q = frame.q_at_time_cms.to_numpy(float)
    for row, (start, stop) in zip(rows, events):
        # A missing value within the allowed 24 h event-bridging window can
        # conceal an excursion that changes event membership. Censor both ends.
        uncertain = (start < 24 or stop + 24 > len(q)
                     or not np.isfinite(q[max(0,start-24):start]).all()
                     or not np.isfinite(q[stop:min(len(q),stop+24)]).all())
        row['boundary_uncertain'] = bool(uncertain)
        row['eligible'] = bool(row['coverage'] >= event_coverage and not uncertain)
        ref = row['reference_valid_window_load_kg']
        row['relative_error'] = ((row['predicted_valid_window_load_kg']-ref)/ref
                                 if row['eligible'] and ref > 1e-8 else np.nan)
    ev = pd.DataFrame(rows)
    if len(ev):
        errs = ev.relative_error.abs().dropna()
        stats.update(events_eligible=len(errs),
                     event_mean_absolute_relative_error=float(errs.mean()),
                     event_median_absolute_relative_error=float(errs.median()),
                     event_missed_fraction=float((ev.loc[ev.eligible,'sample_attempts']==0).mean()),
                     events_boundary_uncertain=int(ev.boundary_uncertain.sum()))
    return stats, rows
