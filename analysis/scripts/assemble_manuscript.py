"""Assemble the scientific manuscript and source-derived tables; no invented data."""
from pathlib import Path
import re,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'manuscript';OUT.mkdir(exist_ok=True)
labels={'uniform':'Periodic','stratified_random':'Stratified random','flow_trigger':'Flow trigger',
        'q_uncertainty':'Discharge × posterior SD','value':'Delayed load value',
        'historical_qr':'Historical QR','historical_dopt':'Historical D-opt'}

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+
                     ['| '+' | '.join(str(x) for x in r)+' |' for r in rows])

def section(name):
    return (ROOT/'docs'/name).read_text(encoding='utf-8').strip()

def getcell(a,stage,policy,budget,mode='online'):
    r=a[(a.stage==stage)&(a.policy==policy)&(a.budget==budget)&(a['mode']==mode)&(a.minimum_events==1)]
    if len(r)!=1:raise ValueError((stage,policy,budget,mode,len(r)))
    return float(r.iloc[0].event_mean_absolute_relative_error)*100

def main():
    a=pd.read_csv(ROOT/'results/paper_analysis_main/aggregate_metrics.csv')
    b=pd.read_csv(ROOT/'results/paper_analysis_reconstructors/aggregate_metrics.csv')
    title='Sampling value depends on reconstruction in river nitrate monitoring under delayed feedback'
    abstract='''Sampling decisions for river nitrate plus nitrite monitoring must accommodate both limited measurement budgets and delayed analytical responses. We evaluated whether prospective load relevance improves sampling utility when alternative schedules share the same concentration predictor and online residual updater. A chronology-preserving replay used United States Geological Survey records from 21 stations during 2019–2025, with seven sampling policies, three annual budgets and a historical predictor receiving no new labels. Policy settings were frozen before a 2025 temporal test and an additional-station 2023–2024 evaluation. The temporal event endpoint comprised 46 qualified high-flow episodes at nine stations. At 96 attempts and a 24 h response delay, the load-value policy reduced mean event absolute relative error from 29.45% with periodic sampling to 26.56%, improving seven stations; the paired station-resampling 95% interval was 0.26–6.23 percentage points. Its smaller advantage over flow triggering had an interval crossing zero. The spatial holdout did not show a general advantage over periodic sampling. Increasing response delay from 6 to 72 h raised load-value error from 24.94% to 28.27% at the largest budget. Reconstruction choices produced larger changes: a post-result diagnostic using identical realized calendars and a simple online residual correction reduced the temporal load-value error to 17.03%. Retrospective reconstruction also changed sampler rankings. These results identify conditional benefits of adaptive sampling while showing that acquisition, response timing and reconstruction must be evaluated together. The sensor replay supports observed-window load comparisons, rather than claims of laboratory deployment or fully observed annual loads.'''
    data=section('DATA_SECTION_DRAFT.md').replace('# Data and reference construction','## Data and reference construction',1)
    data=data.replace('| Virginia |','| VA |').replace('| Illinois |','| IL |').replace('| Indiana |','| IN |').replace('| Iowa |','| IA |').replace('| Missouri |','| MO |').replace('| Kansas |','| KS |')
    methods=section('METHODS_DRAFT.md')
    methods=methods.replace('# Methods','# Materials and methods',1)
    methods=methods.replace('## Historical predictor and residual representation',data+'\n\n## Historical predictor and residual representation',1)
    methods=methods.replace('Hours, events and seeds were not treated as independent experimental units.',
        'Hours, events and seeds were not treated as independent experimental units. Intervals are pointwise empirical summaries, not simultaneous intervals adjusted across all comparisons.')
    methods+='''

## Additional fixed-calendar reconstruction diagnostic

After inspecting the main temporal and spatial outcomes, we evaluated dependence on the shared online reconstructor without changing the realized sampling calendars. One reconstruction retained the last returned residual relative to the historical forest and decayed it exponentially from its arrival with a 168 h time constant, using the rule from the earlier pilot. The other held the last returned concentration constant until another response arrived. Both used the historical predictor before the first response and excluded failed or not-yet-returned labels. The 168 h constant was not selected against the holdouts. These analyses included every sampler and budget in both validation cohorts. They are post-result conditional diagnostics of the collected observations, not new closed-loop trials with these alternative reconstructors controlling acquisition.
'''
    rows=[]
    for policy in labels:
        rows.append([labels[policy]]+[f'{getcell(a,stage,policy,budget):.2f}' for stage in ['temporal','external'] for budget in [24,48,96]])
    rows.append(['Historical forest, no new labels']+[f'{getcell(a,stage,"no_new_labels",0):.2f}' for stage in ['temporal','external'] for _ in [24,48,96]])
    t2='''**Table 2. Mean online event absolute relative error (%).** Columns show nominal annual attempt budgets. The temporal cohort contains nine event-evaluable stations and 46 episodes; the spatial cohort contains eight stations, 14 event-evaluable station-years and 64 episodes. Events and seeds are averaged within station-year, years within station, and then stations equally. The zero-new-label forest is repeated for reference and uses no target-year sampling budget. All other rows share the frozen online residual updater.

'''+table(['Sampling policy','Temporal 24','Temporal 48','Temporal 96','Spatial 24','Spatial 48','Spatial 96'],rows)
    rows=[]
    for mode,name in [('online','Frozen residual updater'),('online_last_residual_fixed_calendar','Last residual, 168 h'),('online_sample_hold_fixed_calendar','Last concentration')]:
        src=a if mode=='online' else b
        for policy in ['uniform','flow_trigger','value']:
            rows.append([name,labels[policy],f'{getcell(src,"temporal",policy,96,mode):.2f}',f'{getcell(src,"external",policy,96,mode):.2f}'])
    t3='''**Table 3. Online reconstruction of the same realized calendars at 96 annual attempts.** Values are mean event absolute relative errors (%), using the same cohorts and weighting as Table 2. The two alternative reconstructors were evaluated after the main results and did not change sampling decisions. “168 h” is an exponential time constant from response arrival. Results for every budget and sampler are retained in the supplementary tables and machine-readable results.

'''+table(['Online reconstruction','Sampling calendar','Temporal error','Spatial error'],rows)
    results=section('RESULTS_DRAFT.md')
    results=results.replace('## Online performance in the future year',t2+'\n\n## Online performance in the future year',1)
    results=results.replace('## Sampling behaviour and computational cost',t3+'\n\n## Sampling behaviour and computational cost',1)
    conclusions='''# Conclusions

The value of an additional nitrate plus nitrite measurement depended on how and when the monitoring system used it. A compact load-value sampling rule modestly improved average online event estimates in the 2025 cohort, particularly relative to periodic sampling at 96 annual attempts, but did not establish a general advantage across stations, budgets and reconstruction tasks. Longer response delays increased error, while innovation-scale adaptation did not improve the load-value policy's mean event load error in the prespecified temporal ablation. A post-result fixed-calendar diagnostic showed that replacing the online reconstructor could improve accuracy more than replacing the sampling rule, even with exactly the same collected observations. Monitoring designs should therefore be compared as complete acquisition-and-reconstruction systems under their actual response deadlines. These findings support a reproducible route for that comparison; prospective validation is needed before selecting a field deployment.

# Data and code availability

Source observations and metadata are publicly available through the USGS Water Data services (U.S. Geological Survey, 2026), with parameter codes, station identifiers, retrieval dates and quality rules documented in the accompanying archive. The versioned hourly analysis data, station metadata, analysis code, frozen configurations, machine-readable outcomes and verification records are supplied in the reproducibility archive accompanying this manuscript. The archived subset was retrieved on 5 October 2026. Subsequent changes in the public record may differ from this snapshot.

# AI assistance

OpenAI Codex and associated large language model agents assisted study design, literature discovery, code development and debugging, computational analysis, figure scripting and manuscript drafting. Numerical findings were generated by the documented computational pipeline. Data qualification, information timing, code invariants and reported calculations were checked against archived records and separate verification implementations. The supplied evidence distinguishes source verification and computational checks from the responsible authors' final scientific review.
'''
    captions='''# Figures

![Figure 1](figures/figure1_reconstruction_and_budget.png){width=6.5in}

**Figure 1. Sampling budgets and reconstruction objectives.** The vertical axis gives equal-station mean absolute relative error of eligible event observed-window loads in the 2025 temporal test (nine stations, 46 events). Points average three seed/phase repetitions. Panels compare the common online residual updater, year-end interpolation of sampled residuals and year-end interpolation of sampled concentrations. Each policy retains the same realized calendar across panels; the retrospective panels use later responses to revise earlier estimates and therefore do not represent online performance. Historical QR and D-opt are calendar adaptations with greater freedom in seasonal allocation. Lines join tested budgets and do not imply a continuous response function. Paired uncertainty is reported in the text and supplementary tables.

![Figure 2](figures/figure2_station_comparisons.png){width=6.5in}

**Figure 2. Paired station-level online comparisons.** Each point is comparator error minus sampling-value error, in percentage points, after averaging eligible events and the three seed/phase repetitions within a station. Positive values favour sampling value. The nine stations contribute equally to the temporal endpoint. Separate panels show annual budgets; point colours distinguish periodic and flow-trigger comparators. Dispersion represents station heterogeneity, not independent repetitions of the same river system.

![Figure 3](figures/figure3_label_delay.png){width=6.5in}

**Figure 3. Sensitivity to the concentration-response delay.** Mean event error in the same temporal cohort is shown for 6, 24 and 72 h delays, three budgets and the four prespecified online policies. The acquisition specification and historical model fitting rules were frozen. Each delay defines a complete chronological replay and can affect both which responses have arrived and subsequent sampling decisions. These curves do not isolate a causal contribution of the delay term in the load-value score.
'''
    library=json.loads((ROOT/'docs/REFERENCE_LIBRARY.json').read_text(encoding='utf-8'))['references']
    # Only include sources used by the main manuscript or supplementary methods.
    used=['Rode2016','Bieroza2023','Reynolds2016','Lee2019','Moatar2007','Bieroza2018',
          'Runkel2004','Hirsch2010','Zhang2019','Wong2016','Blaen2016','Wilson2026','Henkel2026',
          'Manohar2018','BinMamoon2025','Joulani2013','Chaloner1995',
          'Krause2008','Rahimi2007','USGS2026','Wagner2006','Pellerin2013','Roberts2017','Breiman2001',
          'Lee2016']
    refs=[]
    for ref in sorted(library,key=lambda r:r['id'].lower()):
        if ref['id'] not in used:continue
        if ref.get('recommended_citation'):
            refs.append(ref['recommended_citation'])
            continue
        authors=', '.join(ref['authors']);journal=ref.get('journal') or ref.get('publisher') or ''
        if ref.get('report_number'):
            journal='U.S. Geological Survey '+ref['report_number']
        loc=', '.join(dict.fromkeys(str(ref[k]) for k in ['volume','pages','article_number'] if ref.get(k)))
        url=ref.get('doi_url') or ref.get('primary_url') or ''
        note=' [Discussion preprint; not a peer-reviewed final article.]' if 'Preprint' in ref['id'] else ''
        refs.append(f"{authors} ({ref['year']}). {ref['title']}. {journal}{', '+loc if loc else ''}.{note} {url}")
    if len(refs)!=len(used):raise ValueError('Reference keys missing '+str(set(used)-{r['id'] for r in library}))
    # EMA places unpublished work in the text: retain complete preprint provenance
    # beside its first discussion, without representing it as an accepted article.
    intro=section('INTRODUCTION_DRAFT.md')
    preprint=next(r for r in library if r['id']=='BinMamoon2026Preprint')
    marker='(Bin Mamoon et al., 2026, preprint)'
    if intro.count(marker)!=1:raise ValueError('Expected one preprint citation in introduction')
    paragraphs=intro.split('\n\n')
    for i,paragraph in enumerate(paragraphs):
        if marker in paragraph:
            paragraphs[i]=paragraph.replace(marker,'(see the preprint source note below)')
            note=(f"*Preprint source note.* {', '.join(preprint['authors'])} ({preprint['year']}). "
                  f"{preprint['title']}. {preprint['journal']} discussion preprint; "
                  f"not peer reviewed and not an accepted journal article. {preprint['doi_url']}")
            paragraphs.insert(i+1,note)
            break
    intro='\n\n'.join(paragraphs)
    dev=pd.read_csv(ROOT/'results/frozen_paper_v1/development_configuration_comparison.csv')
    s1=[]
    for (config,policy),f in dev.groupby(['config','policy']):
        s1.append([config,labels[policy]]+[f'{float(f.loc[f.budget==B,"mean_event_absolute_relative_error"].iloc[0])*100:.2f}' for B in [24,48,96]])
    paired=pd.read_csv(ROOT/'results/paper_analysis_main/paired_effects.csv')
    f=paired[(paired.stage=='temporal')&(paired['mode']=='online')&(paired.minimum_events==1)&(paired.measure=='event_mean_absolute_relative_error')&(paired.baseline.isin(['uniform','flow_trigger']))]
    s2=[]
    for _,r in f.iterrows():
        s2.append([int(r.budget),labels[r.baseline],f'{100*r.mean_improvement:.2f}',f'{int(r.wins)}/{int(r.stations)}',
                   f'{100*r.station_ci_low:.2f} to {100*r.station_ci_high:.2f}',f'{100*r.huc4_ci_low:.2f} to {100*r.huc4_ci_high:.2f}'])
    s3=[]
    for stage in ['temporal','external']:
        for mode,name in [('online_last_residual_fixed_calendar','Last residual'),('online_sample_hold_fixed_calendar','Last concentration')]:
            for policy in labels:
                s3.append([stage,name,labels[policy]]+[f'{getcell(b,stage,policy,B,mode):.2f}' for B in [24,48,96]])
    sens=pd.read_csv(ROOT/'results/paper_analysis_sensitivity/aggregate_metrics.csv');sens=sens[(sens.minimum_events==1)&(sens.budget>0)]
    s4=[]
    for (delay,rho,policy),f in sens.groupby(['delay_hours','noise_adaptation_rate','policy']):
        s4.append([int(delay),rho,labels[policy]]+[f'{float(f.loc[f.budget==B,"event_mean_absolute_relative_error"].iloc[0])*100:.2f}' for B in [24,48,96]])
    supplementary_tables='\n\n'.join([
        '## Supplementary tables',
        '**Table S1. Complete development configuration grid.** Mean event error (%), seed 41; years are averaged within station and stations equally. C0=(72 h window, 720 h half-life, 0.85 quantile), C1=(168, 720, 0.85), C2=(72, 2160, 0.85), C3=(72, 720, 0.65). The selection score averages the five quota policies and all three budgets; historical QR and D-opt are reported but not in that selection average.',
        table(['Config','Policy','24 attempts','48 attempts','96 attempts'],s1),
        '**Table S2. Temporal online paired improvements.** Positive differences in percentage points favour sampling value. Intervals use 10,000 station or HUC4 resamples, respectively. These are pointwise empirical summaries, not simultaneous intervals. There are nine stations and five HUC4 groups.',
        table(['Budget','Comparator','Mean improvement','Station wins','Station 95% interval','HUC4 95% interval'],s2),
        '**Table S3. Complete post-result online reconstruction diagnostic.** Event error (%) for unchanged realized calendars; no replacement reconstructor was used to regenerate acquisition decisions. Cohorts and weighting match the main event analyses. Last residual uses a 168 h exponential time constant from response arrival.',
        table(['Cohort','Reconstruction','Calendar','24 attempts','48 attempts','96 attempts'],s3),
        '**Table S4. Prespecified temporal online sensitivities.** Mean event error (%). The common main configuration, cohort, weighting and all other settings remain as described in the main text; the 24 h rows here disable innovation-scale adaptation, while retaining residual-mean updates.',
        table(['Delay (h)','Adaptation rate','Policy','24 attempts','48 attempts','96 attempts'],s4)])
    text='\n\n'.join(['# '+title,'## Abstract',abstract,'**Keywords:** adaptive sampling; nitrate plus nitrite; load estimation; delayed feedback; monitoring design; reconstruction',
        intro,methods,results,section('DISCUSSION_DRAFT.md'),conclusions,
        '# References','\n\n'.join(refs),captions,'# Supplementary material',section('SUPPLEMENT_METHODS_DRAFT.md'),supplementary_tables])
    (OUT/'manuscript.md').write_text(text+'\n',encoding='utf-8')
    print(json.dumps({'path':str(OUT/'manuscript.md'),'words_including_references_supplement':len(text.split()),'references':len(refs)}))
if __name__=='__main__':main()
