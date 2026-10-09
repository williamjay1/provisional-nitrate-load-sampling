"""Select the common development configuration and freeze before holdout replay."""
from pathlib import Path
from datetime import datetime,timezone
import json,zipfile
import pandas as pd
from run_value_experiment import CORE_FILES,DEFAULT_POLICIES,CONFIGS
from paper_context import ROOT,frame_digest

out=ROOT/'results/frozen_paper_v1';out.mkdir(parents=True,exist_ok=False)
rows=[];scores={};manifests={}
common=['uniform','stratified_random','flow_trigger','q_uncertainty','value']
for config in CONFIGS:
    folder=ROOT/'results/paper_runs'/f'develop_{config}_v2'
    manifests[config]=json.loads((folder/'run_manifest.json').read_text())
    d=pd.read_csv(folder/'metrics.csv',dtype={'site':str})
    d=d.loc[(d.budget>0)&(d.events_eligible>0)]
    table=d.groupby(['policy','budget','site']).event_mean_absolute_relative_error.mean().groupby(['policy','budget']).mean()
    scores[config]=float(table.loc[common].mean())
    rows.extend({'config':config,'policy':p,'budget':b,'mean_event_absolute_relative_error':v} for (p,b),v in table.items())
selected=min(scores,key=scores.get)
pd.DataFrame(rows).to_csv(out/'development_configuration_comparison.csv',index=False)
manifest={'created_at_utc':datetime.now(timezone.utc).isoformat(),'selected_config':selected,'selected_parameters':CONFIGS[selected],
          'selection_scores':scores,'selection_rule':'equal five quota policies, budgets, stations; years averaged within station; primary event absolute relative error; seed 41',
          'development_run_manifests':manifests,
          'data_sha256':frame_digest(ROOT/'datasets/extended_hourly_2019_2025_v1.parquet'),
          'code_sha256':{f:frame_digest(ROOT/'scripts'/f) for f in CORE_FILES},
          'analysis_plan_sha256':frame_digest(ROOT/'docs/FULL_PAPER_PLAN.md'),
          'allowed_seeds':[41,73,109],'allowed_budgets':[24,48,96],'allowed_policies':DEFAULT_POLICIES,
          'allowed_reconstruction_modes':['online','retrospective_residual','retrospective_linear'],
          'allowed_delays':[6,24,72],'allowed_adaptation_rates':[0.,.1],
          'experiments':{'primary':'temporal 2025; 24 h; rho .1; 7 policies; 3 reconstructions',
                         'external':'new sites 2023/2024; 24 h; rho .1; 7 policies; 3 reconstructions',
                         'delay':'temporal 2025; 6 and 72 h; uniform/flow/QSD/value; online',
                         'feedback_ablation':'temporal 2025; 24 h; rho 0; uniform/flow/QSD/value; online'},
          'status':'frozen before any external or 2025 policy outcome; internal dated plan, not public preregistration'}
(out/'freeze_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
with zipfile.ZipFile(out/'implementation_snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
    for f in CORE_FILES:z.write(ROOT/'scripts'/f,'scripts/'+f)
    for f in (ROOT/'tests').glob('test*.py'):z.write(f,'tests/'+f.name)
    z.write(ROOT/'docs/FULL_PAPER_PLAN.md','FULL_PAPER_PLAN.md')
    z.write(out/'freeze_manifest.json','freeze_manifest.json')
print(json.dumps({'selected':selected,'scores':scores,'manifest':str(out/'freeze_manifest.json')},indent=2))
