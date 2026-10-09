# Scientific-content and review-coverage verification

审查日期：2026-10-09。审查范围为本次修订的 Introduction、Methods、Results、Discussion/Conclusions、合稿摘要、主表 1–3 及相关图注/补充定义。只读检查正文和结果，未改动实验、冻结实现、数据或他人文件，未重新调参或运行模型。完整阅读 `REVIEW_SOURCE_20261009.txt`；其 SHA256 与用户原始评审文本一致：`b43714ffa2ce59f1c0e61ed8146983f1c51e8e223d9e92686c6b5caa822ba0ce`。

**阶段结论：PASS / GO（科学内容、关键数字与评审覆盖）。** 当前证据支持一项限定于本地高频历史、随后单年稀疏观测和延迟信息的监测评估研究。没有发现需要重跑实验才能修复的数值或科学解释错误。此结论不是新增独立验证、真实实验室准确度证明或录用保证。视觉版式和完整引文书目由另行审查负责。

## 1. 已关闭的定义问题与收尾事项

1. **小时发布时钟：已关闭。** 初读 Methods 的“在小时起点发布浓度及相应负荷”容易暗示使用尚未到达的 15/30/45 min 流量。当前 Methods 已明确：起点发布并固定浓度，随流量实际观测累积负荷，小时区间经过后才评价该小时质量；浓度轨迹没有回溯修订。它与代码和积分标签一致。
2. **参考水量分母：已关闭。** 当前 Methods、Table 1 图注和 Online Resource 1 明确采用存在于精确 15 min 网格上的有限非负 Q，每点乘 900 s，独立于浓度是否存在；包括 provisional/estimated Q。它不是所有任意采样频率的 native 点直接加总，更不是缺失期间的全部径流。另有只含合格 Q 的分母。Results 中的 native discharge 简称应在此定义下解读。
3. **真实到达与假定 onset 延迟：已关闭。** Results 和补充材料分别报告两种统计；实际到达包括事件前购买而事件内返回的样本。无事件内可用返回时，事件发生量份额定义为 1，另有 no-arrival 指标；不能解释为事件开始时没有历史浓度信息。
4. **创新尺度开关的主文回应：已关闭。** Results 的 Delay, pending information and quota fallback 节现已明确原始时间 B96 value 误差为26.53%（关闭）与26.56%（开启），且原开关同时影响查询与重构权重，不是 query-only 干预。已对回原始 main/sensitivity 两份 aggregate 全精度：0.2652670129762462与0.2655772513979281；没有将此当新 latest 系统的适应消融。
5. **预算术语统一：已关闭。** 主 Methods/Table 2 正确写 attempted samples；增量检查合稿 Fig. 3–6 均已用 annual sampling attempts / attempted samples，并逐图明确失败尝试也计入预算。v3补充图S3/S4也已实际目视确认。96次名义尝试没有被表述为96个成功标签。
6. **工作记录更新。** REVISION_PLAN 的多项 Planned/In progress 与已完成结果不再一致，交付前应更新为完成/已限定范围，并将案例图号改为实际 Fig. 6。此为状态记录问题，不是数据或结论错误。

## 2. 九项评审问题的实质回应

