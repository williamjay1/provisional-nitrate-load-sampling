"""Publication figure infrastructure for the 9 October revision.

Use the existing scifig interpreter. Scientific figures consume explicit result
tables; the --self-test fixture is labelled as a layout test, not research data.
All outputs remain under the revision directory on D:.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
FIGURES = ROOT / "figures"
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "temp/matplotlib"))
os.environ.setdefault("JOBLIB_TEMP_FOLDER", str(ROOT / "temp"))
sys.path.insert(0, r"C:\Users\Administrator\.agents\skills\sci-figures")
from figstyle import apply_house_style, audit as house_audit, mm, panel_label

plt = apply_house_style(fontsize=7, use_tex=False)
import matplotlib as mpl
from matplotlib.collections import LineCollection, PathCollection
from matplotlib.lines import Line2D
from matplotlib.path import Path as MplPath
from matplotlib.transforms import Bbox
import numpy as np
import pandas as pd
from PIL import Image

WIDTH_MM = 183.0
MAX_HEIGHT_MM = 170.0
PNG_DPI = 1200
MIN_FONT_PT = 7.0
STYLE = {
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 7.0, "axes.titlesize": 7.0, "axes.labelsize": 7.0,
    "xtick.labelsize": 7.0, "ytick.labelsize": 7.0, "legend.fontsize": 7.0,
    "legend.title_fontsize": 7.0, "figure.titlesize": 7.0,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.5, "lines.linewidth": 0.9, "lines.markersize": 3.0,
    "xtick.major.width": 0.5, "ytick.major.width": 0.5,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "xtick.top": False, "ytick.right": False,
    "xtick.direction": "out", "ytick.direction": "out",
    "xtick.minor.visible": False, "ytick.minor.visible": False,
    "axes.grid": False, "text.color": "black", "axes.labelcolor": "black",
    "legend.frameon": False, "savefig.bbox": None, "savefig.pad_inches": 0,
    "savefig.facecolor": "white", "figure.facecolor": "white",
    "mathtext.fontset": "dejavusans", "text.usetex": False,
}
mpl.rcParams.update(STYLE)

# Policy colour is consistent across all figures. Shape/line style carries the
# same identity in greyscale. Scientific comparison is never encoded by hue alone.
POLICY_STYLE = {
    "uniform": {"label": "Regular", "color": "#555555", "marker": "o", "ls": "-"},
    "deadline": {"label": "Block deadline", "color": "#999999", "marker": "s", "ls": ":"},
    "flow_trigger": {"label": "Flow trigger", "color": "#0072B2", "marker": "^", "ls": "--"},
    "value": {"label": "Load value", "color": "#D55E00", "marker": "D", "ls": "-"},
    "q_uncertainty": {"label": "Flow × tree spread", "color": "#009E73", "marker": "v", "ls": "-."},
    "stratified_random": {"label": "Stratified random", "color": "#CC79A7", "marker": "P", "ls": ":"},
    "zero": {"label": "Historical model", "color": "#222222", "marker": "x", "ls": "--"},
}
POLICY_STYLE["deadline_only"] = POLICY_STYLE["deadline"]
POLICY_STYLE["no_new_labels"] = POLICY_STYLE["zero"]
COHORT_LABELS = {"temporal": "Temporal evaluation", "external": "Spatial policy extension"}


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def new_figure(height_mm=140.0):
    if not 30 <= height_mm <= MAX_HEIGHT_MM:
        raise ValueError("Figure height must be 30–170 mm")
    return plt.figure(figsize=(mm(WIDTH_MM), mm(height_mm)), layout=None)


def label_panel(ax, letter, title=None):
    if not re.fullmatch("[a-z]", letter):
        raise ValueError("Panel labels are single lowercase letters")
    panel_label(ax, letter, pad=7)
    ax._left_title.set_fontsize(8)
    ax._left_title.set_fontstyle("normal")
    if title:
        ax.set_title(title, loc="center", pad=7, fontsize=7, fontweight="normal")


def legend_white_zone(fig, bounds, handles, labels, ncol=3):
    """Reserve a separate, data-free Axes; do not overlay a legend on a plot."""
    ax = fig.add_axes(bounds)
    ax._revision_role = "legend"
    ax.set_axis_off()
    legend = ax.legend(handles, labels, loc="center", ncol=ncol, frameon=False,
                       borderaxespad=0, borderpad=0, labelspacing=0.5,
                       handlelength=2.4, handletextpad=0.65, columnspacing=1.8)
    for text in legend.get_texts():
        text.set_color("black")
    return ax, legend


def visible_texts(fig):
    """Include all three title slots and figure/legend text, without duplicates."""
    result = []
    seen = set()

    def add(text, role, axis):
        if id(text) in seen or not text.get_visible() or not text.get_text().strip():
            return
        seen.add(id(text))
        result.append((text, role, axis))

    for i, ax in enumerate(fig.axes):
        if not ax.get_visible():
            continue
        for loc, artist in [("left", ax._left_title), ("center", ax.title), ("right", ax._right_title)]:
            add(artist, "title_" + loc, i)
        for text in ax.texts:
            add(text, "annotation", i)
        if ax.axison:
            for axis, prefix in [(ax.xaxis, "x"), (ax.yaxis, "y")]:
                if not axis.get_visible():
                    continue
                add(axis.label, prefix + "_label", i)
                add(axis.get_offset_text(), prefix + "_offset", i)
                lower,upper=sorted(axis.get_view_interval())
                # Log locators keep extra tick artists outside the view limits;
                # Matplotlib does not draw them even when get_visible() is True.
                for tick in axis.get_major_ticks()+axis.get_minor_ticks():
                    if lower-1e-10<=tick.get_loc()<=upper+1e-10:
                        add(tick.label1, prefix + "_tick", i)
                        add(tick.label2, prefix + "_tick", i)
        legend = ax.get_legend()
        if legend:
            add(legend.get_title(), "legend_title", i)
            for text in legend.get_texts():
                add(text, "legend", i)
    for legend in fig.legends:
        add(legend.get_title(), "legend_title", None)
        for text in legend.get_texts():
            add(text, "legend", None)
    for text in fig.texts:
        add(text, "figure_text", None)
    return result


def bbox_audit(fig, minimum_font_pt=MIN_FONT_PT):
    """Conservative geometry preflight; visual inspection remains mandatory.

    Text collisions include left/right titles. Text/data-line intersections cover
    Line2D and LineCollection strokes, not arbitrary filled polygons or markers.
    A clean report is not a substitute for looking at print-size previews.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    tolerance = fig.dpi / 72 * 0.3
    texts = []
    outside, tiny = [], []
    for text, role, axis in visible_texts(fig):
        bb = text.get_window_extent(renderer)
        record = {"text": text.get_text(), "role": role, "axis": axis,
                  "fontsize_pt": float(text.get_fontsize()), "bbox_px": list(map(float, bb.extents))}
        texts.append((record, bb))
        if record["fontsize_pt"] < minimum_font_pt - 1e-6:
            tiny.append(record)
        if bb.x0 < canvas.x0-tolerance or bb.x1 > canvas.x1+tolerance or bb.y0 < canvas.y0-tolerance or bb.y1 > canvas.y1+tolerance:
            outside.append(record)
    collisions = []
    for i, (one, bb1) in enumerate(texts):
        for two, bb2 in texts[i+1:]:
            intersection = Bbox.intersection(bb1, bb2)
            if intersection is not None and intersection.width > tolerance and intersection.height > tolerance:
                collisions.append({"a": one, "b": two})
    legend_intrusions, legend_outside = [], []
    data_axes = [(i, ax) for i, ax in enumerate(fig.axes) if ax.get_visible() and getattr(ax, "_revision_role", "data") == "data"]
    for i, ax in enumerate(fig.axes):
        legend = ax.get_legend()
        if not legend:
            continue
        lb = legend.get_window_extent(renderer)
        if getattr(ax, "_revision_role", None) != "legend":
            legend_intrusions.append({"axis": i, "reason": "legend belongs to a data panel"})
        if not (ax.bbox.x0-tolerance <= lb.x0 and lb.x1 <= ax.bbox.x1+tolerance and
                ax.bbox.y0-tolerance <= lb.y0 and lb.y1 <= ax.bbox.y1+tolerance):
            legend_outside.append({"axis": i, "legend_bbox": list(map(float, lb.extents))})
        for j, other in data_axes:
            overlap = Bbox.intersection(lb, other.bbox)
            if overlap is not None and overlap.width > tolerance and overlap.height > tolerance:
                legend_intrusions.append({"legend_axis": i, "data_axis": j})
    line_intersections = []
    clipped_data = []
    for i, ax in data_axes:
        paths = []
        for line in ax.lines:
            if line.get_visible() and line.get_linestyle() not in {"None", "", " "}:
                paths.append(line.get_path().transformed(line.get_transform()))
        for collection in ax.collections:
            if isinstance(collection, LineCollection) and collection.get_visible():
                paths.extend(MplPath(segment).transformed(collection.get_transform()) for segment in collection.get_segments())
        # Scientific truncation is separate from text clipping. Check finite
        # data vertices and scatter centres so a tidy layout cannot hide an
        # outlying observation or error-bar endpoint behind a fixed axis limit.
        locations=[path.vertices for path in paths]
        for collection in ax.collections:
            if isinstance(collection,PathCollection) and collection.get_visible():
                locations.append(collection.get_offset_transform().transform(collection.get_offsets()))
        for vertices in locations:
            vertices=np.asarray(vertices,float)
            finite=vertices[np.isfinite(vertices).all(axis=1)]
            if len(finite):
                outside_points=(finite[:,0]<ax.bbox.x0-tolerance)|(finite[:,0]>ax.bbox.x1+tolerance)|(finite[:,1]<ax.bbox.y0-tolerance)|(finite[:,1]>ax.bbox.y1+tolerance)
                if outside_points.any():clipped_data.append({'axis':i,'finite_vertices_outside':int(outside_points.sum())})
        for record, bb in texts:
            part = Bbox.intersection(bb, ax.bbox)
            if part is None or part.width <= tolerance or part.height <= tolerance:
                continue
            if any(path.intersects_bbox(part, filled=False) for path in paths):
                line_intersections.append({"axis": i, "text": record})
    base = house_audit(fig, max_width_mm=WIDTH_MM, verbose=False)
    nominal = np.asarray(fig.get_size_inches()) * 25.4
    vector_only = not any(ax.images for ax in fig.axes) and not any(
        bool(getattr(artist, "get_rasterized", lambda: False)()) for artist in fig.findobj())
    result = {"house_audit": base, "nominal_mm": nominal.tolist(), "texts_checked": len(texts),
              "font_minimum_pt": minimum_font_pt, "small_text": tiny, "text_outside_canvas": outside,
              "text_collisions": collisions, "legend_intrusions": legend_intrusions,
              "legend_outside_reserved_zone": legend_outside, "text_line_intersections": line_intersections,
              "data_vertices_outside_axes": clipped_data,
              "vector_artists_only": vector_only,
              "limitations": "Geometry checks do not classify filled-polygon/marker crowding or near-coincident scientific curves; visual review is required."}
    result["ok"] = bool(base["ok"] and abs(nominal[0]-WIDTH_MM)<0.01 and nominal[1]<=MAX_HEIGHT_MM
                        and not any([tiny, outside, collisions, legend_intrusions, legend_outside, line_intersections,clipped_data])
                        and vector_only)
    return result


