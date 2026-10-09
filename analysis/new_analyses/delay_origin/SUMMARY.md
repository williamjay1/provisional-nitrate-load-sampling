# Fixed-calendar actual-return-delay and residual-decay-origin diagnostic

Post hoc diagnostic of the archived revision replay for the 2025 temporal cohort at a budget of 96 attempted samples per station-year. The purchase calendars of the archived policies uniform (periodic), flow_trigger and deadline_only are held **exactly fixed** as collection timestamps; only the return delay and the origin of the residual decay are varied, and the hourly online prediction is re-derived with the latest-residual correction of the main revision.

Units: the endpoint is a dimensionless mean absolute relative error of the valid-window event load; multiply by 100 for per cent. Differences are in the same units.

## 1. Inputs reused (exact archived files)

Archived replay outputs (read-only):

| file | sha256 (first 16) | role in this analysis |
|---|---|---|
| revision_20261009/results/experiments_main_temporal_v1/attempts.csv | 9025860abb39607e | purchase calendars (sample_index/sample_time) for uniform, flow_trigger, deadline_only at budget 96, held fixed |
| revision_20261009/results/experiments_main_temporal_v1/metrics.csv | 75a903aae0f8deaf | archived endpoints, used only to verify reproduction |
| revision_20261009/results/experiments_main_temporal_v1/events.csv | 624c7bdc58349221 | archived eligible-event definitions and reference masses, used only to verify reproduction |
| revision_20261009/results/experiments_main_temporal_v1/run_manifest.json | 55dcc703377a706d | dataset digest and code digests of the archived run |
| datasets/extended_hourly_2019_2025_v1.parquet | 05398eb7d883d36c | dataset digest 05398eb7d883d36cbb5682847954dd56ac651ae7fa1e2649e6f0de68d9ea9905 matches the archived manifest; its digest keys the frozen context cache |

Frozen historical contexts (loaded with joblib, never refitted), directory D:\MLWork\NitrateAdaptiveSampling_20261005\cache\paper_contexts\05398eb7d883_a1553d8eaf64 — all 39 files used are listed with sha256 in run_manifest.json:

| context file | sha256 (first 16) |
|---|---|
| 02035000_2025_41.joblib | 08005c4efeaf5a07 |
| 02035000_2025_73.joblib | 2154bd3ef9d69936 |
| 02035000_2025_109.joblib | fbd912aa1a3d31ba |
| ... 36 further station-year-seed contexts | (see run_manifest.json) |

Each frozen context supplies the archived base prediction c0 (historical random forest, target_base), the discharge-defined event list (q90 threshold, 24 h merge, 12 h minimum) and the reference hourly load and validity masks. No model was refitted and no new data were read.

Code, imported unchanged from the read-only project tree (hashes in run_manifest.json, all verified equal to the archived revision manifest):

| module | what was reused |
|---|---|
| scripts/paper_metrics.py | evaluate(), the endpoint function, reused verbatim |
| scripts/replay.py | event scoring and boundary censoring inside evaluate() |
| scripts/value_sampling.py | make_context() and RFFFeatureMap (the feature map is passed to the reconstruction for fidelity; the latest-residual rule does not otherwise use it) |
| revision_20261009/scripts/revision_state.py | reconstruct_fixed_calendar(), LatestResidual and SHORT_HALF_LIFE (tau = 168 h) — the main revision output rule |
| scripts/paper_context.py | only its cache-key definition; the contexts themselves were read from the archive cache |

The read-only tree was not modified: interpreter bytecode writing was disabled (PYTHONDONTWRITEBYTECODE=1 and sys.dont_write_bytecode=True), and the script refuses to run if a required frozen context is absent instead of fitting a new one.

## 2. Design

