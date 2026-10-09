# Coverage-threshold sensitivity: feasibility note

Companion file: `coverage_sensitivity.csv` (66 rows: 9 screening rows, 9 retained-coverage
quantile rows, 48 paired rows). All numbers come from `scripts/build_archive_analyses.py`
run on 2026-10-09; see `run_manifest.json` for input hashes.

## The short answer

The event **universe** needed for a coverage re-screen *is* archived, but the **scored
endpoints** are not. Therefore:

| threshold | included stations (temporal / additional) | included events (temporal / additional) | endpoints recomputable? |
|---|---|---|---|
| 90% | 9 / 8 (unchanged) | 51 / 68 (+5 / +4) | **no** |
| 95% (archived primary) | 9 / 8 | 46 / 64 | yes - reproduced exactly |
| 100% | 8 / 6 (1 / 2 stations lost) | 29 / 54 | yes - strict subset, re-run here |

## Why 90% cannot be scored

Two different archived tables cover the events, and they do different jobs.

* `results/context_events.csv` is the **pre-screen universe**. It holds all 373 detected
  events of the three cohorts (development 65, additional/external 161, temporal 147) with
  `reference_hours`, `reference_hour_coverage`, `eligible`, `scorable`,
  `excluded_reason` and `boundary_uncertain`, before the 95% retention rule is applied.
  Its coverage spans 0.0 to 1.0, with 90 events below 0.90 and 32 events in [0.90, 0.95).
  So the pre-screen universe *is* available and counts, station membership and reference
  support can be re-screened at any threshold.
* `results/summary_main_v1/eligible_events.csv` is the **only** table that carries the
  reconstructed event loads (`reference_valid_window_load_kg`,
  `predicted_valid_window_load_kg`, `event_absolute_error_kg`, `event_abs_relative_error`).
  It is written from the 95%-eligible event list only: 110 unique events (temporal 46,
  additional 64), coverage minimum 0.95556, maximum 1.0, and **zero** events below 0.95.
  The 11 events that a 90% screen would newly admit (temporal +5, additional +4;
  development +2 for the third cohort) were never scored by the archived runs, so their
  predicted and reference window loads do not exist anywhere in the archive.

Re-running the reconstruction for those events is outside the archive: it would require the
frozen acquisition/reconstruction code plus the hourly reference series, which are not part
of the revision results tree that this analysis was restricted to. **No 90% paired
difference is reported, and none was approximated.** The 16 paired rows at threshold 0.90
are present in `coverage_sensitivity.csv` with `status = not_computable` and a note, and all
estimates blank.

## The exact consequence of lowering the threshold

Retention is `coverage >= t` with a fixed boundary-uncertainty filter, so the retained set
is **nested**: every event kept at 95% is kept at 90%, and every event kept at 100% is kept
at 95%. Lowering the threshold can only add events; it can never remove or re-score one.
It follows that, *on the existing common event set*, no endpoint can move - the paired
differences published at 95% are unchanged by construction. The only way the endpoints
change is a full re-run that scores the newly admitted events; that re-run is not in the
archive.

Additional properties of the 11 newly admitted events (all archived descriptors):

* none of them has a non-positive reference load, so the positive-load scoring rule would
  not have excluded any of them;
* all 5 temporal additions have a complete reference hour at their Q peak; 3 of the 4
  additional-station additions do;
* median event length 52 h (temporal) and 81 h (additional); median Q peak 191.7 and
  36.0 m3/s.

Lowering the threshold also **adds no station** in any cohort (the 5 temporal and 4
additional additions fall inside the existing 9 and 8 event-eligible stations), so the
station bootstrap population is unchanged at 90%.

## Caveats on the re-screen

* `context_events.csv` records only two exclusion reasons: `reference_coverage_below_0.95`
  and `uncertain_discharge_boundary`. Other retention rules of the original event
  definition (minimum 12 h span, fully observed Q on both 24 h outer boundaries, positive
  observed reference load) were applied upstream of this table and are not separately
  visible. The 90%/95%/100% re-screen here re-applies exactly the two archived flags;
  17 detected events carry a non-positive reference load, and none of them is admitted at
  90%, so this does not affect the reported counts.
* The 100% screen is "every event hour is a complete reference hour"
  (`reference_hours == hours`), not a new event definition.

## What the 100% screen changes (the computable half of the sensitivity)

Tightening to full coverage removes 21 of 110 events (temporal 46 -> 29, additional
64 -> 54) and drops one temporal and two additional stations below the one-event rule.
Equal-station means and the same station bootstrap (10,000 resamples, seed 271828):

| cohort | measure | baseline | value | baseline | difference | station 95% CI |
|---|---|---|---|---|---|---|
| temporal | abs. relative error | Periodic | 20.54% | 25.44% | +4.90 pp | -1.41 to 12.47 |
| temporal | abs. relative error | Flow trigger | 20.54% | 20.67% | +0.13 pp | -1.35 to 1.48 |
| temporal | abs. relative error | Block deadline | 20.54% | 23.24% | +2.70 pp | -0.11 to 5.56 |
| additional | abs. relative error | Periodic | 16.23% | 17.99% | +1.76 pp | -0.57 to 4.10 |
| additional | abs. relative error | Flow trigger | 16.23% | 17.83% | +1.60 pp | +0.37 to 2.89 |
| additional | abs. relative error | Block deadline | 16.23% | 17.57% | +1.35 pp | +0.37 to 2.43 |
| temporal | absolute mass error | Periodic | 19788 kg | 23875 kg | +4087 kg | -1215 to 9884 |
| temporal | absolute mass error | Flow trigger | 19788 kg | 17544 kg | -2244 kg | -5217 to 106 |
| additional | absolute mass error | Periodic | 21283 kg | 23711 kg | +2428 kg | +464 to 4454 |
| additional | absolute mass error | Flow trigger | 21283 kg | 23137 kg | +1854 kg | +225 to 3750 |

Differences are baseline minus value, so positive favours load value. The additional-station
cohort is where the 100% screen bites: the value-versus-flow advantage there moves from
+0.09 pp (-2.52 to 1.99) at the 95% screen to +1.60 pp (+0.37 to 2.89), and the mass-error
comparison becomes favourable with an interval excluding zero. The temporal cohort keeps an
interval that crosses zero against the flow trigger. Because the 100% screen is a *subset*
rather than the requested 90% *superset*, this is an upper-coverage sensitivity, not a
lower-coverage one; it is reported as such and is not a substitute for the 90% test.