def verify_exports(stem):
    pdf = stem.with_suffix(".pdf").read_bytes()
    svg = ET.parse(stem.with_suffix(".svg")).getroot()
    tag = lambda name: "{http://www.w3.org/2000/svg}" + name
    svg_text = list(svg.iter(tag("text")))
    svg_image = list(svg.iter(tag("image")))
    box = re.search(rb"/MediaBox\s*\[\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*\]", pdf)
    if box is None:
        raise ValueError("Cannot verify PDF page size")
    media = [float(value) for value in box.groups()]
    width_mm = (media[2]-media[0])/72*25.4
    with Image.open(stem.with_suffix(".png")) as png:
        pixels = list(png.size)
        dpi = list(png.info.get("dpi", (0, 0)))
    checks = {"pdf_exact_width": abs(width_mm-WIDTH_MM)<0.02,
              "pdf_embedded_truetype": b"/FontFile2" in pdf,
              "pdf_no_type3": re.search(rb"/Subtype\s*/Type3\b", pdf) is None,
              "pdf_no_raster_images": re.search(rb"/Subtype\s*/Image\b", pdf) is None,
              "svg_editable_text": len(svg_text)>0, "svg_no_raster_images": len(svg_image)==0,
              "png_native_1200_dpi": all(abs(value-PNG_DPI)<0.1 for value in dpi),
              "png_native_width": abs(pixels[0]-WIDTH_MM/25.4*PNG_DPI)<=1.1}
    return {"ok": all(checks.values()), "checks": checks, "pdf_width_mm": width_mm,
            "png_pixels": pixels, "png_dpi": dpi, "svg_text_elements": len(svg_text),
            "sha256": {ext: digest(stem.with_suffix('.'+ext)) for ext in ['pdf','svg','png']}}


def export_figure(fig, name, sources=(), metadata=None, qa_fixture=False, supplement=False):
    out = FIGURES / ("_qa" if qa_fixture else "supplement" if supplement else "main")
    out.mkdir(parents=True, exist_ok=True)
    stem = out / name
    report = bbox_audit(fig)
    report.update({"figure": name, "created_utc": datetime.now(timezone.utc).isoformat(),
                   "qa_fixture_not_scientific_data": qa_fixture, "metadata": metadata or {},
                   "source_files": [{"path": str(Path(path)), "sha256": digest(path)} for path in sources]})
    if not report["ok"]:
        stem.with_suffix(".qa.json").write_text(json.dumps(report, indent=2, default=json_default), encoding="utf-8")
        fig.savefig(out / (name+"_FAILED_preview.png"), dpi=180, bbox_inches=None)
        raise ValueError("Figure failed geometry preflight: " + str(stem.with_suffix('.qa.json')))
    # Fixed canvas, not tight-cropped: the actual shipped width remains 183 mm.
    for extension in ['pdf', 'svg', 'png']:
        fig.savefig(stem.with_suffix('.'+extension), dpi=PNG_DPI, bbox_inches=None,
                    metadata={"Creator": "Matplotlib; revision_20261009/plot_revision.py"} if extension=='pdf' else None)
    fig.savefig(out / (name+"_preview.png"), dpi=180, bbox_inches=None)
    report["export_checks"] = verify_exports(stem)
    report["ok"] = report["ok"] and report["export_checks"]["ok"]
    report["visual_review"] = "pending"
    stem.with_suffix(".qa.json").write_text(json.dumps(report, indent=2, default=json_default), encoding="utf-8")
    if not report["ok"]:
        raise ValueError("Exported file checks failed")
    return report


def context_tables():
    folder = ROOT / 'results'
    paths = {key: folder / filename for key, filename in {
        'site': 'context_plot_site_year_long.csv', 'event': 'context_plot_event_long.csv',
        'persistence': 'context_residual_persistence.csv', 'zero': 'context_plot_zero_label_long.csv',
        'summary': 'context_summary.json', 'definitions': 'context_variable_definitions.json',
        'manifest': 'context_figure_source_manifest.json'}.items()}
    tables = {key: pd.read_csv(path, dtype={'site': str}) for key,path in paths.items() if path.suffix=='.csv'}
    tables['summary'] = json.loads(paths['summary'].read_text(encoding='utf-8'))['stages']
    for stage in ['temporal','external']:
        one=tables['site'].query('stage==@stage and metric=="hour_coverage"')
        if one.duplicated(['site','year']).any() or len(one)!=tables['summary'][stage]['station_years']:
            raise ValueError('Context cohort counts do not match final source: '+stage)
    return tables, paths


def add_caption(name, text, supplement=False):
    folder=FIGURES/('supplement' if supplement else 'main')
    # The shared operational budget pays for failed attempts as well as usable
    # concentrations; never label its denominator as successful samples.
    text=text.replace('24, 48 and 96 annual samples','24, 48 and 96 annual sampling attempts')
    text=text.replace('96 samples per year','96 attempted samples per year')
    text=text.replace('96 samples','96 attempted samples')
    text=text.replace('laboratory delay','result-return delay')
    if name.startswith(('Fig3','Fig4','Fig5','Fig6','FigS3','FigS4')):
        text+=' All stated sampling budgets count attempted collections, including attempts that yield no usable concentration.'
    (folder/(name+'.caption.txt')).write_text(text.strip()+'\n',encoding='utf-8')


