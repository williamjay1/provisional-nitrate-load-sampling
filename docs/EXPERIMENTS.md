# 2026-10-09 修订实验约定与运行记录

路线：SCIE 环境监测方法与应用验证，目标 EMA。问题是明确的信息到达与预算条件下，采样规则、结果使用方式、队列和截止日历分别提供何种可评价效用。评价公平性、信息时序、参考支持与主张边界为主要标准，不追加经济学因果识别门槛。已使用 experiment-design 技能组织因素与对照。

**证据身份：所有修订分析均为 revision post-result。** 原 2023/2024 开发、额外站点以及 2025 资料均已被观察；本次执行前的固定设计记录不会将其重新变成未见验证。保留原冻结脚本、输入及结果不变，新实现只存在 revision_20261009/scripts，输出只写该目录下 results/experiments_*。

## 固定比较

| 分析 | 资料与重复 | 改变的因素 | 固定内容 |
|---|---|---|---|
| 完整新系统 | temporal 2025 + external 2023/24，原数据资格；预算24/48/96；seed41/73/109 | uniform、flow_trigger、deadline_only、value | 实际延迟24h；共同 latest-returned residual；tau168h、arrival-age；原RF历史预测器；共同6h候选、min24h、每block1次预算；失败照计成本 |
| 开发期匹配时钟因素 | 仅original开发站2023/24，seed41，B96；三种简单日历uniform/flow/deadline | half-life=168×ln2=116.4487h、720h、2160h；sample/arrival age；rff_pooled/latest_residual，完整3×2×2 | 固定实际日历与24h返回；rho=0；相同历史噪声尺度与RF先验；不以目标年度选择参数 |
| 延迟评分与队列机制 | temporal 2025，B96，3 seeds | 同一实际delay24/72下，评分假设delay=0或实际值；实际72再比较pending-aware与omit-pending | 实际信息只按真实到达时间释放；共同最新残差输出和原C2获取协方差，rho=.1；不改变预算自由度 |
| 候选价值诊断（待主网格后实现） | 仅development，固定每月候选和未来日历 | 加入/不加入一个候选样本后，未来72h负荷误差的条件差 | 未来参考只用于事后评分；不据future质量选候选、不重排后续购买；完整窗口资格过滤单独标明；isolated diagnostic，不称闭环因果效应 |

最新残差输出的 tau168h 和 arrival-age 来自已经查看过的旧诊断，不进行新的测试数据调参。value 内部仍保留原 C2 的9维 RFF 获取协方差、2160h半衰期和96个历史阈值上下文；噪声创新使用真正发布的最新残差模型在采样时的预测，收到标签后更新获取状态，因此新系统重新闭环生成日历。uniform/flow/deadline 共享同一输出规则；flow 阈值仍为历史bank .85 分位数。所有采样器先接收、再预测、再决策。

匹配时钟中的 rff_pooled 与 latest_residual 是**更新族**对比：除表达方式外，还改变多样本池化和先验收缩，不能称为纯表示复杂度效应。clock与half-life在每个更新族内可单独比较；rho固定0避免再混入反馈噪声权重。整个因素表完整输出，无“择优后替换正式主模型”。

统一的是**名义半衰期与年龄起点**：RFF的半衰期作用于数据精度和信息向量，latest的半衰期直接作用于残差幅度。RFF还含固定先验精度，因此相同名义值不保证相同有效预测记忆或冲激响应；结果不能作为已完全隔离“模型复杂度”的证据。

纯 deadline_only 不读取score，只在每个block的最后允许候选购买。value真实24h、最小间隔24h且先收后买意味着eligible候选处pending=0；用日志验证该事实。真实72h为队列对照的激活场景，失败样本也在预定到达前保留于公开pending集合。

## 运行前核验与资源

D盘可用空间检查约198GB。仅CPU、无GPU或外部API成本。原始资料不重下，从D工作数据和历史缓存读取。

- 16项合成检查已通过：先验/RFF原实现兼容、未购买/未返回信息不可见、失败时序、预算/间隔、deadline日历、24h无pending、72h有pending、评分忽略delay不提前真实返回、tau/half-life换算和age差异。
- 实际小debug：05482000/2023、seed41、B96，4采样系统+零标签；context 2.885秒，总4.111秒。
- 实际因素debug：同站年，3固定日历×12配置+零标签；context 5.964秒，总7.428秒。
- 预计主网格29个数据合格站点年×3seed×12付费条件=1,044回放，另87个零标签参照，约10–20分钟CPU墙钟上限建议；最终以manifest实测为准。两个cohort可并行。预计输出低于0.5GB、单进程内存约1GB；这些是运行估计。
- 开发因素按14个数据合格站点年预期504个重构条件、14个零标签，约2–5分钟；真实资格由原函数确定，不强制凑数。
- 机制按13个数据合格站×3seed×5条件=195回放，另每实际delay的零标签，约3–6分钟。

## 输入、实现及信息边界

工作输入：`datasets/extended_hourly_2019_2025_v1.parquet`；SHA256 `05398eb7d883d36cbb5682847954dd56ac651ae7fa1e2649e6f0de68d9ea9905`。

修订网格执行前实现SHA256：

- revision_experiments.py：`5a29f7a6553e5901c27c3fea9a118425a3320f2c1ca2da1a1ba5ed222950fd0f`（实际manifest同时记录精确值）。
- revision_state.py：`c0c4b920dcd5e002d997e5aee42ff5d67fd16e91a50c045f51668e910a67504f`。