| 评审 | 实际回应与证据 | 审计判断 |
|---|---|---|
| 1. 具体用途、时钟和必要性 | Introduction 首段与 Methods 定义本地高频基线后的一年降频，明确是假设性操作场景；不把 24 h 当实际实验室规范。Results 给出负荷时间集中性、onset/实际到达前发生量、历史误差与残差持续性；Table 2 包含零新增标签。 | 已实质回应；时钟修复已关闭。 |
| 2. 原重构器限制公平比较 | 新完整系统确实重新运行 latest 输出及保存的 collection-time innovation；四种核心日历共用输出、预算和可见信息。原始 pooled、旧固定日历诊断及新闭环结果分开。开发因素比较 memory/age/update family，并明确等 nominal half-life 不等于等有效记忆。 | 已回应；没有把新 16.87% 冒充旧 17.03% 或纯表示复杂度效果。 |
| 3. 延迟、pending、浓度适应机制 | 主 24 h 场景 queue 为零；固定真实延迟改变评分 delay；72 h 才检查 pending omission。结果明确未建立机制收益。Results 与OR3均保留旧 rho 开关结果并说明同时影响两种权重。 | 已回应；增量复核后的主文解释正确。 |
| 4. 配额控制大量购买 | 新 deadline-only 基线不读流量/浓度/不确定性；实际 fallback 分别报告全数据站与事件主子集；案例给出 collection/return/fallback 标记，实际 arrival 统计包含无返回事件。 | 已回应；没有把预算完成率当自适应证据。 |
| 5. surrogate 与主要终点不同 | Methods 明说 RFF 内部绝对负荷方差 score 不等于 latest 输出的真实误差收益；Table 3 给出 kg、方向和 10/20% 情景；候选诊断固定候选、后续日历及额外一份样本，不称等预算政策或部署效应。 | 已回应；保留不利排名与 32 个损害候选。 |
| 6. QR 等对照范围 | QR/D-opt 降为透明保留的补充日历改造，不支持完整方法优越性结论；明说预算超过短历史基底秩和时间分配自由度不同。主比较聚焦 uniform/flow/deadline/value 与可靠简单输出。 | 已回应；没有要求与严格在线任务不匹配的事后估计器进入同一排名。 |
| 7. 站点异质性与解释 | 历史 forward 残差独立于目标标签；target-history 变化标为解释性并承认模型重拟合和支持变化混杂。全部站点显示及按固定极值/中位规则提取三个真实案例。Discussion 将水文混合/营养供给解释标为待检验。 | 已回应；没有九站多变量机制拟合或部署前已验证 gate。 |
| 8. 多年高频历史不等于长期稀疏 | 摘要/Introduction/Methods/Discussion 限定单年转型；每年独立历史窗口不构成连续稀疏运行；additional stations 仍要求本站历史。 | 已选择评审允许的严格范围路线，没有伪称已完成连续多年稀疏训练。 |
| 9. 可审计与单位 | 候选—站点年—事件链、购买/返回记录、共同参考公式、实际 raw 单位例子、表格源及独立实验核验已存在。AI 披露涵盖设计、分析、代码及实质写作，不被降格为仅润色。 | 已回应；本报告直接检查关键数字，独立单位检查不靠百分比抵消。 |

## 3. 六项证据上限的处理

| 上限 | 当前处理 | 边界是否保持 |
|---|---|---|
| 缺失时段真实输送未识别 | 保留/排除事件峰值、时长、季节、峰值参考完整性；时间/水量支持；完整参考小时限定，不填补缺失浓度为真值。 | 是；没有完整年度或所有洪水性能主张。 |
| 光学记录不等于独立实验室真值 | sensor-reference 身份贯穿；讨论共同漂移、干扰、维护误差；明确加高斯噪声不能解决共同偏差。 | 是；没有实验室化学准确度声称。 |
| 独立环境重复数有限 | temporal 9 站/5 HUC4、external 8 站/6 HUC4，站层级区间及分组敏感性；小时、事件、seed 不充作独立河流。 | 是；区间为描述性 pointwise，不作普适性保证。 |
| 已查看资料不是未见确认 | 保留原冻结实验身份；全部新系统和诊断标为 post-result；Discussion 明说新确认需要未参与选型的记录。 | 是；无“重新冻结就重新未见”的表达。 |
| 实际成本与可靠性未知 | 预算为名义尝试，delay 为信息情景；明确未模拟交通、人员、服务故障和实时修订，不换算货币节约。 | 是；图注样本/尝试词汇已增量统一。 |
| 估算改善不等于环境改善 | Conclusions 终点为 monitoring quality / transport estimation，并明确不意味着河流环境状态改善。 | 是。 |

## 4. 数字与来源对照

除直接对回下列结果外，使用既有 `EXPERIMENT_VERIFICATION.md` 的独立事件聚合、配对和时间顺序检查，以及 `context_independent_check.json` 的独立单位/lag/arrival/case 检查。没有重复拟合模型。将主表 2 与 3 解析后逐格按来源全精度格式化比较，**70 个数字单元格全部一致**。Table 1 的站/站点年/事件/HUC4 和水量中位数也与 context/factorial 汇总相符。

### 4.1 样本和环境描述

| 数字组 | 核验值 | 来源 |
|---|---|---|
| 工作数据 | 21 站，1,288,728 小时，748,679 完整参考小时，2019–2025 | extended 数据准备审计与既有数据清单 |
| 开发支持 | 7 站/14 数据站点年；7 站/13 事件站点年；36/65 事件；5 HUC4；水量中位数 91.48% | context summary；factorial aggregate |
| 时间支持 | 13 数据站点年；9 主站/46 eligible 事件（147 defined）；5 HUC4 | context summary；main aggregate |
| additional 支持 | 8 站/16 数据站点年；8 站/14 事件站点年；64/161 事件；6 HUC4 | context summary；main aggregate |
| top 10% / 历史 Q90 负荷份额 | temporal 42.37% / 53.23%；external 49.04% / 43.26% | context_site_year.csv，context_summary.json |
| 参考水量 | temporal median 94.39%，range 77.42–98.43%，pooled 90.89%；external median 94.58%，pooled 90.48% | context_site_year.csv，context_summary.json |
| retained/excluded temporal | duration 58/43 h；Qpeak 243.52/125.16 m³/s；峰值完整45/46与75/101；季节3/18/23/2与10/28/44/19 | context_events.csv；context_event_retention_summary.csv |
| onset 24/72 h | temporal event median 42.50/100%，mass weighted 13.36/35.06%；external 43.45/100%，25.18/61.01% | context_summary.json |
| historical persistence | 6/24/72/168 h median .963/.859/.694/.468；168 h range −.025至.872 | context_residual_persistence.csv；连续合格对 |

