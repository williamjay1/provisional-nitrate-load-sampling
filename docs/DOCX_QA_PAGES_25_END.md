# Word visual QA: pages 25 to the final page

2026-10-09。范围仅为科研稿实质可读性：正文与公式是否缺字/裁切，表格是否错列/漏行，图及图注是否完整可辨。使用本机 native `view_image` 逐页实际查看；数值准确性由 `CONTENT_VERIFICATION.md` 和独立结果核验负责。没有改动正文、Word或生成脚本。

## render_v2 预检

源目录：`revision_20261009/temp/render_v2`。实际查看page-25.png至page-34.png，共10页。

| 页 | 主要内容 | 实际视觉结论 |
|---|---|---|
| 25 | 站点表续页、Fig S1 | 表头重复且行完整；图轴、图例、图注未裁切。PASS |
| 26 | Fig S2历史残差/零新增标签 | 图标、轴标签、图注完整可读。PASS |
| 27 | Fig S3、Fig S4 | 两图和标注可辨；S4图注顺延到28页，内容正常衔接。PASS |
| 28 | Fig S4图注结尾、Fig S5 | 续文无丢字；散点图及完整图注可读。PASS |
| 29 | Table S2配对结果 | 各列数字处于正确单元格；24行及注释完整。PASS |
| 30 | 原冻结实验身份、历史模型/日历方法 | 小公式、转置、上下标、负指数显示正常；正文不裁切。PASS |
| 31 | 原实验因素、latest公式、诊断定义 | latest-residual公式完整；正文页底自然续接32页。PASS |
| 32 | Table F1开发网格 | 表头、全部配置行与三个预算列均可读，无溢出。PASS |
| 33 | Table F2与F3主体 | 两表标题及列完整；F3正常跨页。PASS |
| 34 | Table F3余行、Table F4 | F3重复表头正确；F4多行政策名称不碰邻列，表尾完整。PASS |

预检未发现实质排版缺陷。已向主代理建议将F4图注“common main configuration”明确为original frozen pooled-output configuration，以保持新旧系统身份；这是文字澄清而非视觉缺陷。

## render_v3 逐页验收

源目录：`revision_20261009/temp/render_v3`。使用 native `view_image` 实际查看 page-25.png 至 page-36.png，共12页；没有以v2预检替代。

| 页 | 主要内容 | 实际视觉结论 |
|---|---|---|
| 25 | 候选诊断与核验说明、Table S1前18行 | 正文不裁切；各站行、州及HUC4列对齐，页底05599490行完整。PASS |
| 26 | Table S1最后3行、Fig S1 | 重复表头正确，表尾完整；保留/排除事件图及完整图注同页可读。PASS |
| 27 | Fig S2 | 历史残差与零新增标签各面板、图轴和完整图注可读。PASS |
| 28 | Fig S3 | 站点差异图及完整图注可读；图注已写96 attempted samples。PASS |
| 29 | Fig S4 | 实际返回前负荷与无返回比例图、完整图注同页可读；横轴Annual sampling attempts正常。PASS |
| 30 | Fig S5 | 候选评分与真实效用散点图及完整图注可读。PASS |
| 31 | Table S2 | 全24行配对结果及注释完整，各列无溢出/错位。PASS |
| 32 | 原冻结实验身份、历史模型与日历方法 | 转置、波浪号、负上标、单位矩阵及正文均可辨；未见公式乱码。PASS |
| 33 | 原实验因素、fixed-calendar公式与来源 | 帽号、上下标、括号和指数正常；页尾正文自然续接下一页。PASS |
| 34 | 来源说明续文、Table F1 | 全开发网格28行完整，三个预算列对齐，无裁切。PASS |
| 35 | Table F2、Table F3主体 | F2完整，F3正常跨页，政策名称和数值无错列。PASS |
| 36 | Table F3末4行、Table F4 | 续页重复表头正确；F4表头/12行/表尾完整。图注明确original frozen pooled-output configuration，身份澄清已闭环。PASS |

本范围v3结论：PASS，未发现实质可读性缺陷。另一区域单位OMML字形修复及图注粗体调整正在形成v4；本次v3结果不称为最终交付冻结，待主代理给出v4范围再做增量目视。

## 最终 render_v4 逐页验收

最终源目录：`revision_20261009/temp/render_v4`。再次以 native `view_image` 实际打开并查看 page-25.png 至 page-36.png 的全部12页，不以哈希、文本抽取或v3结果替代视觉检查。最终Word为 `delivery/Revised_River_Nutrient_Monitoring_Manuscript.docx`，SHA256：`c8ccaf11fc7dae197c3f35c949e52d724e5bf047d7f1ca5922f9aba0bf1c11fc`。

| 页 | 最终实际检查内容 | 结论 |
|---|---|---|
| 25 | S4/S5正文与Table S1前18行，站名、州及HUC4列、页底表线 | PASS；正文及单元格完整 |
| 26 | S1末3行及重复表头；Fig S1四面板、图例与完整普通字重图注 | PASS；无缺失、错列或裁切 |
| 27 | Fig S2四面板，历史lag/误差轴及完整图注 | PASS；全部可读 |
| 28 | Fig S3站号/差异轴及完整图注 | PASS；attempted samples定义可读 |
| 29 | Fig S4两面板/四策略图例及完整图注 | PASS；图注同页且未裁切 |
| 30 | Fig S5两散点面板、对数轴及完整图注 | PASS；正负刻度与文字清晰 |
| 31 | Table S2全部24行、两个区间列及表下注释 | PASS；数据处于正确列，内容完整 |
| 32 | OR3正文与RFF/QR/D-opt行内公式 | PASS；波浪号、转置、负指数与下标正常 |
| 33 | 原因素说明、latest-residual独立公式、来源说明 | PASS；帽号、下标、指数、括号完整，正文自然续页 |
| 34 | 来源续文、Table F1完整28行 | PASS；标题恢复适当字重，表尾完整 |
| 35 | Table F2全部行、Table F3前24行 | PASS；多词政策名称无邻列碰撞，跨页正常 |
| 36 | Table F3末4行/重复表头、F4完整12行 | PASS；original frozen pooled-output身份明确，表头/表尾完整 |

**最终范围结论：PASS（25–36页）。** 未发现公式乱码、单元格错位/缺行、正文或图注裁切等实质可读性缺陷。无本范围待修事项。本报告不覆盖1–24页，亦不以视觉QA替代科学数值/引用核验。仅更新审查记录，没有修改正文、Word、生成脚本或科学输入/输出。

## 主代理核对最终交付身份

最终 Word 为 v6，SHA256 `1c25b678cb115902cd7fbe8c9826e1e1371a5f0a9e6b6066e452d389cf339d0e`。v4→v5 仅第 9、10 页变化，v5→v6 仅第 22 页变化。第 25–36 页均与本代理实际逐页查看的 v4 PNG 字节完全一致；两轮全页面哈希比较分别记录在 `FINAL_PAGE_INCREMENT_CHECK.json` 和 `FINAL_RENDER_RELEASE_CHECK.json`。因此原逐页实看验收适用于最终交付的全部本责任页面，没有以新一轮未执行的图像查看冒充复查。**最终交付第 25–36 页：PASS。**
