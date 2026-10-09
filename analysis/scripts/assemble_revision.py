"""Assemble one substantive article with source-generated tables and inline figures."""
from pathlib import Path
import re,json
import pandas as pd
R=Path(__file__).resolve().parents[1];P=R.parent
M=R/'manuscript';F=R/'figures'
def tab(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,row))+' |' for row in rows])
def read(name):return (M/name).read_text(encoding='utf-8').strip()
def figure(prefix,sub='main'):
    files=list((F/sub).glob(prefix+'*.caption.txt'))
    assert len(files)==1,(prefix,files)
    stem=files[0].name.replace('.caption.txt','')
    cap=files[0].read_text(encoding='utf-8').strip().rstrip('.')
    number=re.match(r'Fig(S?\d+)',prefix).group(1)
    cap=f'**Fig. {number}** '+cap
    return f'![{prefix}](../figures/{sub}/{stem}.png){{width=7.204724in}}\n\n'+cap
def apa_author(a):
    if a=='U.S. Geological Survey':return a
    parts=a.split();suffix=parts.pop() if parts[-1] in ['Jr.','Sr.','II','III','IV'] else ''
    n=2 if len(parts)>2 and parts[-2] in ['Bin','van','von','de','ter','van’t',"van't"] else 1
    family=' '.join(parts[-n:]);given=parts[:-n]
    initials=[]
    for x in given:
        if '.' in x:initials.extend(y+'.' for y in x.split('.') if y)
        else:initials.append(x[0]+'.')
    return family+', '+' '.join(initials)+(', '+suffix if suffix else '')
