"""Scientific figures from completed summaries, without hand-entered results."""
from pathlib import Path
import os,json
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'cache/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

OUT=ROOT/'manuscript/figures';OUT.mkdir(parents=True,exist_ok=True)
MAIN=ROOT/'results/paper_analysis_main'
labels={'uniform':'Periodic','stratified_random':'Stratified random','flow_trigger':'Flow trigger',
        'q_uncertainty':'Q × posterior SD','value':'Delayed load value','historical_qr':'Historical QR',
        'historical_dopt':'Historical D-opt'}
colors=dict(zip(labels,['#333333','#8A8A8A','#D55E00','#009E73','#0072B2','#CC79A7','#A6761D']))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,
                     'svg.fonttype':'none','pdf.fonttype':42,'axes.labelsize':9,'legend.fontsize':8})

def save(fig,name):
    fig.savefig(OUT/(name+'.svg'),bbox_inches='tight')
    fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight')
    fig.savefig(OUT/(name+'.png'),dpi=900,bbox_inches='tight')
    fig.savefig(OUT/(name+'_preview.png'),dpi=140,bbox_inches='tight')
    plt.close(fig)

def main():
    a=pd.read_csv(MAIN/'aggregate_metrics.csv')
    t=a[(a.stage=='temporal')&(a.minimum_events==1)&(a.budget>0)]
    modes=['online','retrospective_residual','retrospective_linear']
    names=['Online','Retrospective residual','Retrospective concentration']
    fig,axes=plt.subplots(1,3,figsize=(7.2,3.6),sharey=True)
    for i,(mode,name,ax) in enumerate(zip(modes,names,axes)):
        for policy in labels:
            f=t[(t['mode']==mode)&(t.policy==policy)].sort_values('budget')
            ax.plot(f.budget,100*f.event_mean_absolute_relative_error,'o-',label=labels[policy],color=colors[policy],lw=1.5,ms=4)
        ax.set_title(f'{chr(97+i)}  {name}',fontsize=8);ax.set_xticks([24,48,96]);ax.set_xlabel('Attempts per year')
        ax.grid(axis='y',alpha=.18)
    axes[0].set_ylabel('Event load error (%)')
    fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,-.23),ncol=3,frameon=False)
    fig.tight_layout();save(fig,'figure1_reconstruction_and_budget')
    s=pd.read_csv(MAIN/'site_year_metrics.csv',dtype={'site':str})
    s=s[(s.stage=='temporal')&(s['mode']=='online')&(s.events_eligible>=1)]
    fig,axes=plt.subplots(1,3,figsize=(7.2,4.8),sharey=True,sharex=True)
    sites=sorted(s.site.unique()); y=np.arange(len(sites))
    for ax,budget in zip(axes,[24,48,96]):
        w=s[s.budget==budget].pivot(index='site',columns='policy',values='event_mean_absolute_relative_error').reindex(sites)
        ax.axvline(0,color='.45',lw=.8)
        for delta,base,color in [(-.12,'uniform',colors['uniform']),(.12,'flow_trigger',colors['flow_trigger'])]:
            ax.scatter(100*(w[base]-w['value']),y+delta,s=24,label=labels[base],color=color)
        ax.set_title(f'{budget} attempts');ax.set_xlabel('Value improvement (pp)');ax.grid(axis='x',alpha=.15)
    axes[0].set_yticks(y,sites);axes[0].set_ylabel('USGS station');axes[0].invert_yaxis();axes[2].legend(frameon=False,loc='best')
    fig.tight_layout();save(fig,'figure2_station_comparisons')
    sens=ROOT/'results/paper_analysis_sensitivity/aggregate_metrics.csv'
    if sens.exists():
        a2=pd.concat([a,pd.read_csv(sens)],ignore_index=True)
        f=a2[(a2.stage=='temporal')&(a2.minimum_events==1)&(a2['mode']=='online')&(a2.noise_adaptation_rate==.1)]
        fig,axes=plt.subplots(1,3,figsize=(7.2,3.5),sharey=True)
        for ax,budget in zip(axes,[24,48,96]):
            for policy in ['uniform','flow_trigger','q_uncertainty','value']:
                z=f[(f.budget==budget)&(f.policy==policy)].sort_values('delay_hours')
                ax.plot(z.delay_hours,z.event_mean_absolute_relative_error*100,'o-',label=labels[policy],color=colors[policy],lw=1.5,ms=4)
            ax.set_xticks([6,24,72]);ax.set_xlabel('Label return delay (h)');ax.set_title(f'{budget} attempts');ax.grid(axis='y',alpha=.18)
        axes[0].set_ylabel('Event load error (%)')
        fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,-.08),ncol=2,frameon=False)
        fig.tight_layout();save(fig,'figure3_label_delay')
    print(str(OUT))
if __name__=='__main__':main()
