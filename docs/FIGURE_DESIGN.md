# Revision figure design and provenance

Status: final figure set frozen on 9 October 2026 after the revision tables and independent numerical checks were complete. Only finalized analysis tables were plotted. The figure worker changed no scientific input, experiment, metric, interval or case-selection rule.

## Final narrative: six main and five supporting figures

The figures distinguish acquisition, delayed concentration return, online reconstruction and immutable concentration reports. They do not imply empirical laboratory validation, complete annual river load, public preregistration, or deployment without local concentration histories. Scientific line crossings and coincident predictions are preserved; text and legend intersections are not permitted.

| Figure | Final content | Key interpretation boundary |
|---|---|---|
| 1. Information and reference | Three information times; temporal and spatial cohort counts; station-year time and observed-volume coverage | The issued quantity is concentration. Hourly mass becomes complete only after its flow intervals are observed. Observed water is not all runoff. |
| 2. Transport and event timing | Station-year top-10%-hour and high-flow transport shares; individual event first-24/72-hour fractions with median and load-weighted summaries | Fixed windows start at event onset and are not actual first policy returns or error lower bounds. |
| 3. Complete system performance | All four policies plus historical model; three attempted-sample budgets; equally sized temporal and spatial panels; paired station-bootstrap contrasts | Positive baseline-minus-value percentage points favour load value. Relative event error is not kilogram error. Historical model uses zero new labels. |
| 4. Reconstruction memory | Every development combination of three fixed calendars, two families, three nominal half-lives and two age origins; paired family contrasts | Fixed-calendar component analysis. Same nominal half-life is not same effective memory. |
| 5. Delay, queue and fallback | Same-realized-delay scoring contrasts with paired intervals; pending activation; all-policy fallback fractions in both cohorts | Return delay is a replay information-clock condition, not measured laboratory performance. Pending correction is inactive at eligible 24 h candidates. |
| 6. Three real event processes | Largest improvement, nearest-median difference and largest deterioration at B96/seed41; Q, C, cumulative signed error and independent acquisition/return tracks | Cases are deterministic post-result illustrations. Four policy estimates are retained. Completed hourly mass is plotted at hour end; concentration at issue time. |
| S1. Reference selection | Duration and peak-flow empirical distributions for retained and excluded detected events in both cohorts | No missing-transport imputation or claim of random selection. |
| S2. Historical support | Forward residual correlations at exact lags; historical-model event and hourly-load errors | Descriptive, with exact continuous-qualified-pair support and undefined rows documented. |
| S3. Station heterogeneity | All event-eligible station-specific flow-minus-value differences at B96 in both cohorts | No seed-derived station confidence intervals; all negative and positive sites shown. |
| S4. Actual result arrivals | Mean station-level share of event load before first usable return and no-within-event-return frequency | Seeds averaged within event before station aggregation; pre-event samples may return during an event; earlier useful results may exist even without an in-event return. |
| S5. Score and observed utility | All 82 eligible isolated added-sample candidates, raw score versus kilogram utility and within-site fractional ranks | Descriptive post-result fixed-calendar diagnostic, not deployment-policy effect; no fit, p value or new subgroup. |

All budgets count attempted collections, including failed attempts. Ordinary plot text is 7 pt at final 183 mm width; panel letters are 8 pt. Captions are separate editable text files; the manuscript builder controls their placement. Six main panels avoid compressing complete-system and reconstruction comparisons into an unreadable composite.

## Data hand-off contract

Use long-format CSV or Parquet and a JSON manifest with exact definitions, units, source hashes and selection decisions. Retain `site` identifiers as strings. Common keys are `cohort` or `stage`, `site`, `year`, `seed`, `budget`, `policy`, `reconstructor`, and actual `delay_hours`. Mechanism tables additionally identify scoring-delay assumptions, queue switch, memory value and unit, and age origin. A result table must distinguish fixed-calendar component analysis from a newly run closed-loop comparison.

For point intervals provide `estimate`, `ci_low`, `ci_high`, `ci_unit`, `n_sites`, `n_site_years`, `n_events` and the aggregation definition; omit unsupported fields rather than fabricate them. For contrasts use baseline minus candidate, so positive percentage-point error differences favour the candidate. Fractions are stored as fractions and multiplied by 100 only at rendering. All retained/excluded/undefined/no-return denominators must be explicit.

