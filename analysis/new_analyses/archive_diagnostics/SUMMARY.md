# Archive-based supplementary analyses

Scope: supplementary analyses built **only** from the frozen revision archive at
`D:/MLWork/NitrateAdaptiveSampling_20261005/revision_20261009/`. Nothing under the archive
root was created, modified or deleted; nothing outside `F:/SCI/nitrate_rev/analysis_arch/`
was written. Every number in every table was produced by the executed script below.

## Deliverables

| file | rows | content |
|---|---:|---|
| `coverage_sensitivity.csv` | 66 | coverage re-screen at 90/95/100% + paired endpoints where computable |
| `coverage_sensitivity_note.md` | - | feasibility note: what the archive can and cannot support |
| `overlap_counts.csv` | 12 | purchase-timestamp overlap and successful returns at budget 96 |
| `mass_error_pairs.csv` | 24 | paired absolute-mass-error intervals at budget 96, both cohorts |
| `per_station_differences.csv` | 17 | per-station value-minus-flow differences, worst first |
| `station_profile.csv` | 16 | one row per evaluated station |
| `run_manifest.json` | - | SHA-256 of every input and output, environment, conventions |
| `scripts/build_archive_analyses.py` | - | the single script that produced all of the above |

## Command and environment

```powershell
& "C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" `
  "F:\SCI\nitrate_rev\analysis_arch\scripts\build_archive_analyses.py"