- Fixed calendars: 117 = 13 stations x 3 seeds x 3 policies, each with exactly 96 attempted purchases in 2025; the collection timestamps are copied byte-for-byte from the archived attempts.csv and never re-planned.
- Crossed factors: actual return delay d in {6, 24, 72} h x decay origin in {collection, arrival}. For a delay d the arrival clock moves to a = s + d for every purchase; a purchase whose label would arrive after the end of the replay year is unavailable, exactly as in the main analysis.
- Online prediction for every hour t:  c_hat(t) = max(0, c0(x_t) + [c_s - c0(x_s)] * exp(-(t - origin)/168)) where s is the latest purchase whose label has already returned and origin is the collection time s or the arrival time a = s + d. The rule is realised by revision_state.reconstruct_fixed_calendar(family='latest_residual', half_life=168*ln2, age_basis='sample' for collection origin and 'arrival' for arrival origin).
- Endpoint: paper_metrics.evaluate() on the archived target frame with the archived event list and event_coverage = 0.95; the reported value is the mean absolute relative error over eligible events (coverage >= 0.95, not boundary-censored), using the archived reference masses. The same events and the same valid hours are used in all 18 cells of a station-year-seed, so cells are compared on a common set.
- Aggregation hierarchy (identical to revision_20261009/scripts/summarize_revision.py): events within station-year-seed, then seeds, then years, then stations equally. Paired differences are formed per station-year and averaged within station, and intervals are the 95% station-cluster bootstrap with 10000 resamples and seed 271828.
- Difference sign convention: baseline minus candidate; a positive difference means the candidate cell has the LOWER mean absolute relative error (is better).

## 3. Validation that the endpoint is comparable to the main analysis

- Reproduction of the archived cell (d = 24 h, arrival origin) for all 117 calendars: maximum absolute difference in the endpoint 9.71e-17; all event counts match the archive: True.
- Event definitions and reference masses: 414 eligible events compared with the archived events.csv, maximum absolute reference-mass difference 4.66e-10 kg and maximum absolute predicted-mass difference 9.31e-10 kg (float/text-rounding level).
- Aggregate level values against revision_20261009/results/summary_main_v1/aggregate_metrics.csv (temporal, systems, budget 96, delay 24 h, minimum 1 event): maximum absolute difference 5.55e-17 over the three calendars, 9 stations in both.
- Station bootstrap against .../summary_main_v1/paired_effects.csv (archived contrast uniform minus value at delay 24 h): mean difference 0.0381334223 vs archived 0.0381334223; 95% interval [-0.00009633, 0.07956545] vs archived [-0.00009633, 0.07956545]. The interval machinery is therefore the main analysis's own.

## 4. Headline results

### 4.1 Level values (mean event absolute relative error)

| calendar | delay (h) | decay origin | stations | eligible events | mean abs. rel. error | median over stations |
|---|---|---|---|---|---|---|
| deadline_only | 6 | arrival | 9 | 138 | 0.1654 | 0.1620 |
| deadline_only | 6 | collection | 9 | 138 | 0.1682 | 0.1630 |
| deadline_only | 24 | arrival | 9 | 138 | 0.1941 | 0.1951 |
| deadline_only | 24 | collection | 9 | 138 | 0.2034 | 0.1945 |
| deadline_only | 72 | arrival | 9 | 138 | 0.2277 | 0.1831 |
| deadline_only | 72 | collection | 9 | 138 | 0.2335 | 0.1997 |
| flow_trigger | 6 | arrival | 9 | 138 | 0.1442 | 0.1343 |
| flow_trigger | 6 | collection | 9 | 138 | 0.1465 | 0.1363 |
| flow_trigger | 24 | arrival | 9 | 138 | 0.1770 | 0.1373 |
| flow_trigger | 24 | collection | 9 | 138 | 0.1838 | 0.1442 |
| flow_trigger | 72 | arrival | 9 | 138 | 0.2309 | 0.2028 |
| flow_trigger | 72 | collection | 9 | 138 | 0.2332 | 0.2036 |
| uniform | 6 | arrival | 9 | 138 | 0.1880 | 0.1219 |
| uniform | 6 | collection | 9 | 138 | 0.1893 | 0.1239 |
| uniform | 24 | arrival | 9 | 138 | 0.2068 | 0.1462 |
| uniform | 24 | collection | 9 | 138 | 0.2081 | 0.1532 |
| uniform | 72 | arrival | 9 | 138 | 0.2481 | 0.2102 |
| uniform | 72 | collection | 9 | 138 | 0.2413 | 0.1960 |

Best cell: flow_trigger, delay 6 h, arrival origin = 0.1442. Worst cell: uniform, delay 72 h, arrival origin = 0.2481. Across all 18 cells the endpoint spans 0.1442 to 0.2481.

### 4.2 Origin effect (collection origin minus arrival origin, within calendar and delay)