Figure 6 requires `time_utc`, valid reference mask, discharge in m³ s⁻¹, concentration in mg N L⁻¹, reference hourly load in kg N, predicted concentration or load, original sample time, return time and return success. Its selection manifest lists candidate population, deterministic ranking or matching rule, chosen IDs, and post-result status. Missing reference segments remain visible gaps.

No plotting helper silently filters null values without recording the resulting denominator. No plot recomputes an inferential analysis that the analysis owner has not specified. A figure-level JSON records source hashes, filters, axis units and numerical values displayed.

## Physical and visual specification

Every main figure has an actual exported width of 183 mm and height no greater than 170 mm. The newer Nature figure guide's height limit supersedes the old guide's full-page-depth figure of 247 mm for this design. All ordinary text, tick labels, axis labels and legend labels are Arial 7 pt; panel letters are 8 pt bold upright lowercase. Lines are 0.5–1.0 pt. All text is black. No decorative icons, shadows, background grid, 3D chart or rainbow map.

The skill's `apply_house_style(fontsize=7)` otherwise reduces ticks and legends to 6 pt; `plot_revision.py` explicitly restores 7 pt. Its `save(..., bbox_inches='tight')` helper would alter physical width; this project uses the house style and audit, then exports on the fixed canvas with `bbox_inches=None`, independently checking the PDF MediaBox. This retains the requested 183 mm width rather than resizing text after export.

PDF embeds TrueType (`pdf.fonttype=42`); SVG retains editable `<text>` (`svg.fonttype='none'`). Data lines, error bars and area shapes remain vectors: no `imshow`, rasterized artists or screenshot composites. PNG is directly rendered at 1200 dpi, not upsampled; it is a review/backup format rather than the vector publication master. Each figure also has a 180 dpi preview for visual inspection. Editable SVG requires the relevant font on the editor's computer; embedded PDF is the stable viewing master.

Policy identity is consistent: regular = grey circle, block deadline = light-grey square, flow trigger = blue triangle, load value = vermilion diamond, flow × tree spread = green inverted triangle, stratified random = purple plus; use line styles as well as colour. Colours follow Nature's published accessible palette. The figure's main comparison never depends on hue alone. A sequential scientific colour map may encode magnitude in supplementary matrices, with a labelled scale; two-sided differences use a symmetric perceptually balanced map only when a matrix is preferable to intervals.

Legends occupy a separately reserved white Axes; they never sit over plotted observations. Internal text is avoided on busy data panels. Cohort titles use separate panel-title space, and all x/y axes have clear units. Zero-reference lines are thin and do not run through labels. Table coordination: root can use the same short policy labels, positive-improvement sign convention, percentage versus percentage-point distinction, and temporal/spatial order; tables do not duplicate every value printed in a figure.

## Reproducible QA

`plot_revision.py --self-test` tests deliberately failing cases for a long left title, text over a data line, overlapping labels, sub-7-pt text an overlaid legend, and data outside fixed axis limits. The exported fixture is explicitly marked as a layout test and is stored in `figures/_qa`, never mixed with scientific figures.

The deterministic audit inventories left/centre/right titles, tick labels, axis labels, annotations and figure/legend text. It checks canvas clipping, font sizes, text bounding-box intersections, independent legend space, and text intersections with line/line-collection paths. It also checks nominal/exported dimensions, PDF font resources and absence of raster images, SVG text/image elements, and native PNG dimensions/DPI. Every export records source hashes and a pending visual-review flag.

These checks do not prove absence of crowding in filled polygons or markers, nor reveal near-coincident curves. Final acceptance therefore also requires direct preview inspection with the vision-backend skill, including the three real event plots and any legends or left titles. Scientific numbers are verified from their source tables, not estimated from image pixels. A passed geometry audit alone is not a passed visual review.

Infrastructure check completed on 9 October: all six intentionally bad layouts were detected; exported fixture PDF width was 183.000 mm, TrueType was embedded, PDF/SVG contained no raster images, SVG had editable text, and the PNG was 8645 × 3685 pixels with 1199.9976 dpi metadata (rounding of nominal 1200 dpi). Native preview inspection and the vision-backend `see.ps1` check both found no clipping, overlaps, text/line crossings or legend crowding after removing unused top/right ticks. This validates the layout-test fixture only; scientific figures still require their own checks after final data are available.