```

Python 3.12.14, pandas 3.0.1, numpy 2.3.5. Runtime well under the 900 s tool budget.
File hashes are in `run_manifest.json` (`input_sha256`, `script_sha256`, `outputs`).

## Sources

| analysis | archived inputs |
|---|---|
| coverage re-screen | `results/context_events.csv` (pre-screen universe, 373 events) |
| coverage endpoints | `results/summary_main_v1/eligible_events.csv`, `station_metrics.csv`, `site_year_metrics.csv`, `paired_effects.csv` |
| overlap | `results/experiments_main_temporal_v1/attempts.csv`, `results/experiments_main_external_v1/attempts.csv` |
| mass error / per-station | `results/summary_main_v1/paired_effects.csv`, `station_metrics.csv`, `site_year_metrics.csv` |
| station profile | `results/context_events.csv`, `context_site_year.csv`, `context_residual_persistence.csv`, `context_forward_model.csv` |
| definitions | `docs/CONTEXT_ANALYSIS.md`, `results/context_variable_definitions.json` |

Policy naming follows `scripts/assemble_revision.py`: `uniform` = **Periodic**,
`flow_trigger` = **Flow trigger**, `deadline_only` = **Block deadline**,
`value` = **Load value**, `no_new_labels` = **Historical predictor**.
Cohort naming: `stage=temporal` = **temporal cohort**; `stage=external` =
**additional-station cohort**; `stage=development` = **development cohort**.

## Definitions and conventions

* **Estimand / hierarchy** (unchanged from the archive): events are averaged inside
  station-year-seed, then across seeds, then across years within a station, then with equal
  weight across stations. Reimplemented here from `eligible_events.csv` and verified
  against `site_year_metrics.csv` (299 comparable rows, max absolute difference
  5.8e-11).
* **Bootstrap**: station-block resampling, 10,000 resamples, seed 271828, ratio estimator
  `sum(z_i * n_i) / sum(n_i)` over resampled stations; identical to
  `scripts/summarize_revision.py::interval`. Reproduced here against
  `paired_effects.csv`: 96 comparisons, station counts identical, max absolute difference
  2.9e-11.
* **Difference convention**: `baseline - value`; a positive difference means load value has
  the **lower** error. `stations_value_better` is the archive's `candidate_lower`.
* **Budget**: 96 attempted samples per calendar year; actual result delay 24 h.
* **Candidate grid**: 6 h (`ValueSamplingConfig.candidate_interval_hours`), minimum spacing
  24 h.
* **Reference coverage**: fraction of an event's hours that are complete reference hours
  (all four joint-qualified quarter-grid observations present). Primary retention rule is
  `coverage >= 0.95`.
* **Reference concentration** (`median_reference_nox_mean_mg_l`): median over the station's
  evaluated years of `reference_nox_mean_mg_l` from `context_site_year.csv`, which is the
  mean of the exact-hour NOx label over the joint-qualified hours of that station-year.
* **Residual lag correlations**: `pearson_residual_autocorrelation` from
  `context_residual_persistence.csv` with `pair_support = continuous_all_hours_qualified`
  (every intervening hour and both endpoints jointly qualified), median across the
  station-years available for that station.

## (1) Coverage-threshold sensitivity - see `coverage_sensitivity_note.md`

The pre-screen universe *is* archived (`context_events.csv`, 373 events, coverage
0.0-1.0), but the reconstructed per-event loads are archived only for events that already
passed the 95% rule (`eligible_events.csv`: 110 events, coverage 0.95556-1.0, **no** event
below 0.95).

| threshold | temporal stations / events | additional stations / events | development stations / events | mean reference support (temporal / additional) |
|---|---|---|---|---|
| 90% | 9 / 51 (+5) | 8 / 68 (+4) | 7 / 38 (+2) | 0.9873 / 0.9930 |
| 95% | 9 / 46 | 8 / 64 | 7 / 36 | 0.9935 / 0.9975 |
| 100% | 8 / 29 (-1 station) | 6 / 54 (-2 stations) | 6 / 23 (-1 station) | 1.0000 / 1.0000 |

* **90%: paired differences are NOT computable.** The 11 newly admitted events were never
  scored, so their predicted/reference window loads do not exist in the archive. The 16
  corresponding rows carry `status = not_computable` and blank estimates; nothing was
  approximated. Lowering the threshold can only *add* events (the retained set is nested),
  so on the existing common event set the published endpoints cannot change.
* **100%: computable** as a strict subset and reported with the same bootstrap. It removes
  21 of 110 events and 1 temporal / 2 additional stations under the one-event rule.

Headline at 100% (equal-station means, baseline minus value, positive favours load value):

* temporal abs. relative error - Periodic 20.54% vs 25.44%, **+4.90 pp** (-1.41 to 12.47);
  Flow trigger 20.54% vs 20.67%, +0.13 pp (-1.35 to 1.48); Block deadline
  20.54% vs 23.24%, +2.70 pp (-0.11 to 5.56).
* additional abs. relative error - Periodic 16.23% vs 17.99%, +1.76 pp (-0.57 to 4.10);
  Flow trigger 16.23% vs 17.83%, **+1.60 pp (+0.37 to 2.89)**; Block deadline
  16.23% vs 17.57%, +1.35 pp (+0.37 to 2.43).
* additional absolute mass error - Periodic 21.28 vs 23.71 x10^3 kg, **+2.43 x10^3 kg
  (+0.46 to 4.45)**; Flow trigger 21.28 vs 23.14 x10^3 kg, **+1.85 x10^3 kg
  (+0.23 to 3.75)**.

The additional-station value-versus-flow interval moves from crossing zero at the 95%
screen to excluding zero at the 100% screen; the temporal cohort does not.

Retained-event coverage distribution (temporal + additional, 110 events): min 0.9556,
5% 0.9737, 10% 0.9829, 25% 1.0, median 1.0, max 1.0.

## (2) Sampling-opportunity overlap at budget 96 (`overlap_counts.csv`)

All 6 comparison rows use only timestamps; each policy spends exactly 96 attempts per
station-year-seed, and every purchase time lies on the archived 6 h candidate grid with
24 h minimum spacing, so "identical" is exact timestamp equality and needs no tolerance.
`timestamps_within_6h_not_identical` additionally counts purchases whose nearest
counterpart is an adjacent 6 h grid slot.

Full archived cohorts (temporal: 13 sites x 2025 x 3 seeds = 39 groups, 3744 attempts per
policy; additional: 8 sites x 2 years x 3 seeds = 48 groups, 4608 attempts per policy):

| cohort | comparison | identical | differing | within 6 h, not identical | successful returns (value / baseline) |
|---|---|---:|---:|---:|---|
| temporal | value vs flow trigger | 3127 | 617 | 217 | 3349 / 3328 |
| temporal | value vs periodic | 36 | 3708 | 48 | 3349 / 3329 |
| temporal | value vs block deadline | 2879 | 865 | 525 | 3349 / 3345 |
| additional | value vs flow trigger | 3703 | 905 | 270 | 4313 / 4308 |
| additional | value vs periodic | 44 | 4564 | 81 | 4313 / 4267 |
| additional | value vs block deadline | 3779 | 829 | 358 | 4313 / 4323 |

Restricted to the primary event-eligible stations (temporal 9 sites, 2592 attempts per
policy; the additional cohort is unchanged because all eight of its stations are
event-eligible): value vs flow trigger 2082 identical / 510 differing; value vs periodic
30 / 2562; value vs block deadline 1840 / 752.

Success rates over the full archived cohorts are 89.4% per policy in the temporal cohort and
92.6-93.8% in the additional cohort; `label_success` is a property of the purchased hour,
verified identical across policies at the same station-year-seed-sample_index, so the
counts differ only through the chosen calendar.

## (3) Paired mass error and per-station differences

`mass_error_pairs.csv` (budget 96; the primary specification is `minimum_events = 1`,
both cohorts; `minimum_events = 3` is carried as the archived sensitivity). Absolute mass
error, equal-station means in kg N, difference = baseline minus value:

| cohort | spec | baseline | value | baseline | difference | station 95% CI | stations value better |
|---|---|---|---:|---:|---:|---|---:|
| temporal | min 1 | Periodic | 51796 | 47528 | -4268 | -26165 to 10993 | 4 / 9 |
| temporal | min 1 | Flow trigger | 51796 | 59531 | +7735 | -1738 to 22852 | 6 / 9 |
| temporal | min 1 | Block deadline | 51796 | 54594 | +2798 | -4312 to 10499 | 6 / 9 |
| additional | min 1 | Periodic | 25879 | 24554 | -1325 | -12296 to 5559 | 6 / 8 |
| additional | min 1 | Flow trigger | 25879 | 26586 | +707 | -1350 to 2721 | 5 / 8 |
| additional | min 1 | Block deadline | 25879 | 27913 | +2034 | -636 to 5535 | 4 / 8 |

**No absolute-mass-error interval excludes zero at the 95% screen in either cohort at the
primary specification.** The equal-station means reproduce the published Table 3 values
(temporal 47.53 / 59.53 / 54.59 / 51.80 x10^3 kg; additional 24.55 / 26.59 / 27.91 /
25.88 x10^3 kg) exactly. The same table also carries the absolute-relative-error intervals,
which do exclude zero against the block deadline in both cohorts.

`per_station_differences.csv` (17 station rows, budget 96, minimum_events = 1, sorted
descending by value minus flow) shows where **updating worsened performance**:

* temporal cohort - 3 of 9 stations worse with load value: 06902000 Grand River near Sumner
  (+3.17 pp; +6138 kg), 05484500 Raccoon River at Van Meter (+2.05 pp; +3128 kg),
  03346500 Embarras River at Lawrenceville (+1.91 pp; -562 kg).
* additional cohort - 3 of 8 stations worse: 05599490 Big Muddy River at Murphysboro
  (+8.05 pp; +4861 kg, 1 eligible event among its 18 detected events), 05484000 South Raccoon River at
  Redfield (+0.32 pp; +881 kg), 05482300 North Raccoon River near Sac City (+0.08 pp;
  +331 kg, 1 eligible event).
* The largest single improvement is 03374100 White River at Hazleton (-4.61 pp relative
  error, -65752 kg), a station with 2 eligible events.

## (4) Station profile (`station_profile.csv`)

16 distinct stations carrying 28 station-cohort memberships: 13 in the temporal cohort,
8 in the additional-station cohort and 7 in the development cohort. Twelve of the sixteen
stations belong to two cohorts (five temporal + additional, seven temporal + development)
and four belong to one (06902000 temporal only; 01646500, 03353200 and 05537980
additional only), which is why the per-cohort event counts and years are separate columns.
Columns are restricted to fields that exist in the archives: USGS id and name,
HUC4, cohort membership, evaluation years (union and per cohort), eligible and detected
event counts (total and per cohort), median reference coverage, median Q peak and median
reference load of eligible events, median reference concentration, and the historical
forward residual lag correlations at 6 / 24 / 72 / 168 h with the number of contributing
station-years. No catchment area, land use or inferred category is present.

All 16 stations have residual lag correlations (2 or 3 station-years each, from the 43
fitted station-years). Median lag correlation across stations falls from about 0.94-0.99 at
6 h to about -0.03-0.86 at 168 h, i.e. persistence at one week varies from near zero
(03346500) to strong (05482000).

## Limitations

1. The 90% coverage sensitivity requested in the brief **cannot be computed** from this
   archive. The 11 events it would add have no archived reconstruction endpoints. This is
   stated rather than approximated. The 100% screen is offered as the computable half of the
   coverage sensitivity; it is a subset, not a superset, and does not substitute for the
   90% test.
2. The re-screen re-applies only the two exclusion flags archived in
   `context_events.csv` (coverage below threshold, uncertain discharge boundary). Other
   retention rules (minimum 12 h span, fully observed Q on the 24 h outer boundaries,
   positive observed reference load) were applied upstream and are not separately visible.
3. `eligible_events.csv` carries per-event endpoints only; the whole-window measures
   `absolute_valid_window_bias`, `hourly_load_normalized_absolute_error` and
   `concentration_mae_mg_l` live in `experiments_*_v1/metrics.csv` and are therefore not
   recomputable from the event table for the 100% subset; they are not reported here.
4. The station profile pools across cohorts for a station that belongs to two cohorts
   (per-cohort event counts and per-cohort years are given as separate columns so the
   pooling is reversible).
5. `median_reference_nox_mean_mg_l` is a median over evaluated station-years of an
   unweighted annual concentration mean; it is not a load-weighted event concentration.
6. All intervals are station-block bootstrap intervals at the archived seed and resample
   count; no alternative bootstrap or multiplicity adjustment was applied.