| calendar | delay (h) | mean difference | 95% station CI | stations favouring arrival origin |
|---|---|---|---|---|
| deadline_only | 6 | +0.0027 | [+0.0003, +0.0053] | 6/9 |
| deadline_only | 24 | +0.0092 | [+0.0007, +0.0184] | 6/9 |
| deadline_only | 72 | +0.0057 | [-0.0066, +0.0178] | 5/9 |
| flow_trigger | 6 | +0.0024 | [-0.0000, +0.0048] | 5/9 |
| flow_trigger | 24 | +0.0068 | [-0.0021, +0.0161] | 6/9 |
| flow_trigger | 72 | +0.0023 | [-0.0102, +0.0152] | 4/9 |
| uniform | 6 | +0.0013 | [-0.0006, +0.0032] | 5/9 |
| uniform | 24 | +0.0013 | [-0.0080, +0.0105] | 5/9 |
| uniform | 72 | -0.0068 | [-0.0283, +0.0162] | 3/9 |

Absolute differences are at most 0.0092 and only 2 of 9 intervals exclude zero (both for deadline_only, favouring the arrival origin by ~0.003-0.009). The origin convention therefore does not materially change the endpoint.

### 4.3 Delay effect (longer delay minus shorter delay, within calendar and origin)

| calendar | origin | delay pair | mean difference | 95% station CI | stations favouring shorter delay |
|---|---|---|---|---|---|
| deadline_only | arrival | 24 h vs 6 h | +0.0287 | [+0.0040, +0.0615] | 7/9 |
| deadline_only | arrival | 72 h vs 6 h | +0.0623 | [+0.0103, +0.1196] | 7/9 |
| deadline_only | arrival | 72 h vs 24 h | +0.0336 | [-0.0023, +0.0681] | 7/9 |
| deadline_only | collection | 24 h vs 6 h | +0.0352 | [+0.0111, +0.0668] | 8/9 |
| deadline_only | collection | 72 h vs 6 h | +0.0653 | [+0.0138, +0.1220] | 7/9 |
| deadline_only | collection | 72 h vs 24 h | +0.0301 | [-0.0012, +0.0635] | 6/9 |
| flow_trigger | arrival | 24 h vs 6 h | +0.0328 | [+0.0027, +0.0686] | 8/9 |
| flow_trigger | arrival | 72 h vs 6 h | +0.0867 | [+0.0515, +0.1272] | 9/9 |
| flow_trigger | arrival | 72 h vs 24 h | +0.0539 | [+0.0296, +0.0770] | 8/9 |
| flow_trigger | collection | 24 h vs 6 h | +0.0373 | [+0.0044, +0.0720] | 8/9 |
| flow_trigger | collection | 72 h vs 6 h | +0.0866 | [+0.0462, +0.1298] | 9/9 |
| flow_trigger | collection | 72 h vs 24 h | +0.0493 | [+0.0206, +0.0774] | 7/9 |
| uniform | arrival | 24 h vs 6 h | +0.0188 | [+0.0091, +0.0308] | 9/9 |
| uniform | arrival | 72 h vs 6 h | +0.0601 | [+0.0304, +0.0876] | 7/9 |
| uniform | arrival | 72 h vs 24 h | +0.0413 | [+0.0146, +0.0631] | 7/9 |
| uniform | collection | 24 h vs 6 h | +0.0188 | [+0.0101, +0.0286] | 9/9 |
| uniform | collection | 72 h vs 6 h | +0.0520 | [+0.0179, +0.0825] | 8/9 |
| uniform | collection | 72 h vs 24 h | +0.0332 | [+0.0053, +0.0563] | 8/9 |

All 18 delay contrasts are positive and 16 of 18 intervals exclude zero: a longer actual return delay always raises the event error, by 0.0188-0.0373 (24 h vs 6 h), 0.0301-0.0539 (72 h vs 24 h) and 0.0520-0.0867 (72 h vs 6 h).

### 4.4 Where the labels went (mechanism check)

Mean number of labels returned within the replay year, out of 96 attempted purchases (arrival origin; the collection origin returns the same counts):

| calendar | 6 h | 24 h | 72 h |
|---|---|---|---|
| deadline_only | 84.92 | 84.92 | 84.92 |
| flow_trigger | 84.56 | 84.56 | 84.54 |
| uniform | 85.36 | 85.08 | 84.56 |

End-of-year truncation removes only 0.27 labels on average between d = 6 h and d = 72 h, so the delay effect is driven by when and how strongly the correction is applied, not by lost labels. About 10.5 of the 96 purchases per calendar fail outright (no valid label), independently of the delay.

### 4.5 Robustness (stations with at least 3 eligible events)

Restricting to station-years with >= 3 eligible events leaves 8 stations and endpoint values from 0.1517 to 0.2527. The delay effect survives (12 of 18 intervals exclude zero, all positive, 0.0164 to 0.0773), whereas the origin effect disappears (0 of 9 intervals exclude zero, -0.0126 to +0.0065).