水量中位数按数据合格 station-year；事件结果按事件可评价 station-year/站汇总。两者分母不同且已说明。历史 persistence 是 seed 41 的前推浓度残差，训练浓度不含校准年；Q 标准化沿用允许的全历史窗口，文中已诚实区分于全嵌套 feature-scaling 验证。

### 4.2 新完整系统与主区间

`summary_main_v1/aggregate_metrics.csv`、`paired_effects.csv`：

| 策略 | temporal B24/B48/B96 (%) | external B24/B48/B96 (%) |
|---|---|---|
| value | 22.81 / 21.19 / 16.87 | 18.45 / 16.74 / 14.55 |
| flow | 23.86 / 22.13 / 17.70 | 17.42 / 16.09 / 14.64 |
| uniform | 25.75 / 22.18 / 20.68 | 18.52 / 17.54 / 15.59 |
| deadline | 25.54 / 24.29 / 19.41 | 21.94 / 20.16 / 17.49 |
| no new labels | 31.74（零预算） | 19.07（零预算） |

B96 正差均定义 baseline minus value，单位为百分点：

| 群组/基线 | 点估计 | station 95% interval | 改善站 |
|---|---:|---:|---:|
| temporal / no labels | 14.87 | 8.61至21.12 | 9/9 |
| temporal / flow | 0.83 | −0.86至2.42 | 6/9 |
| temporal / uniform | 3.81 | −0.01至7.96 | 7/9 |
| temporal / deadline | 2.54 | 0.99至4.17 | 7/9 |
| external / no labels | 4.52 | −2.36至10.97 | 5/8 |
| external / flow | 0.09 | −2.52至1.99 | 5/8 |
| external / deadline | 2.95 | 0.93至5.67 | 7/8 |

Temporal flow 的 HUC4 interval −0.68至2.30 匹配来源。外部五站改善三站恶化、区间过零均保留；“on average”只能解释已观察均值，不能推出新的总体显著收益。

Table 3 的 kg N、正负号、20% 与 50% 比例全部通过逐格比较。重点非同向结果：temporal uniform/value absolute event kg 为 47.53/51.80 千 kg，external 为 24.55/25.88；temporal value 的 >50% 事件比例6.61%略高于flow6.00%。≥3事件敏感性支持8站44事件与6站60事件，B96 value/flow分别17.84/18.20%与14.35/16.07%，均与原精度舍入一致。

### 4.3 更新、机制和候选诊断

- 原始 pooled B96 temporal value/uniform/flow 26.56/29.45/27.87%；external 21.39/21.16/22.93%；旧 fixed-calendar latest value temporal 17.03%。来源为原 `results/paper_analysis_main` 与 `paper_analysis_reconstructors`，不混为新闭环结果。
- 开发短尺度 arrival flow latest/pooled 15.31/18.84%，差3.53 points，CI1.33–6.00，6/7站；2160 h 对应16.20/16.01%，差−.19，CI−6.17至6.35。Periodic short 19.48/21.23%，long21.16/15.87%。Sample-age flow short为16.32/18.94%，arrival为15.31/18.84%。来源 `summary_factorial_v1` 与 `diagnostics_v1/factor_family_contrasts.csv`。
- Fixed actual delay 24 h aware/immediate-score 16.87/16.71%，alternative-minus-aware CI−.71至.31；72 h aware/immediate/omit-pending 22.12/22.00/22.03%，相应CI−.43至.26与−.40至.30。正文没有把实际延迟改变的总效应归因为评分延迟项。
- 主24 h pending=0；72 h aware的22,455/37,925 eligible candidate evaluations 有pending，最大1。该候选计数包含13数据合格站与3seed，不是独立事件数。来源完成检查及机制trace汇总。
- 全13 temporal站value fallback 60.26/67.84/76.44%，flow58.23/65.97/71.85%；event-primary value52.16/61.11/70.52%；external event-primary value57.47/73.61/83.16%。均由 `attempt_summaries.csv` 核对，未混用全站与主事件子集。
- 月候选168，82 eligible，50改善32损害；relative utility median1.70个百分点，pooled rank .153，within-site-rank .114。来源 `candidate_summary.json`；其筛选、额外样本非等预算及固定后续日历身份清楚。