## Primary-source tool verification, 9 October 2026

The `agent-reach` GitHub CLI route was used (`gh repo view`, `gh api`, `gh search repos`). No repository code was installed or executed. These are tool references, not evidence for the water-quality results.

- [SciencePlots repository](https://github.com/garrettj403/SciencePlots), MIT license reported by GitHub; inspected master commit `b9b16959570bd2fbc9ff5118bacc423c3bddd592` and [nature.mplstyle](https://github.com/garrettj403/SciencePlots/blob/b9b16959570bd2fbc9ff5118bacc423c3bddd592/src/scienceplots/styles/journals/nature.mplstyle). Its nature style specifies 7 pt ordinary text and sans-serif fonts; style selection alone does not enforce panel layout or scientific clarity.
- [cmcrameri repository](https://github.com/callumrollo/cmcrameri), inspected main commit `78f02a088fa3c4fb4cb8aa92bd8e52389ab9d09a`; the README identifies it as the Python wrapper for Fabio Crameri's Scientific colour maps. GitHub reports the license field as `NOASSERTION`, so no license conclusion is inferred from that metadata.
- [Matplotlib repository](https://github.com/matplotlib/matplotlib) and [official font documentation](https://matplotlib.org/stable/users/explain/text/fonts.html): the PDF and editable SVG font settings were checked against the documentation. The installed scifig environment is Python 3.12.10, Matplotlib 3.11.2, pandas 3.0.6; Arial resolves to an installed TrueType font. No new installation is required.
- [Nature: building and exporting figure panels](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/) supports the 183 mm width, 170 mm maximum figure height, editable vector output and accessible palette.
- [Nature: preparing figures](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/) supports standard sans-serif fonts, 8 pt lowercase panel labels, avoidance of overlapping text and decoration, and TrueType embedding.
- [Nature final artwork PDF](https://www.nature.com/documents/nature-final-artwork.pdf) is the older official guide. The current online guide is used where it provides a more restrictive figure-height limit.

The standards are used to improve clarity and production quality, not to imply suitability for Nature as a publication venue. The requested 1200 dpi backup is a project delivery choice; the vector originals preserve editability.


## Final execution and visual acceptance

The actual plotting commands use the installed scifig Python interpreter and `scripts/plot_revision.py` with `--context`, `--results`, `--cases` and `--diagnostics`. `--self-test` passes six negative geometry tests and export checks. Dependencies are Matplotlib, NumPy, pandas, Pillow and the already installed `figstyle.py` house-style helper. SciencePlots and cmcrameri were inspected as primary-source tooling references; no downloaded repository code was installed or executed. The plotted designs use explicit Matplotlib artists rather than a raster template.

All 11 PDFs were independently rendered by Poppler at 300 dpi on their fixed physical canvases into `figures/_qa/print/`. Every resulting page was actually opened and visually inspected: titles, left panel labels, units, legends and policy tracks are readable; no text/text or text/line overlap, clipped label, missing glyph, data truncation or overlaid legend remains. The light-grey case event windows are data-aligned; the three cumulative-error axes share limits that include the 125.49% regular-calendar outlier. Legitimately overlapping curves remain coincident and use distinct dashes/markers rather than artificial displacement.

The optional external vision backend returned a successful layout assessment for the test fixture and reference/history supplements. Later main-figure calls timed out at 45–55 seconds. Those timeouts are recorded as unavailable secondary checks, not as external passes. Final acceptance for every figure rests on native visual inspection of the actual PDF renders plus deterministic geometry, data-boundary and vector-export checks. Precise scientific values come from the source CSVs, never image interpretation.

`figures/final_figures_manifest.json` inventories the frozen 6 + 5 outputs and hashes, source-hash matches, PDF dimensions, TrueType embedding, editable SVG and native 1200 dpi PNG checks. Every figure has an individual `.qa.json` and `.caption.txt`. The PNG width is 8645 pixels; stored dpi is 1199.9976 due to PNG metadata quantization. PDF/SVG contain vector artists and no raster image payload. Typography uses ordinary 7 pt text with standard mathematical superscripts; it is not resized after export.

The numeric analyses and source tables were not edited during figure production. New inferential estimates were not calculated. Figure assembly is now frozen pending a concrete editorial correction.