### 4.6 Coverage of the endpoint

13 stations are archived in the temporal cohort, but only 9 have at least one eligible event in 2025 under the archived definitions: 03339000, 05447500, 05595000, 05599490 contribute no eligible event (05447500 also has no event defined at all in 2025). Each of the 9 retained stations contributes all 3 seeds, and each calendar cell carries 138 eligible events summed over the 27 station-year-seed cases (mean 5.11 per case). The archived main summary reports 46 events per cell because it sums seed-averaged counts, where summary.csv sums seed counts.

## 5. Reproduction

All commands were run from F:/SCI/nitrate_rev/analysis_delay with the interpreter whose package versions match revision_20261009/ENVIRONMENT_REVISION.json (Python 3.12.10, numpy 2.5.1, pandas 3.0.5, scipy 1.18.0, scikit-learn 1.9.0, pyarrow 25.0.0, joblib 1.5.3):

    $env:PYTHONDONTWRITEBYTECODE = "1"
    & 'D:\ptenv\Scripts\python.exe' delay_origin_diagnostic.py   # stage 1: reconstruction + endpoint
    & 'D:\ptenv\Scripts\python.exe' summarize_delay.py           # stage 2: aggregation + bootstrap
    & 'D:\ptenv\Scripts\python.exe' make_summary_md.py           # this report

Measured in-script runtime (excluding interpreter start-up): stage 1 35.1 s, stage 2 0.5 s (total 35.6 s), well inside the 40-minute budget.

## 6. Limitations

1. The calendars are the products of the original acquisition rules at an assumed 24 h delay (flow_trigger thresholds come from the archived 24 h scoring library; uniform phase and block deadlines as archived). They are held fixed across d, so the d = 6 h and d = 72 h cells do NOT describe what those policies would have purchased at those delays; the archived mechanisms suite covers delay-aware acquisition for the value policy separately. This is a controlled decomposition of the published pipeline, not a policy redesign.
2. Post hoc diagnostic on archived 2025 replay outputs: no new data, no hold-out, no unseen validation, and no re-tuning of the correction. Every one of the 117 calendars was already used in the published revision.
3. Small station sample: the endpoint is defined on 9 station clusters, so the station bootstrap intervals are coarse and should be read as approximate; the origin effect in particular is of the order of a few thousandths, at or below what 9 clusters can resolve.
4. One year only (2025, the temporal cohort): the "then years" step of the aggregation is vacuous here, so nothing is claimed about year-to-year stability.
5. One correction family only: the latest-residual rule with tau = 168 h, i.e. the published revision output rule. RFF-pooled updates and other half-lives exist in the archived factorial suite but were not crossed here.
6. The delay changes label availability only through the end-of-year rule (about one label per calendar between 6 h and 72 h); within-year timing and attenuation of the correction is the dominant channel, by construction of the fixed-calendar design.
7. Event definitions are inherited from the archived contexts (discharge q90 threshold with 24 h merge and 12 h minimum); any sensitivity of the endpoint to that definition is inherited as well.
8. Input completeness: all required inputs were present (117 archived calendars, 39 frozen contexts, archived event definitions and reference masses). No input was missing and nothing was substituted.

## 7. Files

| file | rows | content |
|---|---|---|
| results.csv | 702 | site, year, seed, policy, delay, origin, event_mean_absolute_relative_error, n_events per calendar x delay x origin x station-year-seed, plus diagnostic columns (event_median_absolute_relative_error, attempts, successful_labels, labels_returned_within_horizon, events_all, valid_hours, hour_coverage) |
| summary.csv | 90 | row_type = level (18 per minimum-events setting) and contrast (27 per setting): levels give the station-equal aggregate; contrasts give baseline/candidate cells, the mean difference and the 95% station bootstrap interval |
| validation_against_archive.csv | 117 | per-calendar reproduction of the archived endpoint, event counts and reference masses |
| validation_aggregation.csv | 4 | replication of the archived aggregate level values and of one archived paired effect with the same bootstrap |
| run_manifest.json | - | sha256 of every input (archive files, dataset, 39 frozen contexts, code), runtime, design and validation summaries, sha256 of every output |
| delay_origin_diagnostic.py, summarize_delay.py, make_summary_md.py | - | the analysis code |

Note on counting: summary.csv n_events sums eligible events over station-year-seed cases (3 seeds per station-year), whereas the archived main summary sums seed-averaged counts; the two differ by the number of seeds and are reconciled in section 4.6.