def ordered_spread(count, width=.15):
    # Deterministic display-only jitter; does not alter measured values.
    if count<2:return np.zeros(count)
    return np.random.default_rng(314159).permutation(np.linspace(-width,width,count))


def values_for(table,stage,metric,scorable=None):
    rows=table.loc[table.stage.eq(stage)&table.metric.eq(metric)].copy()
    if scorable is not None:rows=rows.loc[rows.scorable.eq(scorable)]
    rows=rows.sort_values([key for key in ['site','year','event_id'] if key in rows])
    selected=rows.loc[np.isfinite(rows.value)]
    record={'stage':stage,'metric':metric,'rows_selected':len(rows),'finite_displayed':len(selected),
            'undefined_not_displayed':int((~np.isfinite(rows.value)).sum()),'scorable':scorable,
            'values':selected[['site','year']+(['event_id'] if 'event_id' in selected else [])+['value']].to_dict('records')}
    return selected,record


def plot_context_design(tables,paths):
    fig=new_figure(145)
    clock=fig.add_axes([.085,.765,.84,.16]);clock.set(xlim=(0,1),ylim=(0,1));clock.axis('off')
    label_panel(clock,'a','Information available within one assessment year')
    clock.annotate('',xy=(.97,.45),xytext=(.035,.45),arrowprops={'arrowstyle':'->','lw':.7,'color':'black'})
    for x,title,bottom in [(.18,'Sample collected','Sample time s'),(.50,'Concentration returned','Arrival time s + d'),(.83,'C estimate published','Report time t')]:
        clock.plot([x,x],[.39,.51],color='black',lw=.7)
        clock.text(x,.72,title,ha='center',va='center',fontsize=7)
        clock.text(x,.13,bottom,ha='center',va='center',fontsize=7)
    fig.text(.50,.728,'Local historical model + observed flow + concentrations already returned; past reports stay fixed',ha='center',fontsize=7)
    for stage,letter,x in [('temporal','b',.085),('external','c',.555)]:
        ax=fig.add_axes([x,.395,.37,.255]);ax.axis('off');ax.set(xlim=(0,1),ylim=(0,1))
        summary=tables['summary'][stage]
        title='Temporal evaluation · 2025' if stage=='temporal' else 'Spatial policy extension · 2023–2024'
        label_panel(ax,letter,title)
        labels=[f"{summary['sites']} data-eligible sites; {summary['station_years']} station-years",
                f"{summary['events_all']} detected high-flow events",
                f"{summary['events_eligible_positive_load']} retained events at {summary['event_sites']} sites"]
        for y,label in zip([.82,.49,.16],labels):
            ax.text(.5,y,label,ha='center',va='center',fontsize=7)
        for hi,lo in [(.73,.59),(.40,.26)]:
            ax.annotate('',xy=(.5,lo),xytext=(.5,hi),arrowprops={'arrowstyle':'->','lw':.7,'color':'#777777'})
    ax=fig.add_axes([.235,.115,.69,.205]);label_panel(ax,'d','Common reference support')
    rowspec=[('temporal','hour_coverage','Temporal: hours'),('temporal','reference_volume_fraction_observed_q','Temporal: water'),
             ('external','hour_coverage','Spatial: hours'),('external','reference_volume_fraction_observed_q','Spatial: water')]
    records=[]
    for j,(stage,metric,label) in enumerate(rowspec):
        selected,rec=values_for(tables['site'],stage,metric);records.append(rec)
        ax.scatter(selected.value.to_numpy()*100,j+ordered_spread(len(selected),.085),s=15,
                   marker='o' if metric=='hour_coverage' else 'D',color='#0072B2' if stage=='temporal' else '#555555',
                   linewidths=.3,edgecolors='white',zorder=3)
    ax.set(yticks=range(4),yticklabels=[r[2] for r in rowspec],ylim=(3.45,-.45),xlim=(45,101),xticks=[50,60,70,80,90,100],
           xlabel='Observed record covered by complete reference hours (%)')
    ax.spines['left'].set_visible(False);ax.tick_params(axis='y',length=0,pad=6)
    report=export_figure(fig,'Fig1_information_and_reference',sources=list(paths.values()),metadata={'counts':tables['summary'],'displayed_support':records})
    plt.close(fig)
    add_caption('Fig1_information_and_reference',
        'Information clocks, evaluation cohorts and observed reference support. (a) Schematic information sequence: a concentration sampled at s becomes available at s + d; the concentration estimate issued at the start of hour t uses only information already available and is not revised. Hourly transport accumulates as flow is observed during the hour; its completed integral is not known at the hour’s start. The schematic is not an observed event. (b,c) Data-eligible station-years and detected versus retained events in temporal evaluation and the spatial policy extension. Each spatial site supplies its own local concentration history. Retention requires the specified complete-hour coverage and observable flow boundaries. (d) Each point is a data-eligible station-year (13 temporal; 16 spatial). Hours: complete reference hours divided by calendar hours. Water: volume in complete reference hours divided by all available numeric nonnegative quarter-grid flow volume, including provisional and estimated flow. This denominator is observed flow volume, not unobserved total runoff. Seeds do not add environmental replication. No missing transport is imputed.')
    return report


def plot_context_transport(tables,paths):
    fig=new_figure(145);records=[]
    top_metrics=['top10pct_reference_load_fraction','load_fraction_q_ge_historical_q90']
    for col,stage in enumerate(['temporal','external']):
        x=.095+col*.495;summary=tables['summary'][stage]
        top=fig.add_axes([x,.63,.365,.275]);label_panel(top,'ab'[col],f"{'Temporal' if stage=='temporal' else 'Spatial'} · {summary['station_years']} station-years")
        for j,metric in enumerate(top_metrics):
            selected,rec=values_for(tables['site'],stage,metric);records.append(rec)
            top.scatter(j+ordered_spread(len(selected)),selected.value.to_numpy()*100,s=17,color='#0072B2',edgecolors='white',linewidths=.3)
        top.set(xticks=[0,1],xticklabels=['Highest-load\n10% of hours','Q ≥ historical\n90th percentile'],xlim=(-.42,1.42),ylim=(-3,105),yticks=[0,25,50,75,100])
        if col==0:top.set_ylabel('Share of observed load (%)')
        bottom=fig.add_axes([x,.205,.365,.275]);label_panel(bottom,'cd'[col],f"{'Temporal' if stage=='temporal' else 'Spatial'} · {summary['events_eligible_positive_load']} retained events")
        for j,hours in enumerate([24,72]):
            metric=f'load_fraction_occurred_first{hours}h'
            selected,rec=values_for(tables['event'],stage,metric,True);records.append(rec)
            bottom.scatter(j+ordered_spread(len(selected),.17),selected.value.to_numpy()*100,s=8,color='#A0A0A0',alpha=.68,linewidths=0,zorder=2)
            bottom.scatter([j-.21],[summary[f'equal_event_median_load_fraction_first{hours}h']*100],marker='s',s=27,color='black',edgecolors='white',linewidths=.4,zorder=4)
            bottom.scatter([j+.21],[summary[f'load_weighted_fraction_first{hours}h']*100],marker='D',s=28,color='#D55E00',edgecolors='white',linewidths=.4,zorder=4)
        bottom.set(xticks=[0,1],xticklabels=['First 24 h','First 72 h'],xlim=(-.42,1.42),ylim=(-2,108),yticks=[0,25,50,75,100])
        if col==0:bottom.set_ylabel('Load in first event window (%)')
    handles=[Line2D([],[],marker='o',color='#A0A0A0',ls='None',markersize=3),Line2D([],[],marker='s',color='black',ls='None',markersize=4),Line2D([],[],marker='D',color='#D55E00',ls='None',markersize=4)]
    legend_white_zone(fig,[.095,.065,.86,.055],handles,['Individual event','Event median','Load-weighted share'],3)
    report=export_figure(fig,'Fig2_transport_and_event_timing',sources=list(paths.values()),metadata={'displayed_values':records,'provided_aggregates':tables['summary'],
        'timing_identity':'Fixed 24/72 h from event onset, not actual first policy arrival; not an error lower bound.'})
    plt.close(fig)
    add_caption('Fig2_transport_and_event_timing',
        'Observed transport is concentrated in time, and timing summaries depend on their weighting. (a,b) Each point is a data-eligible station-year: the fraction of complete-hour reference load in the highest-load 10% of complete hours, and in complete hours with exact-hour flow at or above the preceding three-year flow 90th percentile. Top-hour count is ceil(0.10 × complete hours). (c,d) Fractions of retained-event reference load occurring during the first 24 or 72 h after event onset. Grey dots are individual events; black squares are unweighted event medians; vermilion diamonds weight events by their observed reference load. A short event can reach 100% while contributing little to the load-weighted total. These fixed-window quantities describe a hypothetical sample at event onset; they are not the actual first result arrival under a sampling policy and not a lower bound on estimation error. Only retained positive-reference-load events are included (46 temporal events at nine sites; 64 spatial events at eight sites). Event points are nested within sites, not independent environmental replicates. All quantities are restricted to observed reference support.')
    return report