### 4.4 实际到达与过程案例

实际 arrival 采用先每物理事件跨3seed平均、再事件→station-year→station等权。B96共46物理事件/9站，非138独立事件：

| 策略 | first usable arrival 前参考负荷 (%) | no usable arrival within event (%) |
|---|---:|---:|
| value | 48.13062514896847 | 22.795414462081126 |
| flow | 46.967273743983184 | 18.271604938271604 |

因此正文48.13/46.97%与22.80/18.27%正确。它们不是等事件均值（后者50.56/48.10%），也不是质量加权份额。来源 `context_arrival_summary.csv`，种子先合并的 event/station 中间表完整保留。

案例选自新 `experiments_main_temporal_v1`，B96/seed41，以全部46事件的 value-minus-flow absolute RE 固定极值/中位规则选择：

- 06902000，Jul 9–10：value4.66% vs flow41.92%，二者事件内无可用返回；解释为此前返回留下的不同校正状态正确。
- 06902000，Jul 6–8：value41.83% vs flow13.79%；first-arrival前参考负荷56.38% vs92.05%。额外直接加总首次value返回之后的小时记录：参考19,599.4147547 kg，value预测8,366.6602649 kg，剩余段RE=−57.3117%。故“underestimated remaining transport”有记录支持，而不只是由整事件误差猜测。
- 02035000，May14–21：两策略购买与返回时间相同，均0.44%。没有为避免两个极端同站而替换案例。

这些是解释性真实轨迹；只有浓度与流量的传感器记录，不支持识别营养源、混合机制或跨站部署决策规律。

## 5. 单位和计算身份

Online Resource 1 的独立例子正确：02035000，2025-01-01 00:00 UTC，7350 ft³/s ×0.3048³ =208.1288224512 m³/s；900 s体积187315.94020608 m³；0.34 mg N/L对应63.6874196700672 kg N。四个quarter Q=7350,7350,7350,7320且C=.34，合计748499.205966336 m³和254.489730028554 kg N。这个绝对单位检查来自原始单位元数据及原始记录，未利用相对误差抵消。

名义预算24/48/96、6 h决策网格、24 h间隔、24 h主实际返回；辅助6/72 h原冻结敏感性与新固定实际delay的机制实验身份分开。正式新run完成记录提供elapsed：main temporal354.8438 s，main external462.8606 s，factorial94.2951 s，mechanisms451.0262 s，candidate9.7466 s。这些是各次机器run用时，不是整个项目人工/机器总成本；当前主文没有把它们夸大为部署效率或全部研究时间。

本轮另行实验核验已经直接检查1281条付费日历、预算/间隔/到达、140汇总行与48主配对；context核验检查344 lag记录、1656 actual-arrival记录和12 case-policy负荷。本文的证据强度仍由研究设计和共同观测支持决定，哈希与测试不替代科学解释。

## 6. 当前版本与审计边界

在逐格主表比较时读取的SHA256如下；如主代理继续加入已建议的澄清语句，应以增量复核关闭，不应将这个旧哈希声称为后续字节完全一致：

| 文件 | SHA256 |
|---|---|
| Introduction.md | 8cdb67e6a8ea07ff69301375a470bb99c4808c9c2adc669b975af49e57b6cb00 |
| Methods.md | 47e1b6e79c83df4dfcf37d7734ccb781af675ac7768ab0e6f7317df443c9cdb3 |
| Results.md | 5135a10fcb10f45ce40d07c507b3390051e3e6b2afd2398c49bc1c3dd112aab4 |
| Discussion.md | 62e2fdf9e8b9d2cce0f119cd5c8953a29ea74ad8c0a8fd39300582fa975f9ce6 |
| manuscript.md | 345e44801d52517164eaf91e402c0fabe257c83e701c73240e02230f70b3327a |

没有新增推断性检验或九站机制模型。主张限定、负结果呈现和三种实验身份（原冻结、旧事后fixed calendar、新修订完整系统）已一致。剩余独立实验室真值、缺失负荷、实际运行成本和未见确认属于已公开的证据边界，不能由更多种子或叙述调整消除；它们也不构成本研究所选监测评估任务必须无限追加的实验。
