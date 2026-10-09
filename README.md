# Provisional river nitrate plus nitrite load estimation: sparse sampling and delayed updating

Analysis code, derived data and result tables for the manuscript

> **Sparse sampling and delayed updating for provisional river nitrate plus nitrite load estimation**

The study evaluates how much a reduced concentration sampling programme improves *provisional* hourly
river transport estimates when discharge continues to be observed, and when a more complex acquisition
rule stops earning its keep. The endpoint is the trajectory an analyst would actually have issued,
not a final annual load reassembled after every result has returned.

## What is here

| Folder | Content |
|---|---|
| `analysis/scripts/` | The chronological replay, sampling policies, reconstruction rules, metrics and summary code (Python 3.12) |
| `analysis/new_analyses/delay_origin/` | Fixed calendar diagnostic crossing the actual result return delay (6/24/72 h) with the residual decay origin (collection or arrival) |
| `analysis/new_analyses/archive_diagnostics/` | Reference coverage threshold sensitivity, sampling opportunity overlap, paired mass error intervals, per station differences and station profiles |
| `data/` | Derived hourly working snapshot (discharge and optical nitrate plus nitrite, 2019 to 2025, 21 stations) and the preparation and acquisition manifests |
| `results/` | Complete comparison tables, paired effects, eligible events, station metrics and context diagnostics as CSV |
| `docs/` | Experiment description, context analysis, verification records and delivery audit |
| `manuscript/` | LaTeX source of the manuscript and the Online Resources, plus the vector figure files |

## Archived release and DOI

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23256544.svg)](https://doi.org/10.5281/zenodo.23256544)

Version 1.0.0 of this archive is deposited on Zenodo:

- Version DOI (this snapshot): https://doi.org/10.5281/zenodo.23256544
- Concept DOI (all versions): https://doi.org/10.5281/zenodo.23256543
- GitHub release: https://github.com/williamjay1/provisional-nitrate-load-sampling/releases/tag/v1.0.0

Please cite the version DOI when referring to the analyses reported in the manuscript.

## Data provenance

All observations come from the United States Geological Survey Water Data for the Nation service
(parameter 00060 discharge and parameter 99133 optical nitrate plus nitrite), retrieved on
5 October 2026 for calendar years 2019 to 2025. The station identifiers, the exact query manifests
and the quality screens are recorded in `data/` and `docs/`. The derived snapshot in `data/` is
a filtered working copy, not a redistribution of the service.

## Reproducing the analyses

```bash
python -m pip install -r requirements.txt
python analysis/scripts/revision_experiments.py --help        # main replay suites
python analysis/new_analyses/delay_origin/delay_origin_diagnostic.py
python analysis/new_analyses/archive_diagnostics/scripts/build_archive_analyses.py
```

Two independent checks are included in `docs/`: the archived endpoints are reproduced by the delay and
origin diagnostic with a maximum difference of 9.7e-17, and the paired effects are reproduced with
identical station counts and a maximum difference of 2.9e-11 using the same 10,000 resample station
bootstrap (seed 271828).

## Scope

The analyses describe the qualified sensor reference, the declared information clock and the observed
support of these records. They do not establish accuracy against independent laboratory measurements,
complete annual loads, or sustained operation over several sparse monitoring years.

## License

Code is released under the MIT License (see `LICENSE`). The derived data snapshot is provided for
reproduction of the published analyses.