def plot_reference_selection(tables,paths):
    fig=new_figure(142);records=[]
    for col,stage in enumerate(['temporal','external']):
        for row,metric in enumerate(['hours','q_peak_cms']):
            ax=fig.add_axes([.10+col*.495,.60-row*.395,.365,.275])
            label_panel(ax,'abcd'[row*2+col],('Temporal evaluation' if stage=='temporal' else 'Spatial policy extension'))
            for retained,color,style in [(True,'#0072B2','-'),(False,'#777777','--')]:
                selected,rec=values_for(tables['event'],stage,metric,retained);records.append(rec)
                values=np.sort(selected.value.to_numpy(float));positive=values>0
                if not positive.all():raise ValueError('Log distribution requires positive observed values')
                ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',color=color,ls=style,lw=.9)
            ax.set(xscale='log',ylim=(0,1.02),yticks=[0,.25,.5,.75,1],xlabel='Event duration (h)' if metric=='hours' else 'Observed flow peak (m³/s)')
            if metric=='hours':ax.set_xlim(10,3000)
            else:ax.set_xlim(1,30000)
            if col==0:ax.set_ylabel('Cumulative fraction of events')
    handles=[Line2D([],[],color='#0072B2',ls='-'),Line2D([],[],color='#777777',ls='--')]
    legend_white_zone(fig,[.18,.055,.67,.045],handles,['Retained for event error','Excluded from event error'],2)
    report=export_figure(fig,'FigS1_reference_selection',sources=list(paths.values()),metadata={'displayed_distributions':records,'distribution':'Empirical cumulative distribution, separately normalized within stage and retention group'},supplement=True)
    plt.close(fig)
    add_caption('FigS1_reference_selection',
        'Detected events retained and excluded from event-error evaluation. Empirical cumulative distributions compare event duration (a,b) and observed peak flow (c,d). Each distribution is normalized by its own event count: temporal 46 retained and 101 excluded; spatial 64 retained and 97 excluded. Events are nested within sites. Retention combines reference-hour coverage, observable flow boundaries and positive reference load. Exclusion does not necessarily mean a missing concentration at every hour. Peak-flow distributions reflect the station mix as well as event hydrology, and do not establish that missingness is confined to small events. The common logarithmic x-axis limits are held equal across cohorts; no significance test or missing-load imputation is performed.',supplement=True)
    return report


def plot_historical_support(tables,paths):
    fig=new_figure(142);records=[]
    for col,stage in enumerate(['temporal','external']):
        top=fig.add_axes([.095+col*.495,.61,.365,.285]);label_panel(top,'ab'[col],('Temporal histories' if stage=='temporal' else 'Spatial-extension histories'))
        data=tables['persistence'].loc[tables['persistence'].stage.eq(stage)&tables['persistence'].pair_support.eq('continuous_all_hours_qualified')]
        for j,lag in enumerate([6,24,72,168]):
            rows=data.loc[data.lag_hours.eq(lag)].sort_values(['site','year']);good=rows.loc[np.isfinite(rows.pearson_residual_autocorrelation)]
            top.scatter(j+ordered_spread(len(good),.13),good.pearson_residual_autocorrelation,s=14,color='#0072B2',edgecolors='white',linewidths=.3)
            records.append({'stage':stage,'lag_hours':lag,'rows':len(rows),'finite_displayed':len(good),'values':good[['site','year','pairs','pearson_residual_autocorrelation']].to_dict('records')})
        top.axhline(0,color='#C0C0C0',lw=.5);top.set(xticks=range(4),xticklabels=['6','24','72','168'],xlabel='Exact historical lag (h)',ylim=(-.12,1.03),yticks=[0,.25,.5,.75,1])
        if col==0:top.set_ylabel('Forward residual correlation')
        bottom=fig.add_axes([.095+col*.495,.175,.365,.275]);label_panel(bottom,'cd'[col],('Temporal historical-model error' if stage=='temporal' else 'Spatial historical-model error'))
        for j,metric in enumerate(['event_mean_absolute_relative_error','hourly_load_normalized_absolute_error']):
            selected,rec=values_for(tables['zero'],stage,metric);records.append(rec)
            bottom.scatter(j+ordered_spread(len(selected),.14),selected.value.to_numpy()*100,s=16,color='#555555',edgecolors='white',linewidths=.3)
        bottom.set(xticks=[0,1],xticklabels=['Event absolute\nrelative error','Hourly load\nnormalized error'],xlim=(-.4,1.4),ylim=(0,85),yticks=[0,20,40,60,80])
        if col==0:bottom.set_ylabel('Historical-model error (%)')
    report=export_figure(fig,'FigS2_historical_support',sources=list(paths.values()),metadata={'displayed_values':records,'descriptive_only':True},supplement=True)
    plt.close(fig)
    add_caption('FigS2_historical_support',
        'Historical residual persistence and the need for additional concentration feedback vary across station-years. (a,b) Each point is a historical calibration-year residual correlation, based on a forward model trained only on earlier permitted years, for one data-eligible target station-year. A pair at lag 6, 24, 72 or 168 h requires qualified labels at both endpoints and throughout the intervening interval; exact pair counts accompany the source table. The correlations do not identify an optimal correction-memory constant. (c,d) Original historical-model errors with no new concentration labels, averaged over model seeds within station-year. Event error is the mean absolute relative error across retained events; hourly normalized error is summed absolute load error divided by observed reference load. Undefined event-error rows are not drawn; hourly-error points retain all data-eligible station-years. Points, years and seeds are not independent rivers. These are descriptive context diagnostics, not a fitted relationship between persistence and policy benefit.',supplement=True)
    return report


def context_figures():
    tables,paths=context_tables()
    reports=[]
    for function in [plot_context_design,plot_context_transport,plot_reference_selection,plot_historical_support]:
        reports.append(function(tables,paths))
        print(json.dumps({'figure':reports[-1]['figure'],'geometry_and_exports_pass':reports[-1]['ok']},default=json_default),flush=True)
    (FIGURES/'context_figures_manifest.json').write_text(json.dumps({'created_utc':datetime.now(timezone.utc).isoformat(),
        'figures':[{'name':report['figure'],'ok':report['ok']} for report in reports],
        'script_sha256':digest(__file__),'sources':[{ 'path':str(path),'sha256':digest(path)} for path in paths.values()],
        'visual_review':'pending'},indent=2),encoding='utf-8')


def self_test():
    fig = new_figure(78)
    ax = fig.add_axes([.105,.29,.83,.52])
    label_panel(ax, 'a', 'Layout test — not research data')
    ax.plot([0,1,2],[0,1,.5], color='#0072B2', marker='o', label='Test series')
    ax.set(xlabel='Test position (unit)', ylabel='Test value (unit)', xticks=[0,1,2], yticks=[0,.5,1])
    legend_white_zone(fig,[.16,.055,.70,.09], [Line2D([],[],color='#0072B2',marker='o')], ['Test series'],1)
    clean = bbox_audit(fig)
    assert clean['ok'], json.dumps(clean,indent=2,default=json_default)
    # Every mechanism failure below must actually be caught, especially a left
    # title absent from ax.texts and from the default centred get_title().
    ax.set_title('Left title deliberately wider than the entire physical figure '*5,loc='left')
    assert bbox_audit(fig)['text_outside_canvas']
    label_panel(ax,'a','Layout test — not research data')
    text = ax.text(1,1,'Collision',ha='center',va='center',fontsize=7)
    assert bbox_audit(fig)['text_line_intersections']
    twin = ax.text(1,1,'Collision',ha='center',va='center',fontsize=7)
    assert bbox_audit(fig)['text_collisions']
    twin.remove();text.remove()
    text = ax.text(.1,.3,'Too small',fontsize=6)
    assert bbox_audit(fig)['small_text']
    text.remove()
    ax.legend(loc='upper right')
    assert bbox_audit(fig)['legend_intrusions']
    ax.get_legend().remove()
    xlim,ylim=ax.get_xlim(),ax.get_ylim()
    outside_line,=ax.plot([0,1],[0,100],color='black')
    ax.set(xlim=xlim,ylim=ylim)
    assert bbox_audit(fig)['data_vertices_outside_axes']
    outside_line.remove()
    report = export_figure(fig,'layout_self_test',metadata={'purpose':'Deterministic export and collision assertions'},qa_fixture=True)
    plt.close(fig)
    print(json.dumps({'status':'PASS','negative_layout_checks':6,'export_checks':report['export_checks'],
                      'preview':str(FIGURES/'_qa/layout_self_test_preview.png')},indent=2))