def main():
    a=pd.read_csv(R/'results/summary_main_v1/aggregate_metrics.csv');a=a[a.minimum_events==1]
    labels={'uniform':'Periodic','flow_trigger':'Flow trigger','deadline_only':'Block deadline','value':'Load value','no_new_labels':'Historical only'}
    def cell(stage,policy,B):
        g=a[(a.stage==stage)&(a.policy==policy)&(a.budget==B)]
        assert len(g)==1;return g.iloc[0]
    t1='**Table 1** Evaluation support after data qualification and event screening\n\n'+tab(['Assessment records','Data sites / site-years','Primary sites / site-years','Eligible / defined events','Primary HUC4 groups','Reference-water median (%)'],[
        ['Development 2023–2024','7 / 14','7 / 13','36 / 65','5','91.48'],
        ['Additional stations 2023–2024','8 / 16','8 / 14','64 / 161','6','94.58'],
        ['Temporal 2025','13 / 13','9 / 9','46 / 147','5','94.39']])+ '\n\nWater support is the median across data-eligible station-years, using complete-reference volume divided by all observed finite nonnegative quarter-hour-grid discharge volume. Event endpoints require at least one eligible positive-mass episode. HUC4 groups describe geography rather than independent replication. Development and temporal records can involve the same stations.'
    rows=[]
    for policy in ['uniform','flow_trigger','deadline_only','value','no_new_labels']:
        rows.append([labels[policy]]+[f'{100*cell(stage,policy,0 if policy=="no_new_labels" else B).event_mean_absolute_relative_error:.2f}' for stage in ['temporal','external'] for B in [24,48,96]])
    t2='**Table 2** Complete-system event mean absolute relative error (%)\n\n'+tab(['System','Temporal 24','Temporal 48','Temporal 96','Additional 24','Additional 48','Additional 96'],rows)+'\n\nBudgets are annual attempted samples; all paid systems use the latest returned residual, a 168 h exponential time constant from arrival and a 24 h actual delay. Events are averaged within station-year and seed, seeds within station-year, years within station and then stations equally. The historical-only result has zero purchases and is repeated solely for comparison. All paid results are revision post-result complete-system replays.'
    rows=[]
    for stage in ['temporal','external']:
        for policy in ['uniform','flow_trigger','deadline_only','value','no_new_labels']:
            v=cell(stage,policy,0 if policy=='no_new_labels' else 96)
            rows.append(['Temporal' if stage=='temporal' else 'Additional',labels[policy],f'{v.event_mean_signed_error_kg/1000:+.2f}',f'{v.event_mean_absolute_error_kg/1000:.2f}',f'{100*v.event_fraction_within_20pct:.2f}',f'{100*v.event_fraction_worse_than_50pct:.2f}'])
    t3='**Table 3** Error magnitude and illustrative accuracy scenarios at budget 96\n\n'+tab(['Records','System','Signed mass error (10³ kg N)','Absolute mass error (10³ kg N)','Within 20% (%)','Above 50% (%)'],rows)+'\n\nSigned error is predicted minus reference event mass; its sign is not a quality ranking. Absolute error is averaged with the same event/seed/year/station hierarchy as Table 2, and thus includes river-size variation. Threshold proportions use that hierarchy and are analyst-selected scenarios, not regulatory standards. The historical-only comparator has zero purchases. Complete 10%, 20% and secondary outcomes are in Online Resource 2.'
    intro=read('Introduction.md');methods=read('Methods.md');results=read('Results.md');discussion=read('Discussion.md')
    methods=methods.replace('An analyst issued a provisional hourly concentration estimate and associated transport estimate, using only information available by that hour.', 'An analyst issued a provisional concentration estimate at the start of each hour using only information then available. That fixed concentration was combined with discharge as it was subsequently observed to accumulate transport; the complete hourly mass became evaluable after its discharge intervals elapsed.')
    methods=methods.replace('all finite nonnegative observed native discharge values, including estimated or provisional values, subject to the documented interval assumptions', 'all finite nonnegative quarter-hour-grid discharge readings, each weighted by 900 s regardless of concentration availability, including estimated or provisional discharge values')
    (M/'Methods.md').write_text(methods+'\n',encoding='utf-8')
    anchor='Quality and boundary screening retained 46 of 147 defined temporal events and 64 of 161 additional-station events. The resulting event population is narrower than all high-flow transport.'
    results=results.replace(anchor,anchor+'\n\n'+t1+'\n\n'+figure('Fig1_'))
    results=results.replace('## Complete systems with a common simple output rule',figure('Fig2_')+'\n\n## Complete systems with a common simple output rule')
    anchor='Thus scheduling before quota expiry added information in this setting, but the data did not establish a stable advantage over a simple hydrological trigger.'
    # Table and figure remain near the complete-system comparisons.
    para='All four revised systems completed their nominal attempt budgets while respecting result availability, block quotas and minimum spacing. Their event errors are shown together with the zero-label comparator in Table 2 and Fig. 3.'
    results=results.replace(para,para+'\n\n'+t2)
    results=results.replace('The endpoint mattered (Table 3).',figure('Fig3_')+'\n\nThe endpoint mattered (Table 3).')
    results=results.replace('Requiring at least three eligible events',t3+'\n\nRequiring at least three eligible events')
    results=results.replace('## Delay, pending information and quota fallback',figure('Fig4_')+'\n\n## Delay, pending information and quota fallback')
    results=results.replace('The isolated candidate diagnostic further limited interpretation',figure('Fig5_')+'\n\nThe isolated candidate diagnostic further limited interpretation')
    results += '\n\n'+figure('Fig6_')
    title='Feedback timing and residual updating shape the value of adaptive river nutrient sampling'
    abstract='''Sparse river nutrient observations can improve provisional transport estimates only if their results arrive in time and are used appropriately. We evaluated a hypothetical one-year reduction in concentration monitoring at stations with local high-frequency history and continuing discharge observations. A chronological sensor-record replay distinguished collection, result arrival and immutable concentration estimates. Quality-screened USGS records from 21 stations during 2019–2025 supported temporal and additional-station assessments; primary event endpoints used nine stations with 46 episodes and eight stations with 64 episodes, respectively. Revised complete systems coupled periodic, flow-triggered, block-deadline and load-value sampling to a common latest-residual correction. At 96 annual attempts and a 24 h return delay, temporal mean event absolute relative error was 16.87% for load-value sampling, 17.70% for flow triggering, 19.41% for deadline sampling and 31.74% without new labels. The value–flow improvement was 0.83 percentage points, with a station-resampling 95% interval of −0.86 to 2.42. Additional-station errors were 14.55% and 14.64%, respectively. Fixed-calendar comparisons showed that updating family, memory and residual age could reverse rankings. At fixed actual return times, delay-aware scoring and pending-information correction did not establish stable improvements; the pending queue was inactive in the main scenario. Process cases showed that earlier feedback could coexist with larger error. All revised comparisons use previously inspected records and retain their post-result identity. The assessment supports prioritizing credible returned-sample updating before acquisition complexity, within the sensor reference and observed transport support.'''
    assert 150<=len(abstract.split())<=250,len(abstract.split())
    declarations='''# Declarations

## Data and code availability

Source observations and metadata are publicly accessible through USGS Water Data for the Nation (U.S. Geological Survey, 2026), using station identifiers in Table S1, parameters 00060 and 99133, calendar years 2019–2025 and UTC timestamps. The archived subset was retrieved on October 5, 2026. Online Resource 3 contains the original reproducibility archive, including the versioned hourly working data, metadata, exact query manifests, frozen configurations, source-verification records and original outcomes. The revision component supplies executable code, complete comparison outputs, diagnostic selections, table/figure sources and independent verification records. It also contains a README with commands for reproducing each completed analysis. Access is through the electronic archive supplied with this manuscript; no permanent public repository identifier is asserted. Subsequent live-service revisions may differ from this snapshot.

## Research ethics and computational assistance

The study uses public environmental monitoring records and involves no recruitment of human participants or animal experiment. The role of language-model assistance in design, code, analysis and substantive drafting is described in Materials and methods. Computational verification is distinguished from responsible authors’ final review. Source observations, numerical outputs and plots were not generated as synthetic environmental evidence.
'''
    old=(P/'manuscript/manuscript.md').read_text(encoding='utf-8')
    original_methods=old.split('# Supplementary methods',1)[1].split('## Supplementary tables',1)[0]
    # Supplemental acquisition equations retained from the documented implementation.
    oldmethods=(P/'docs/METHODS_DRAFT.md').read_text(encoding='utf-8')
    state=oldmethods.split('The adaptable residual model used four covariates:',1)[1].split('## Budgets, comparators',1)[0]
    state='The original and revision acquisition states use four covariates:'+state
    state=state.replace('and a common reconstruction across samplers','and the declared acquisition state').replace('V_t=', 'S_t=')
    online1='''# Online Resource 1: Supplementary methods and monitoring diagnostics

## S1. Acquisition surrogate and original state

The following equations specify the unchanged acquisition surrogate and the original pooled-output experiment. The revision core output is the distinct latest-residual correction in the main Methods. In revision mechanism tests, the assumed scoring delay replaces d in the projected covariance, effective noise and load functional; the real return clock is unchanged. The innovation used by a revised complete system is its actual issued prediction saved at collection. Gaussian-design identities concern this surrogate, not a proven error reduction of the latest-residual output.

'''+state+'''

## S2. Reference units and support

The independent raw-record check uses 1 ft³/s = 0.3048³ m³/s and kg N = Q(ft³/s) × 0.3048³ × 900 s × c(mg N/L) × 1000 L/m³ × 10⁻⁶ kg/mg. At station 02035000 on January 1, 2025, 00:00 UTC, Q = 7350 ft³/s and c = 0.34 mg N/L yield 208.1288224512 m³/s, 187315.94020608 m³ and 63.6874196700672 kg N for one quarter hour. The next two quarters have the same recorded values; the last has Q = 7320 ft³/s. Their sum is 748499.205966336 m³ and 254.489730028554 kg N, matching the analysis record. This verifies absolute units independently of cancellation in percentage errors.

Observed-water coverage uses every finite nonnegative reading on the exact quarter-hour grid, weighted by 900 s, including estimated/provisional Q and independently of concentration availability. A secondary denominator retains only qualified Q. Neither estimates runoff during absent Q readings. Complete reference hours require the four qualified joint Q–concentration pairs; no concentration interpolation or annual scaling is applied. Instrument methods, inclusion/exclusion reasons and complete station-year support are retained in the electronic data tables.

## S3. Forward residuals and process timing

For each station-year the seed-41 historical calibration forest was reconstructed using earlier years and predicted all hours of the latest eligible historical calibration year. Its original up-to-4000-observation error audit was reproduced in all 43 included contexts. Historical lag correlations require exactly lagged qualified pairs and every intervening hour to be qualified; endpoint-only pairs are reported separately. In-sample historical predictions do not enter these persistence diagnostics. The same historical discharge scaling as the original experiment is retained, so this is forward concentration withholding rather than fully nested scaling. Target-minus-history residual changes entangle environmental variation, model refitting and support selection.

Onset-based elapsed-transport fractions use eligible events and complete reference hours. Event medians give each event equal weight; load-weighted fractions divide summed early mass by summed event mass. Actual-policy first-arrival fractions instead locate the first successful return in the event interval, including samples collected before onset. If none returns during the event, the fraction is defined as one and a separate no-arrival flag is retained; earlier information may still influence the estimate. At temporal budget 96, the equal-station mean fraction of reference mass before first usable arrival was 48.13% for value and 46.97% for flow; no-arrival fractions were 22.80% and 18.27%. Seeds are averaged within event, events within station, then stations equally. These figures do not represent unavoidable estimation error.

The three process cases use all 46 eligible events at budget 96, seed 41. Selection minimizes, maximizes and approaches the median of |RE_value| − |RE_flow|, with ties broken by station/year/event and distinct events required. The selected extremes belong to the same station and remain unchanged. Four policy-specific loads per case were independently checked against completed replay event records. Separate marker tracks distinguish collection, usable arrival and block expiry.

## S4. Candidate utility and factor comparisons

The monthly candidate diagnostic starts from the development budget-96 periodic calendar and seed 41. It nominates the 15th at 12:00 UTC without reading future concentration, reference quality or error. All 168 nominated times remain in the outputs, with no replacement. Eligibility after nomination requires feasible spacing, no duplicate purchase, a successful virtual sample, at least 95% common reference support in the 72 h after the 24 h arrival, and positive reference mass. Future labels serve only these declared evaluation screens and error scoring. The original future calendar and saved sample innovation weights remain fixed; an added sample changes the latest correction until the next scheduled successful arrival. Thus the result diagnoses score alignment conditional on one additional observation rather than evaluating a new equal-budget closed-loop policy. Rank associations are descriptive without inferential p values, and complete beneficial and harmful observations are supplied.

The reconstruction factorial holds each simple calendar fixed and includes every combination of three nominal half-lives, two age origins and two update families on development records. Equal numerical forgetting scales do not imply equal effective responses because the pooled model discounts information while retaining prior precision and the latest correction discounts amplitude. No evaluation-year parameter winner replaces the declared main output. Station-paired intervals describe the finite monitored population and are pointwise across contrasts.

## S5. Computational verification

Sixteen replay self-checks and five candidate self-checks passed. Independent calculations verified 1281 paid calendars, budget and spacing constraints, actual arrival times, common event support, 140 aggregate metric rows and 48 principal paired comparisons, with differences limited to floating-point rounding. Context verification separately checked 344 historical lag summaries, 1656 actual-arrival records, all twelve case-policy loads and the raw-unit example. The original implementation and its frozen inputs/results were not overwritten. Runtime versions and implementation hashes are provided in the archive rather than embedded in the scientific narrative.
'''
    pair=pd.read_csv(R/'results/summary_main_v1/paired_effects.csv');pair=pair[(pair.minimum_events==1)&(pair.measure=='event_mean_absolute_relative_error')]
    rows=[]
    for _,v in pair.iterrows():
        rows.append([v.stage,int(v.budget),labels[v.baseline],f'{100*v.mean_difference:.2f}',f'{int(v.candidate_lower)}/{int(v.stations)}',f'{100*v.station_ci_low:.2f}, {100*v.station_ci_high:.2f}',f'{100*v.huc4_ci_low:.2f}, {100*v.huc4_ci_high:.2f}'])
    online2='# Online Resource 2: Complete revised outcomes\n\n**Table S2** Paired baseline error minus value-system error (percentage points)\n\n'+tab(['Records','Budget','Baseline','Difference','Sites improved','Station 95% interval','HUC4 95% interval'],rows)+'\n\nPositive EARE differences favour the value system. All intervals are pointwise; HUC4 resampling is a geographical sensitivity rather than proof of independent groups. Machine-readable outputs additionally retain every site, budget, seed, whole-window outcome, signed/absolute mass error, 10%/20% accuracy scenario, three-event sensitivity and HUC4 deletion. No selected subset substitutes for the primary population.\n\n'
    metadata=json.loads((P/'datasets/extended_station_metadata_v1.json').read_text(encoding='utf-8'))
    # Only the 21 stations with working records enter Table S1.
    working=set(pd.read_csv(R/'results/context_site_year.csv',dtype={'site':str}).site)
    # Histories include additional working stations not target eligible; use the unchanged hourly inventory.
    inventory=pd.read_parquet(P/'datasets/extended_hourly_2019_2025_v1.parquet',columns=['site'])
    working=set(inventory.site.astype(str).unique())
    rows=[[x['site'],x['name'].title(),x['state'],x['huc4_group']] for x in metadata if x['site'] in working]
    online1+='\n\n**Table S1** Stations with qualified working records\n\n'+tab(['USGS station','Station name','State','HUC4'],rows)+'\n\nThe full metadata and instrument-provenance inventory, as well as each station’s data and event eligibility by year, are supplied electronically. Presence in the working inventory does not imply inclusion in every assessment.'
    for prefix in ['FigS1_','FigS2_','FigS3_','FigS4_','FigS5_']:
        paths=list((F/'supplement').glob(prefix+'*.caption.txt'))
        if paths:online1+='\n\n'+figure(prefix,'supplement')
    origtable=old.split('## Supplementary tables',1)[1]
    origtable=origtable.replace('The common main configuration','The original frozen pooled-output configuration').replace('remain as described in the main text','remain as described in the original methods above')
    # Preserve original table values and identities; rename their table references locally.
    for n in range(1,5):origtable=origtable.replace(f'Table S{n}.',f'Table F{n}.')
    online3='''# Online Resource 3: Original frozen experiment and analysis lineage

The original configuration and comparisons remain unchanged. They used pooled RFF residual output, seven calendar policies and online/year-end reconstruction modes. C2 was selected using the development grid before the original assessment. The year-end modes permit later responses to revise earlier estimates and do not represent the provisional task. Subsequent fixed-calendar latest-residual/hold-concentration results were already post-result diagnostics. All revised main systems, factors and mechanism comparisons in this article are additional post-result analyses of previously inspected records. Their manifests keep this identity separate from the original freeze. The original attempt/calendars/results and every reconstruction mode remain in the archive.

QR and D-opt are historical calendar adaptations rather than complete replications of published sparse-sensing systems. The rank is capped at eight while the smallest budget is 24, so QR pivots after rank can reflect numerical ordering. These calendars also allow unrestricted seasonal allocation, unlike block-quota policies. They are retained for transparency, without a superiority claim against the published methods.

Innovation-scale adaptation in the original rho=0 comparison affects both subsequent query weighting and reconstruction weighting. It did not isolate a query-only mechanism. The original 6/72 h sensitivity changes actual information availability and subsequent calendars, unlike the revised fixed-real-delay score ablation. Tables F1–F4 retain these distinctions; none is a new independent assessment of the revised system.

'''+original_methods+'\n\n## Frozen and earlier post-result tables\n\n'+origtable
    # APA author order and initials from verified metadata, without newly invented fields.
    used=['Rode2016','Bieroza2023','Reynolds2016','Lee2016','Lee2019','Moatar2007','Bieroza2018','Runkel2004','Hirsch2010','Zhang2019','Wong2016','Wilson2026','Manohar2018','BinMamoon2025','Chaloner1995','USGS2026','Wagner2006','Pellerin2013','Roberts2017','Breiman2001','Rahimi2007']
    library=json.loads((P/'docs/REFERENCE_LIBRARY.json').read_text(encoding='utf-8'))['references'];refs=[]
    for x in library:
        if x['id'] not in used:continue
        if x.get('recommended_citation'):line=x['recommended_citation']
        else:
            authors=[apa_author(y) for y in x['authors']]
            au=', '.join(authors[:-1])+', & '+authors[-1] if len(authors)>1 else authors[0]
            journal=x.get('journal') or x.get('publisher') or ''
            if x.get('report_number'):journal='U.S. Geological Survey '+x['report_number']
            vol=x.get('volume') or '';issue=f"({x['issue']})" if x.get('issue') else ''
            loc=x.get('pages') or ('Article '+str(x['article_number']) if x.get('article_number') else '')
            line=f"{au} ({x['year']}). {x['title']}. *{journal}*"+ (f", *{vol}*{issue}" if vol else '')+(f", {loc}" if loc else '')+'. '+(x.get('doi_url') or x.get('primary_url') or '')
        refs.append((apa_author(x['authors'][0]),line))
    assert len(refs)==len(used)
    references='# References\n\n'+'\n\n'.join(line for _,line in sorted(refs))
    text='\n\n'.join(['# '+title,'## Abstract',abstract,'**Keywords:** optical nitrate; provisional transport; information availability; high-flow episodes; residual persistence; reference support',intro,methods,results,discussion,declarations,references,online1,online2,online3])
    (M/'manuscript.md').write_text(text+'\n',encoding='utf-8')
    tables=[]
    for match in re.finditer(r'(?m)^\|[^\n]*\n\|[-:| ]+\n(?:\|[^\n]*\n)+',text+'\n'):
        vals=[[v.strip() for v in l.strip().strip('|').split('|')] for l in match.group().strip().splitlines()]
        tables.append(vals[:1]+vals[2:])
    (M/'table_source.json').write_text(json.dumps(tables,indent=2),encoding='utf-8')
    (R/'docs/ASSEMBLY_CHECK.json').write_text(json.dumps({'abstract_words':len(abstract.split()),'total_words':len(text.split()),'main_words_before_references':len(text.split('# References')[0].split()),'references':len(refs),'tables':len(tables),'source':'completed result CSVs and verified reference metadata'},indent=2))
    print((R/'docs/ASSEMBLY_CHECK.json').read_text())
if __name__=='__main__':main()