每个run_manifest.json记录精确脚本/冻结依赖SHA和输入SHA；model_audit.json逐site/year/seed记录原历史cache路径和SHA、历史训练审计、真实延迟与获取配置。运行结束重新核对实现hash；中途代码变动则拒绝写最终完成manifest。读入原load_context时仍要求过去年度训练；目标标签仅在action之后由回放环境检查。

## 输出字段契约

共同键：`site, year, seed, stage, policy, budget, reconstructor, scenario, delay_hours, mode, experiment, analysis_status`。`assumed_delay_hours`与真实`delay_hours`分开。

- `metrics.csv`：原paper_metrics主端点及whole-window指标，保持原单位/资格。
- `events.csv`：逐事件参考/预测kg、相对误差、资格、覆盖及采样次数，供主代理计算绝对/有符号kg、风险和10/20%分析情景。
- `attempts.csv`：采样/到达时刻、成功/失败、horizon内返回、reason、forced_deadline、测量尺度和实际发布的采样时预测。
- `candidate_trace.parquet`：只记录真正有资格执行动作的候选；pending_count、当前score/threshold/action，并列delay_aware_pending、delay_zero、delay_aware_omit三种评分/阈值/触发。在同一个当前状态计算，属于诊断对照，不自动等同三条闭环轨迹。
- `predictions.parquet`：使用`--save-predictions`时记录第一个seed全部预算/策略的逐时输出和共同先验，供按固定选择原则画事件图；其余种子均保留事件与汇总端点。
- 因素分析额外键：`reconstructor_family, half_life_hours, age_origin, rho=0`。其attempts按固定日历只存一次；reconstruction配置通过共同calendar键连接，不伪称每个配置另行采样。

主代理负责station/HUC4配对区间、跨年/种子汇总及正文。没有最终run_manifest的目录是未完成运行；失败记录保留，不将其并入已完成结果。

## 固定命令

研究Python：`C:/Users/Administrator/AppData/Local/Programs/Python/Python312/python.exe`；脚本：`revision_20261009/scripts/revision_experiments.py`。

```text
--suite systems --stage temporal --years 2025 --seeds 41 73 109 --budgets 24 48 96 --run-name main_temporal_v1 --save-predictions
--suite systems --stage external --years 2023 2024 --seeds 41 73 109 --budgets 24 48 96 --run-name main_external_v1 --save-predictions
--suite factorial --stage development --years 2023 2024 --seeds 41 --budgets 96 --run-name factorial_development_v1
--suite mechanisms --stage temporal --years 2025 --seeds 41 73 109 --budgets 96 --run-name mechanisms_temporal_v1 --save-predictions
```

2026-10-09：主代理已批准以上网格，先运行主比较，再运行因素与机制；候选诊断单独记录其代码与设计，不变更这些结果身份。

## 实际完成记录（2026-10-09）

以下目录均有最终 `run_manifest.json`，不是 debug 结果；时间为脚本实测墙钟，部分任务并行，不能直接相加作为总历时。

| 正式目录尾名 | 站点年 | metrics 行 | events 行 | 实测秒 |
|---|---:|---:|---:|---:|
| main_temporal_v1 | 13 | 507 | 5733 | 354.84 |
| main_external_v1 | 16 | 624 | 6279 | 462.86 |
| factorial_development_v1 | 14 | 518 | 2405 | 94.30 |
| mechanisms_temporal_v1 | 13 | 273 | 3087 | 451.03 |

`experiments_candidate_development_v1` 在14个开发站点年输出168个固定候选，耗时9.75秒；82个满足事后评价资格，全部168条均保留，不替补。主要字段为 `acquisition_score`、`absolute_error_reduction_kg`、`absolute_relative_error_reduction`、`eligible_diagnostic` 和排除原因。候选脚本SHA256为 `a696e114046d67cd19df6262bf0dd34399be48df40fc08b600891b5ac150f2e7`，5项局部时序/更新合成检查写在该manifest。此前16项完整回放检查另存 `results/experiments_self_test_v1.json`。

完整运行检查写入 `results/experiments_completion_checks_v1.json`。24h主比较的全部可行动候选均为pending=0；72h机制中aware场景有22455/37925个候选pending>0（最大1），omit场景22056/37604，assumed-zero场景22233/37828。这里是各自闭环轨迹上的候选分母，不能把它们当作同一批候选的配对比例。所有付费日历的真实到达差均符合指定24/72h。

没有运行失败或中途变更被冻结实验实现；四正式网格和候选诊断均核对了运行前后脚本SHA。debug目录仅供软件核验，不进入科学汇总。后续科学/数值审查记录在 `docs/EXPERIMENT_VERIFICATION.md`。

### 候选诊断的预定抽取规则（先写规则，后计算）

仅original开发站2023/2024、seed41，使用 B96 periodic + latest residual 的固定基线日历。每月15日12:00 UTC作为唯一预定候选，不根据浓度、误差、未来覆盖或score重选。每个候选在当时按已返回观测重建原RFF获取状态与评分，已购买但未返回的信息只以公开pending元数据进入投影。返回前不能查看其浓度或成功标记。

然后才作离线诊断：真实delay24h，固定原未来购买日历和每份原样本的采样时创新/权重，仅增加该一个候选的latest residual更新；比较其到达之后72h共同观测窗口的绝对负荷差。下一份固定日历成功样本返回后，两条latest轨迹再次相同。候选失败、与已购样本重合、最小间隔不足、窗口覆盖不足95%或参考负荷接近0，均输出明确状态，不以新时间替补。间隔判断用已知固定日历，覆盖及参考负荷过滤仅在事后评价时应用。额外一次样本不是新的同预算政策，不能用其误差差声称闭环因果增益或重新训练/校准评分。