EARE = 'event_mean_absolute_relative_error'
POLICIES = ['uniform','deadline_only','flow_trigger','value']


def policy_handles(policies, lines=True):
    return [Line2D([],[],color=POLICY_STYLE[p]['color'],marker=POLICY_STYLE[p]['marker'],
                   ls=POLICY_STYLE[p]['ls'] if lines else 'None',markersize=3.5) for p in policies]


def read_final(folder,filename):
    path=ROOT/'results'/folder/filename
    return pd.read_csv(path,dtype={'site':str}),path


def plot_system_performance():
    aggregate,p1=read_final('summary_main_v1','aggregate_metrics.csv')
    paired,p2=read_final('summary_main_v1','paired_effects.csv')
    aggregate=aggregate.loc[aggregate.minimum_events.eq(1)]
    paired=paired.loc[paired.minimum_events.eq(1)&paired.measure.eq(EARE)&paired.baseline.isin(POLICIES[:3])]
    fig=new_figure(158)
    displayed=[]
    for col,stage in enumerate(['temporal','external']):
        rows=aggregate.loc[aggregate.stage.eq(stage)]
        ax=fig.add_axes([.115+col*.49,.655,.35,.255])
        label_panel(ax,'ab'[col],COHORT_LABELS[stage]+f" · {int(rows.stations.max())} sites")
        for policy in POLICIES:
            data=rows.loc[rows.policy.eq(policy)].sort_values('budget')
            if data.budget.tolist()!=[24,48,96]:raise ValueError('Missing budget/policy result')
            style=POLICY_STYLE[policy]
            ax.plot(range(3),data[EARE]*100,color=style['color'],ls=style['ls'],marker=style['marker'],lw=.9,markersize=3.5)
        zero=rows.loc[rows.policy.eq('no_new_labels')]
        if len(zero)!=1:raise ValueError('Unique historical comparator required')
        ax.axhline(float(zero[EARE].iloc[0])*100,color=POLICY_STYLE['zero']['color'],ls=(0,(4,3)),lw=.8)
        ax.set(xlim=(-.12,2.12),xticks=[0,1,2],xticklabels=['24','48','96'],xlabel='Annual sampling attempts',ylim=(12,35),yticks=[15,20,25,30,35])
        if col==0:ax.set_ylabel('Mean event absolute relative error (%)')
        bx=fig.add_axes([.115+col*.49,.175,.35,.335])
        label_panel(bx,'cd'[col],'Paired differences and 95% intervals')
        labels=[]
        y=0
        for budget in [24,48,96]:
            for policy in ['uniform','flow_trigger','deadline_only']:
                r=paired.loc[paired.stage.eq(stage)&paired.budget.eq(budget)&paired.baseline.eq(policy)]
                if len(r)!=1:raise ValueError('Nonunique paired main contrast')
                r=r.iloc[0];s=POLICY_STYLE[policy];v=float(r.mean_difference)*100
                bx.errorbar(v,y,xerr=np.array([[v-float(r.station_ci_low)*100],[float(r.station_ci_high)*100-v]]),
                    fmt=s['marker'],color=s['color'],markersize=3.5,elinewidth=.8,capsize=2)
                short='Deadline' if policy=='deadline_only' else s['label']
                labels.append(f"{short} · {budget}")
                displayed.append(r.to_dict());y+=1
            y+=.4
        ys=[j+i*.4 for i in range(3) for j in range(i*3,i*3+3)]
        bx.axvline(0,color='#B0B0B0',lw=.6,zorder=0)
        bx.set(yticks=ys,yticklabels=labels,ylim=(9.4,-.6),xlim=(-7,14),xticks=[-5,0,5,10],xlabel='Baseline − load-value error (pp)')
        bx.spines['left'].set_visible(False);bx.tick_params(axis='y',length=0,pad=4)
    policies=POLICIES+['no_new_labels']
    handles=policy_handles(POLICIES)+[Line2D([],[],color=POLICY_STYLE['zero']['color'],ls=(0,(4,3)),lw=.8)]
    legend_white_zone(fig,[.04,.035,.92,.06],handles,[POLICY_STYLE[p]['label'] for p in policies],5)
    report=export_figure(fig,'Fig3_complete_system_performance',sources=[p1,p2],metadata={'aggregates':aggregate.to_dict('records'),
        'paired_displayed':displayed,'difference_sign':'baseline minus load value; positive favours load value','ci':'station paired bootstrap 95%','minimum_events':1})
    plt.close(fig)
    add_caption('Fig3_complete_system_performance',
        'Complete sampling systems under the same online reconstruction rule. (a,b) Mean station-level event absolute relative error for all four policies at 24, 48 and 96 annual samples, with actual laboratory delay fixed at 24 h. All use the latest returned residual with arrival-origin exponential decay (time constant 168 h). The horizontal historical-model line uses zero new labels and is not charged any of the plotted sample budgets. Temporal evaluation contains nine event-eligible sites and 46 retained events; the spatial policy extension contains eight sites and 64 retained events across 2023–2024. Each spatial site provides its own historical calibration data. Seed and year averaging precede equal-site averaging. (c,d) Paired station mean differences (baseline minus load value), with 95% station-bootstrap intervals from the authoritative analysis. Positive values favour load value; intervals crossing zero show uncertain direction at this sampling level. Differences are percentage points of relative event error, not kilograms of nitrogen removed or recovered. The event endpoint gives events equal weight within site. HUC4-cluster sensitivity intervals and all-site hourly metrics are reported separately.')
    return report


