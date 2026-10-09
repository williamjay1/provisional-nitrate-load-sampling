"""Write the stage report from checked result tables, without altering any run."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / 'results' / 'analysis_v2'
agg = pd.read_csv(A/'aggregate_summary.csv')
pairs = pd.read_csv(A/'paired_summary.csv')
counts = pd.read_csv(A/'site_event_counts.csv', dtype={'site':str})
names = {'uniform':'均匀日历', 'flow_trigger':'流量与涨水触发', 'rf_disagreement':'RF树间分歧',
         'rf_load_disagreement':'流量加权RF分歧', 'historical_design':'历史杠杆分数（配额块）',
         'historical_qr':'历史QR日历适配', 'historical_dopt':'历史D-opt日历适配'}
metric = 'event_mean_absolute_relative_error'

def table(year, mode='online'):
    part=agg[(agg.year==year)&(agg['mode']==mode)&(agg.metric==metric)]
    rows=['|策略|24次/年|48次/年|96次/年|','|---|---:|---:|---:|']
    for policy,name in names.items():
        nums=[float(part.loc[(part.policy==policy)&(part.budget==b),'median'].iloc[0])*100 for b in [24,48,96]]
        rows.append('|'+name+'|'+'|'.join(f'{v:.2f}%' for v in nums)+'|')
    return '\n'.join(rows)

def paired_table():
    part=pairs[(pairs.year==2024)&(pairs['mode']=='online')&(pairs.policy=='rf_load_disagreement')&(pairs.metric==metric)]
    rows=['|预算|比较基线|胜/平/负站点|配对误差差值中位数（百分点）|','|---:|---|---:|---:|']
    for b in [24,48,96]:
        for base in ['uniform','flow_trigger']:
            r=part[(part.budget==b)&(part.baseline==base)].iloc[0]
            rows.append(f'|{b}|{names[base]}|{int(r.wins)}/{int(r.ties)}/{int(r.losses)}|{100*r.median_paired_difference:+.2f}|')
    return '\n'.join(rows)

runs={y:json.loads((ROOT/'results'/name/'run_manifest.json').read_text()) for y,name in [(2023,'validation_2023_v2'),(2024,'test_2024_v2')]}
zero={y:float(agg.loc[(agg.year==y)&(agg.policy=='no_new_labels')&(agg['mode']=='online')&(agg.metric==metric),'median'].iloc[0])*100 for y in runs}
coverage=['|站点|2023有效小时覆盖|2023合格/全部事件|2024有效小时覆盖|2024合格/全部事件|','|---|---:|---:|---:|---:|']
for site,grp in counts.groupby('site'):
    x=grp.set_index('year')
    coverage.append(f"|{site}|{100*x.loc[2023,'hour_coverage']:.1f}%|{int(x.loc[2023,'events_eligible'])}/{int(x.loc[2023,'events_all'])}|{100*x.loc[2024,'hour_coverage']:.1f}%|{int(x.loc[2024,'events_eligible'])}/{int(x.loc[2024,'events_all'])}|")
report=f'''# 固定预算河流NOx采样：首轮实证报告

日期：2026-10-05。阶段：数据审计、可复现回放、2023开发验证及冻结后的2024时间外测试已完成。本文是阶段报告，尚无投稿稿件或实地部署验证。

**判断：CONDITIONAL——值得继续检验采样价值，但当前“流量加权模型分歧”尚未显示稳定超越水文规则的增量。** 2024每年96次采样时，对均匀日历在7个可评价站均较好；24/48次时结果不稳定。对更强的流量触发规则，胜站数为2/7、2/7、4/7，不能主张普遍优势。

## 1. 已完成什么

从USGS获取8站、32站年的真实历史观测，核验99133对应的原位紫外吸收测量方法；目标为硝酸盐加亚硝酸盐，以氮计，不是总氮。观测响应159.805 MB，压缩原始归档7.650 MB；生成280,512小时记录，213,358个完整参考小时（76.06%）。13项数据语义、积分、哈希与只读检查通过。

2021—2022训练，2023开发，2024在2026-10-05 15:01:23 UTC冻结代码与配置后首次执行。全部8站保留；3个年度预算×7个有预算策略×3随机种子×8站×2年，共1008次有预算年度回放，每次分别计算在线、期末残差重建、期末线性插值三种结果，另有零新增标签对照；共3072条指标记录。

同一历史RF模型作为所有策略的浓度先验。采样最短间隔24小时、标签延迟24小时；不可回放的尝试仍消耗预算。新标签更新共同的残差校正器，查询分数本身冻结，因此本轮是情境自适应采样，未实现标签反馈驱动的主动学习。

## 2. 主指标与评价支持

主指标为**高覆盖（至少95%）、边界可判定的高流量事件中，有效观测窗口负荷的绝对相对误差**。先计算每站、每种子的事件误差均值，再平均3种子，再报可评价站的中位数。下表数字越低越好，百分比是相对误差，不是事件漏采率。在线预测只使用当时已到达的已购标签，不能回填过去。

2023有16个、2024有20个合格事件，两年均只有7个站可计算主指标。05465500没有合格事件，仍在覆盖表、有效窗口偏差和全部采样记录中保留。事件和种子不充当独立站点，不计算虚假的小时级显著性。

### 2024冻结测试：在线估计

{table(2024)}

零新增标签历史RF参照：{zero[2024]:.2f}%。它没有额外采样成本，但已经利用本站两年历史密集浓度，不是无数据模型。

下表是流量加权RF分歧与两种基线的**逐站配对**比较；负差值表示AI策略误差更小。跨站中位数的差不等于配对差中位数，不能混用。

{paired_table()}

### 2023开发验证：在线估计

{table(2023)}

零新增标签参照：{zero[2023]:.2f}%。2023与2024的结果变化说明，不能只根据某年、某预算的最佳结果确定算法优势。没有按2024结果更改策略、参数、站点名单或主指标。

## 3. 期末重建与次级结果

期末残差重建和线性插值允许利用期末已返回的购买标签重估过去，不能作为事件发生时的实时精度。完整结果、有效窗口总负荷偏差、每站事件和配对差见[汇总表](results/analysis_v2/aggregate_summary.csv)、[逐站表](results/analysis_v2/site_summary.csv)、[逐站配对表](results/analysis_v2/paired_sites.csv)。未择优切换到表现更好的重建器。

一个值得警惕的例子：2024、24次预算的期末残差重建，AI跨站误差中位数约18.72%，低于均匀采样的26.90%，但逐站仅胜3/7，配对差中位数反而约+1.17个百分点。只报两个总体中位数会掩盖异质性。

![逐站在线误差差值]({(A/'online_site_heterogeneity.png').as_posix()})

图中的负数代表流量加权RF分歧误差更小。精确数值以CSV为准。SVG/PDF与屏幕PNG同时保存；图件尚未按具体期刊版面制作。

## 4. 数据限制及修复

{chr(10).join(coverage)}

没有站年具有完整全年参考，不能将有效窗口负荷称为全年负荷。高流诊断时段完整参考覆盖约80.05%，共同评分掩码不能消除缺测选择偏差。2024主指标由40个Q事件中的20个提供参考，其余也保留记录；此处数量不乘方法、预算或种子。

开发审查发现并修复两项实质问题：高流事件跨Q缺口误合并；训练/标签/浓度MAE未全部统一到非删失reference_ok。全时段396个整点值属于已审批但删失的A|<，全部在07144100；0.1 mg/L表示真实浓度小于0.1，不能作为精确值。修复后独立12项单测、42组平闰年预算日历检查通过；旧v1结果保留但不参与当前结论。

## 5. 能支持与尚不能支持的主张

支持：本轮数据上可以实现严格按时间推进、计入失败尝试及化验延迟的固定预算回放；已得到可核验的逐站结果和明显的预算/年份异质性。

尚不能支持：AI查询分数稳定优于强水文规则；不存在本站历史浓度时仍然有效；跨流域迁移；现场采样或实验室测量精度；实际货币节约或污染减少。流量来自最终审批历史归档，尚未重建实时发布版本。传感器值模拟抓样信息，未模拟真实化验误差。

历史QR/D-opt是清楚标注的前瞻日历适配，使用共享重建器；不是作者原版DSS系统的精确复现。年度自由配置日历与配额块触发的约束集合有所不同。均匀日历目前只有固定相位，后续仍需检验相位敏感性。

近邻研究已涉及历史训练的稀疏采样设计：[2025 GRL论文](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2025GL114935)、[2026 HESS讨论稿](https://egusphere.copernicus.org/preprints/2026/egusphere-2026-3230/)。本项目不能以“历史资料设计日历”主张首创。已读层次及复现缺口见[证据文档](docs/EVIDENCE_AND_POSITIONING.md)。

## 6. 继续方向与资源

下一阶段最有价值的问题是：**一个样本24小时后返回，究竟能减少多少未来负荷估计误差？** 应先用历史前推交叉验证检查该量与现有query score的关系，再设计会利用已返回残差、季节与剩余预算的采样价值模型；增加周期起始相位及新站点/年份验证。当前查询分数只是树间分歧乘流量，尚未直接估计采样后的误差减少量，追加RL/GNN复杂度尚无证据支持。

2024已经使用，不能再充当未见测试集。任何后续开发在2024上的表现均标探索，并另留新的站点年验证。具体设计门槛见[后续实验决策](docs/NEXT_EXPERIMENT_DECISION.md)。期刊类型暂定水文、水质监测或环境建模的方法/应用验证，具体选刊待贡献成立后核实。

最终v2验证回放机器墙钟时间{runs[2023]['elapsed_seconds']:.2f}秒、测试{runs[2024]['elapsed_seconds']:.2f}秒，合计{sum(v['elapsed_seconds'] for v in runs.values()):.2f}秒；进程累计CPU时间{sum(v['cpu_seconds'] for v in runs.values()):.2f}秒。这些数值仅覆盖模型训练与年度回放，不含网络下载、检索、调试、独立审计和汇总。使用CPU，不依赖CUDA或付费模型API。

工作目录与复跑说明见[README](README.md)。原始数据位于F盘只读仓库，训练数据、代码、缓存和结果位于D盘。冻结指纹及实现快照见[freeze manifest](results/frozen_v2/freeze_manifest.json)；审计见[独立代码复核](docs/CODE_REVIEW_V1.md)。

交付前独立结果核验通过：从事件参考/预测负荷重新计算主指标，与汇总表的20项主结果、12项配对胜站统计全部一致；两年代码、配置、数据与冻结快照吻合。详见[独立结果检查](results/INDEPENDENT_RESULT_CHECK.json)。
'''
(ROOT/'PILOT_REPORT.md').write_text(report,encoding='utf-8')
print(ROOT/'PILOT_REPORT.md')