def plot_reconstruction_memory():
    aggregate,p1=read_final('summary_factorial_v1','aggregate_metrics.csv')
    contrasts,p2=read_final('diagnostics_v1','factor_family_contrasts.csv')
    aggregate=aggregate.loc[aggregate.minimum_events.eq(1)&aggregate.budget.eq(96)]
    aggregate['half_life_hours']=pd.to_numeric(aggregate.half_life_hours)
    fig=new_figure(152)
    family_style={'latest_residual':('#D55E00','o','Latest residual'),'rff_pooled':('#0072B2','s','Pooled RFF')}
    policies=['uniform','flow_trigger','deadline_only'];memories=sorted(aggregate.half_life_hours.unique())
    for col,policy in enumerate(policies):
        left=.10+col*.305
        ax=fig.add_axes([left,.635,.235,.265]);label_panel(ax,'abc'[col],POLICY_STYLE[policy]['label']+' calendar')
        for family,(color,marker,label) in family_style.items():
            for age,ls,fill in [('arrival','-','full'),('sample','--','none')]:
                data=aggregate.loc[aggregate.policy.eq(policy)&aggregate.reconstructor_family.eq(family)&aggregate.age_origin.eq(age)].sort_values('half_life_hours')
                if len(data)!=3:raise ValueError('Incomplete reconstruction factorial')
                ax.plot(range(3),data[EARE]*100,color=color,marker=marker,ls=ls,fillstyle=fill,markersize=3.7,lw=.8)
        ax.set(xlim=(-.13,2.13),xticks=range(3),xticklabels=['116.45','720','2160'],xlabel='Nominal half-life (h)',ylim=(13,23),yticks=[14,16,18,20,22])
        if col==0:ax.set_ylabel('Mean event absolute relative error (%)')
        bx=fig.add_axes([left,.20,.235,.27]);label_panel(bx,'def'[col],'Paired family differences')
        labels=[]
        for j,memory in enumerate(memories):
            for offset,age,marker in [(-.12,'arrival','o'),(.12,'sample','s')]:
                data=contrasts.loc[contrasts.policy.eq(policy)&np.isclose(contrasts.half_life_hours,memory)&contrasts.age_origin.eq(age)]
                if len(data)!=1:raise ValueError('Incomplete family contrast')
                r=data.iloc[0];v=r.mean_rff_minus_latest*100
                bx.errorbar(v,j+offset,xerr=[[v-r.station_ci_low*100],[r.station_ci_high*100-v]],fmt=marker,
                    color='#222222',mfc='#222222' if age=='arrival' else 'white',markersize=3.5,lw=.8,capsize=2)
        bx.axvline(0,color='#B0B0B0',lw=.6,zorder=0)
        bx.set(yticks=range(3),yticklabels=['116.45','720','2160'],ylim=(2.5,-.5),xlim=(-14,10),xticks=[-10,0,10],xlabel='Pooled − latest error (pp)')
        if col==0:bx.set_ylabel('Nominal half-life (h)')
    h=[Line2D([],[],color=family_style[f][0],marker=family_style[f][1],ls=ls,fillstyle=fill,markersize=3.5)
       for f in family_style for age,ls,fill in [('arrival','-','full'),('sample','--','none')]]
    labels=[family_style[f][2]+' · '+age for f in family_style for age in ['arrival','sample']]
    legend_white_zone(fig,[.05,.035,.90,.075],h,labels,2)
    report=export_figure(fig,'Fig4_reconstruction_memory',sources=[p1,p2],metadata={'factorial':aggregate.to_dict('records'),'paired':contrasts.to_dict('records'),
       'scope':'development fixed calendars; nominal half-life matched, effective memory not equivalent','ci':'station paired bootstrap 95%'})
    plt.close(fig)
    add_caption('Fig4_reconstruction_memory',
        'Reconstruction family, nominal memory and age origin under fixed acquisition calendars. (a–c) All 36 development configurations: three sampling calendars, two reconstruction families, three nominal half-lives and sample- versus arrival-origin ageing. Calendars are held fixed at 96 samples per year; actual delay is 24 h; innovation feedback is disabled (ρ = 0). All points average the seven development sites after seed and year aggregation. Solid filled symbols indicate arrival-origin ageing; dashed open symbols indicate sample-origin ageing. (d–f) Paired mean error difference between pooled random Fourier features (RFF) and latest-residual reconstruction at the same calendar, nominal half-life and age origin, with 95% station-bootstrap intervals; circle = arrival, open square = sample. Positive differences favour latest-residual reconstruction. The 116.45 h nominal half-life equals a 168 h exponential time constant. Matching nominal half-life does not match effective memory: a latest-residual estimator replaces its previous residual, whereas the pooled estimator retains multiple contributions. These fixed-calendar component comparisons do not evaluate a newly optimized sampling policy and do not establish a universal ranking of reconstruction families.')
    return report


def plot_delay_and_fallback():
    contrasts,p1=read_final('diagnostics_v1','mechanism_contrasts.csv')
    attempts,p2=read_final('diagnostics_v1','attempt_summaries.csv')
    check_path=ROOT/'results/experiments_completion_checks_v1.json'
    checks=json.loads(check_path.read_text())
    queue=[r for r in checks['mechanisms_temporal_v1']['queue'] if r['scenario']=='delay_aware_pending']
    fig=new_figure(143)
    ax=fig.add_axes([.235,.65,.315,.25]);label_panel(ax,'a','Scoring assumptions at fixed actual delay')
    labels=[]
    for j,r in enumerate(contrasts.itertuples()):
        v=r.alternative_minus_aware*100
        ax.errorbar(v,j,xerr=[[v-r.station_ci_low*100],[r.station_ci_high*100-v]],fmt='o',color='#333333',capsize=2,markersize=3.5,lw=.8)
        label=('Score delay = 0' if r.alternative=='delay_zero_pending' else 'Pending omitted')+f'\nActual delay {r.delay_hours} h'
        labels.append(label)
    ax.axvline(0,color='#B0B0B0',lw=.6)
    ax.set(yticks=range(3),yticklabels=labels,ylim=(2.55,-.55),xlim=(-.85,.55),xticks=[-.5,0,.5],xlabel='Alternative − aware error (pp)')
    ax.spines['left'].set_visible(False);ax.tick_params(axis='y',length=0,pad=5)
    bx=fig.add_axes([.72,.65,.225,.25]);label_panel(bx,'b','Queue activation')
    queue=sorted(queue,key=lambda r:r['delay_hours'])
    ratios=[r['<lambda_0>']/r['count']*100 for r in queue]
    bx.plot([0,1],ratios,'o',color='#0072B2',markersize=4)
    bx.set(xticks=[0,1],xticklabels=['24','72'],xlim=(-.3,1.3),ylim=(-3,103),yticks=[0,25,50,75,100],
           xlabel='Actual delay (h)',ylabel='Candidates with a pending result (%)')
    # Denominator: event-primary station set, as provided in the descriptive table.
    scope=[s for s in attempts.scope.unique() if 'event' in s]
    if len(scope)!=1:raise ValueError('Explicit event-primary attempt scope required')
    selected=attempts.loc[attempts.scope.eq(scope[0])]
    for col,stage in enumerate(['temporal','external']):
        cx=fig.add_axes([.105+col*.49,.205,.355,.255]);label_panel(cx,'cd'[col],COHORT_LABELS[stage])
        for p in POLICIES:
            rows=selected.loc[selected.stage.eq(stage)&selected.policy.eq(p)].sort_values('budget')
            if len(rows)!=3:raise ValueError('Incomplete fallback comparison')
            s=POLICY_STYLE[p]
            cx.plot(range(3),rows.fallback_fraction*100,color=s['color'],marker=s['marker'],ls=s['ls'],lw=.9,markersize=3.5)
        cx.set(xticks=range(3),xticklabels=['24','48','96'],xlim=(-.12,2.12),ylim=(-3,105),yticks=[0,25,50,75,100],xlabel='Annual sampling attempts')
        if col==0:cx.set_ylabel('Attempts forced by block deadline (%)')
    legend_white_zone(fig,[.08,.055,.84,.05],policy_handles(POLICIES),[POLICY_STYLE[p]['label'] for p in POLICIES],4)
    report=export_figure(fig,'Fig5_delay_queue_and_fallback',sources=[p1,p2,check_path],metadata={'contrasts':contrasts.to_dict('records'),
       'queue':queue,'attempts':selected.to_dict('records'),'queue_denominator':'eligible candidate evaluations pooled across all data-eligible sites, three seeds and the aware scenario at B96',
       'paired_denominator':'nine temporal event-eligible stations'})
    plt.close(fig)
    add_caption('Fig5_delay_queue_and_fallback',
        'Delay and pending-result mechanisms are tested under fixed realized laboratory delay. (a) At 96 samples per year, paired temporal station mean error differences between each altered scoring rule and delay-aware, pending-aware scoring, with 95% station-bootstrap intervals (nine event-eligible sites). The score-delay-zero variant still receives actual results after 24 or 72 h; the pending-omitted variant retains the actual 72 h delay. Positive differences favour the fully aware rule. No new effect of actual turnaround speed is estimated by these contrasts. (b) Fraction of eligible candidate evaluations with a result pending in the fully aware scenario: 0 of 38,019 at 24 h; 22,455 of 37,925 at 72 h, at most one pending result. Candidate evaluations pool all 13 data-eligible temporal sites and three seeds and are an operational count, not independent statistical replicates. At 24 h delay, the minimum 24 h spacing leaves the pending correction inactive at eligible candidates. (c,d) Mean station-level fraction of attempts forced by block-deadline fallback, restricted to each cohort’s event-primary site set. Regular attempts are scheduled and not fallback attempts; the block-deadline policy consists entirely of fallback attempts. High fallback shares constrain how much the adaptive score can change the acquisition calendar. Fallback alone neither proves nor disproves useful concentration feedback.')
    return report


def plot_station_heterogeneity():
    data,p1=read_final('summary_main_v1','station_metrics.csv')
    data=data.loc[data.minimum_events.eq(1)&data.budget.eq(96)&data.policy.isin(['value','flow_trigger'])]
    fig=new_figure(110);records=[]
    for col,stage in enumerate(['temporal','external']):
        rows=data.loc[data.stage.eq(stage)].pivot(index='site',columns='policy',values=EARE).sort_index()
        difference=(rows.flow_trigger-rows.value)*100
        ax=fig.add_axes([.15+col*.49,.24,.31,.61]);label_panel(ax,'ab'[col],COHORT_LABELS[stage])
        ax.axvline(0,color='#B0B0B0',lw=.6,zorder=0)
        ax.hlines(np.arange(len(rows)),0,difference,color='#D55E00',lw=.8)
        ax.scatter(difference,np.arange(len(rows)),s=18,color='#D55E00',marker='D',zorder=3)
        ax.set(yticks=np.arange(len(rows)),yticklabels=rows.index,ylim=(len(rows)-.4,-.6),xlim=(-15,15),xticks=[-10,0,10],xlabel='Flow − load-value error (pp)')
        ax.spines['left'].set_visible(False);ax.tick_params(axis='y',length=0,pad=4)
        records.extend({'stage':stage,'site':site,'flow_minus_value_pp':float(value)} for site,value in difference.items())
    report=export_figure(fig,'FigS3_station_heterogeneity',sources=[p1],metadata={'station_contrasts':records,'budget':96,'ci':'none; individual station descriptive differences'},supplement=True)
    plt.close(fig)
    add_caption('FigS3_station_heterogeneity','Station-specific flow-trigger minus load-value event error at 96 samples per year and 24 h actual delay, using the same latest-residual reconstruction. Positive values favour load value. All event-eligible sites are shown in station-number order, including negative differences; no site-specific uncertainty intervals are inferred from seed replication. For the spatial extension, years and seeds are averaged within site. These percentage-point differences in relative event error are not absolute-load improvements.',supplement=True)
    return report


def result_figures():
    for function in [plot_system_performance,plot_reconstruction_memory,plot_delay_and_fallback,plot_station_heterogeneity]:
        report=function();print(json.dumps({'figure':report['figure'],'geometry_and_exports_pass':report['ok']},default=json_default),flush=True)


def plot_event_cases():
    folder=ROOT/'results'
    paths=[folder/'context_case_selection.csv',folder/'context_case_hourly.csv',folder/'context_case_attempts.csv',folder/'context_case_manifest.json']
    selection,hourly,attempts=[pd.read_csv(p,dtype={'site':str}) for p in paths[:3]]
    hourly['time_utc']=pd.to_datetime(hourly.time_utc,utc=True)
    for c in ['sample_time','arrival_time']:attempts[c]=pd.to_datetime(attempts[c],utc=True)
    fig=new_figure(170);records=[]
    columns=[('largest_improvement','Largest improvement'),('nearest_median_difference','Median difference'),('largest_harm','Largest deterioration')]
    for col,(rule,title) in enumerate(columns):
        chosen=selection.loc[selection.selection.eq(rule)]
        if len(chosen)!=1:raise ValueError('Case selection is not unique')
        chosen=chosen.iloc[0];data=hourly.loc[hourly.case_id.eq(chosen.case_id)].sort_values('time_utc')
        start=pd.Timestamp(chosen.start_time);end=pd.Timestamp(chosen.end_time_exclusive)
        t=(data.time_utc-start).dt.total_seconds().to_numpy()/3600
        endh=(end-start).total_seconds()/3600;limits=(t.min(),t.max());event=data.within_event.to_numpy(bool)
        ref=data.cumulative_event_reference_load_kg.to_numpy(float);finalref=float(np.nanmax(ref))
        if finalref<=0:raise ValueError('Nonpositive case reference load')
        left=.12+col*.305;axes=[]
        specs=[(.785,.105),(.545,.17),(.315,.16),(.175,.072)]
        for row,(bottom,height) in enumerate(specs):
            ax=fig.add_axes([left,bottom,.25,height]);axes.append(ax)
            ax.axvspan(0,endh,color='#F2F2F2',lw=0,zorder=-4)
            for h in [0,endh]:ax.axvline(h,color='#B0B0B0',ls=':',lw=.5,zorder=-3)
            ax.set_xlim(*limits)
            if row<3:ax.tick_params(axis='x',labelbottom=False)
            label_panel(ax,'abcdefghijkl'[row*3+col],title+'\n'+chosen.site+' · '+start.strftime('%d %b') if row==0 else None)
        axes[0].plot(t,data.q_at_time_cms,color='#222222',lw=.85)
        axes[0].set_ylim(bottom=0);axes[0].yaxis.set_major_locator(mpl.ticker.MaxNLocator(3))
        axes[1].plot(t,data.reference_point_mg_l,color='black',lw=1.0,zorder=5)
        case_metrics=[]
        for policy in POLICIES:
            s=POLICY_STYLE[policy]
            # Alternating dash patterns preserve genuinely coincident trajectories.
            axes[1].plot(t,data[f'prediction_{policy}_mg_l'],color=s['color'],ls=s['ls'],lw=.9,
                         marker=s['marker'],markevery=(POLICIES.index(policy)*7+5,37),markersize=2.2)
            error=(data[f'cumulative_event_predicted_load_{policy}_kg'].to_numpy(float)-ref)/finalref*100
            # A row starts the concentration hour; its integrated mass is only
            # complete one hour later. Do not draw future flow at the issue time.
            cumulative_time=np.r_[0,t[event]+1]
            cumulative_error=np.r_[0,error[event]]
            axes[2].plot(cumulative_time,cumulative_error,color=s['color'],ls=s['ls'],lw=.9,
                         marker=s['marker'],markevery=(POLICIES.index(policy)*7+5,37),markersize=2.2)
            case_metrics.append({'policy':policy,'end_relative_error_percent':float(error[np.flatnonzero(event)[-1]])})
            one=attempts.loc[attempts.case_id.eq(chosen.case_id)&attempts.policy.eq(policy)]
            y=POLICIES.index(policy)
            for r in one.itertuples():
                sample=(r.sample_time-start).total_seconds()/3600;arrival=(r.arrival_time-start).total_seconds()/3600
                if limits[0]<=sample<=limits[1]:
                    axes[3].scatter(sample,y-.12,marker='s' if r.forced_deadline else 'o',s=14,facecolor='white',edgecolor=s['color'],linewidths=.7,zorder=4)
                if limits[0]<=arrival<=limits[1]:
                    usable=bool(r.label_success and r.label_available_by_horizon)
                    axes[3].scatter(arrival,y+.12,marker='^' if usable else 'x',s=14,color=s['color'],linewidths=.7,zorder=4)
        axes[1].set_ylim(bottom=0);axes[1].yaxis.set_major_locator(mpl.ticker.MaxNLocator(3))
        axes[2].axhline(0,color='#A0A0A0',lw=.5,zorder=-2);axes[2].set_ylim(-50,135);axes[2].set_yticks([-40,0,40,80,120])
        axes[3].set_ylim(3.5,-.5);axes[3].set_yticks(range(4),['Regular','Deadline','Flow','Value'] if col==0 else ['']*4)
        axes[3].tick_params(axis='y',length=0,pad=3);axes[3].spines['left'].set_visible(False)
        ticks=[-48,0,48] if endh<50 else [-48,0,96,192]
        axes[3].set_xticks([tick for tick in ticks if limits[0]<=tick<=limits[1]])
        if col==0:
            axes[0].set_ylabel('Flow (m³/s)');axes[1].set_ylabel('Concentration (mg N/L)')
            axes[2].set_ylabel('Cumulative load error\n(% of event reference)')
        records.append({'selection':chosen.to_dict(),'final_reference_load_kg':finalref,'x_limits_hours':limits,'end_errors':case_metrics})
    fig.text(.575,.121,'Hours relative to event onset',ha='center',fontsize=7)
    curve_handles=[Line2D([],[],color='black',lw=1)]+policy_handles(POLICIES)
    legend_white_zone(fig,[.055,.067,.91,.035],curve_handles,['Reference']+[POLICY_STYLE[p]['label'] for p in POLICIES],5)
    marker_handles=[Line2D([],[],marker='o',mfc='white',mec='#555555',ls='None'),Line2D([],[],marker='s',mfc='white',mec='#555555',ls='None'),
       Line2D([],[],marker='^',color='#555555',ls='None'),Line2D([],[],marker='x',color='#555555',ls='None')]
    legend_white_zone(fig,[.055,.018,.91,.035],marker_handles,['Sample','Deadline sample','Usable return','Unusable return'],4)
    report=export_figure(fig,'Fig6_real_event_processes',sources=paths,metadata={'cases':records,'budget':96,'seed':41,
      'display':'Light shading is the defined event. Curves can genuinely coincide; no artificial displacement is used.'})
    plt.close(fig)
    add_caption('Fig6_real_event_processes',
       'Real event trajectories show improvement, neutral difference and deterioration. Columns follow the largest improvement, nearest median difference and largest deterioration in the load-value versus flow-trigger absolute relative error among the 46 retained temporal events, using 96 samples and seed 41. Selection is explicitly post-result and deterministic; examples do not estimate frequency of success or validate a mechanism. The two extreme cases occur at the same station in adjacent events and are retained without substitution. Rows show observed flow (a–c), exact-hour reference concentration and four online concentration estimates (d–f), cumulative signed load error on common complete-hour reference support (g–i), and independently aligned collection/return markers (j–l). Completed hourly mass integrals are plotted at the end of their hour; concentration estimates are plotted at issue time. Cumulative error is divided by the final observed event reference load, not by a running denominator. Light shading marks each defined event; curves can genuinely coincide. Samples are open circles, forced-deadline samples open squares, usable returns filled triangles, and unusable returns crosses. Samples and returns are slightly separated vertically within each policy row only for legibility; their times are unchanged. Samples taken before event onset may return within the event. Predictions never use future returns and are not retrospectively revised. Return timing alone does not show benefit. The case records are observed-support reconstructions, not continuously complete river-load truth.')
    return report


def plot_actual_arrivals():
    folder=ROOT/'results'
    paths=[folder/'context_arrival_summary.csv',folder/'context_arrival_station_means.csv',folder/'context_arrival_summary_manifest.json']
    data=pd.read_csv(paths[0]);fig=new_figure(88)
    specs=[('fraction_load_before_first_usable_arrival','Load before first usable return (%)','Observed transport timing'),
           ('no_usable_arrival_within_event','Events with no usable return (%)','Absence of a within-event return')]
    for col,(metric,ylabel,title) in enumerate(specs):
        ax=fig.add_axes([.105+col*.49,.30,.355,.48]);label_panel(ax,'ab'[col],title)
        for policy in POLICIES:
            one=data.loc[data.policy.eq(policy)].sort_values('budget');s=POLICY_STYLE[policy]
            if one.budget.tolist()!=[24,48,96]:raise ValueError('Incomplete arrival summary')
            ax.plot(range(3),one[metric]*100,color=s['color'],ls=s['ls'],marker=s['marker'],markersize=3.5,lw=.9)
        ax.set(xticks=range(3),xticklabels=['24','48','96'],xlim=(-.12,2.12),ylim=(-2,103),yticks=[0,25,50,75,100],xlabel='Annual sampling attempts',ylabel=ylabel)
    legend_white_zone(fig,[.08,.065,.84,.06],policy_handles(POLICIES),[POLICY_STYLE[p]['label'] for p in POLICIES],4)
    report=export_figure(fig,'FigS4_actual_result_arrivals',sources=paths,metadata={'summary':data.to_dict('records'),
      'denominator':'46 retained temporal events nested in nine sites; seed means within event, event means within site-year, year means within site, equal site means',
      'no_return_convention':'load fraction is 1 if no usable result returns during event; earlier useful results may nevertheless be available'},supplement=True)
    plt.close(fig)
    add_caption('FigS4_actual_result_arrivals',
       'Actual concentration-return timing under the revised temporal replay with 24 h laboratory delay. (a) Fraction of observed event reference load occurring before the first usable within-event result return. A returned result may originate from a pre-event sample. When no usable result returns within an event, the fraction is set to one; an earlier returned result can nevertheless still inform prediction. (b) Fraction of events with no usable within-event return. Both summaries average seeds within each of the 46 physical events, then events within site-year, years within site, and the nine event-eligible sites equally. They do not treat three seed replays as independent events. These are descriptive timing measures, not the fixed-onset windows in Fig. 2, measures of successful correction, or error lower bounds. The ordinate in (a) is not the cohort’s load-weighted total.',supplement=True)
    return report


def plot_candidate_diagnostic():
    data,p1=read_final('diagnostics_v1','candidate_plot_data.csv')
    summary_path=ROOT/'results/diagnostics_v1/candidate_summary.json'
    summary=json.loads(summary_path.read_text())
    if not data.eligible_diagnostic.all():raise ValueError('Candidate plotting file contains ineligible cases')
    fig=new_figure(94)
    ax=fig.add_axes([.115,.28,.35,.53]);label_panel(ax,'a','Single-candidate replay · 82 candidates')
    ax.scatter(data.acquisition_score,data.absolute_error_reduction_kg,s=13,color='#0072B2',alpha=.75,edgecolors='white',linewidths=.2)
    ax.axhline(0,color='#B0B0B0',lw=.6,zorder=0)
    ax.set(xscale='log',yscale='symlog',xlim=(1,1e10),ylim=(-30000,200000),xticks=[1,1e3,1e6,1e9],yticks=[-10000,0,10000,100000],
           xlabel='Acquisition score (proxy units)',ylabel='Absolute load-error reduction (kg N)')
    ax.set_yscale('symlog',linthresh=1000)
    ax.set_yticks([-10000,-1000,0,1000,10000,100000])
    ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda value,pos:f'{value:,.0f}'))
    bx=fig.add_axes([.625,.28,.32,.53]);label_panel(bx,'b','Within-site ranks')
    bx.scatter(data.score_rank_within_site,data.utility_rank_within_site,s=13,color='#0072B2',alpha=.75,edgecolors='white',linewidths=.2)
    bx.set(xlim=(0,1.04),ylim=(0,1.04),xticks=[0,.25,.5,.75,1],yticks=[0,.25,.5,.75,1],
           xlabel='Within-site score rank',ylabel='Within-site error-reduction rank')
    report=export_figure(fig,'FigS5_score_and_observed_utility',sources=[p1,summary_path],metadata={'diagnostic_summary':summary,
      'candidate_rows':data[['site','year','sample_time','acquisition_score','absolute_error_reduction_kg','score_rank_within_site','utility_rank_within_site']].to_dict('records'),
      'axis_note':'Raw score horizontal logarithm; signed utility vertical symmetric logarithm, linear threshold 1000 kg N. No regression or p value.'},supplement=True)
    plt.close(fig)
    add_caption('FigS5_score_and_observed_utility',
       'The acquisition score is a proxy rather than an observed-utility estimate. (a) An independently specified post-result diagnostic adds one candidate sample to an otherwise fixed replay and compares absolute accumulated load error over its diagnostic window. Positive kilogram differences mean less absolute load error after the added result; negative differences mean more. Of 168 planned candidates, 82 qualified for this diagnostic (50 beneficial, 32 harmful), spanning seven sites. The raw score uses a logarithmic x axis. The signed error reduction uses a symmetric logarithmic y axis, linear within ±1,000 kg N, so both negative outcomes and the large positive outcome remain visible. (b) Fractional ranks computed within site, using the supplied diagnostic table; tied or identical ranks may overlap. No fit, significance test, subgroup search or causal claim is added. The window-level added-sample contrast is not the effect of deploying an altered closed-loop policy. Eligibility requires spacing, usable concentration and the specified window reference coverage, and limits the diagnostic population. Absolute kilogram improvements and relative event-error improvements are distinct outcomes.',supplement=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true',help='Run geometry/export tests with explicitly non-scientific test coordinates')
    parser.add_argument('--context',action='store_true',help='Render final context Figures 1/2 and supporting reference/history figures')
    parser.add_argument('--results',action='store_true',help='Render final complete-system, reconstruction and mechanism summaries')
    parser.add_argument('--cases',action='store_true',help='Render the three final, independently verified event cases')
    parser.add_argument('--diagnostics',action='store_true',help='Render actual-return timing and single-candidate diagnostics')
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.context:
        context_figures()
    elif args.results:
        result_figures()
    elif args.cases:
        report=plot_event_cases();print(json.dumps({'figure':report['figure'],'geometry_and_exports_pass':report['ok']},default=json_default))
    elif args.diagnostics:
        for function in [plot_actual_arrivals,plot_candidate_diagnostic]:
            report=function();print(json.dumps({'figure':report['figure'],'geometry_and_exports_pass':report['ok']},default=json_default),flush=True)
    else:
        parser.error('Scientific plotting awaits the frozen revision result tables; use --self-test for infrastructure checks.')


if __name__ == '__main__':
    main()
