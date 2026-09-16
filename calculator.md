# 计算器 v2

Python 3 标准库，无第三方依赖。所有命令从 skill 根目录执行。

```bash
python3 scripts/roi-calculator.py --sample > config.json
python3 scripts/roi-calculator.py config.json
python3 scripts/roi-calculator.py config.json --json
python3 scripts/roi-calculator.py config.json --l2-scenarios 0.5 1 1.5
python3 scripts/roi-calculator.py - --json < config.json
python3 scripts/test_roi_calculator.py
```

样例全部为虚构数据。无参数退出并提示输入，不自动运行演示；不提供会把空白自动填零的交互输入。`--json` 输出机器可读的明细，便于留档；错误写 stderr，退出码 2。

## 输入结构

完整配置见 `assets/sample-config.json`。未知字段报错，避免拼写错误被静默忽略。

| 顶层字段 | 说明 |
|---|---|
| schema_version | 必须为整数 2 |
| name / currency | 项目名、同一币种；程序不自动换汇 |
| period_unit | month / quarter / year，等长期间 |
| initial_cost | t=0 现金投入，非负；不含未来成本 |
| period_costs | 每期末的项目现金成本数组，1~600期；零成本也填0；数组长度定义时间窗 |
| discount_rate | 每期折现率，必须大于-1；年度利率换月度可用 `(1+r_year)^(1/12)-1` |
| cost_source / cost_quality | 成本依据；high / medium / low |
| benefits | 收益项目数组；可为空以计算仅有成本的情况 |
| l3_intangibles | 可选的非空文字数组，不入数值 |

每项收益必填：

| 字段 | 说明 |
|---|---|
| id / name | 唯一 ID、项目描述 |
| level | L1 可兑现现金贡献/节约；L2 非现金代理价值 |
| amount | 首个存续期金额，项目成本扣除前；有限数值 |
| start_period / duration | 从第几期开始、持续多少期；均正整数，不可超出时间窗 |
| dropoff | 每期衰减0~1；首个存续期不衰减；duration=1时必须为0 |
| basis | gross原始金额；incremental已隔离本次贡献 |
| adjustments | 必含 deadweight / attribution / displacement，各0~1；incremental 的前两项必须为0 |
| adjustment_reason | 三项扣减与衰减的依据；0也说明为何无需扣；未知不能用0代替 |
| source | 数据或假设出处、代理单价/数量与可比性说明；预测需明确标记 |
| overlap_group | 同一价值的唯一组；重复组报错。合并同组重复估值，独立价值用不同组并说明边界 |
| evidence | design: experiment/quasi/estimate/unknown；data_quality与valuation_quality: high/medium/low；note为证据和局限说明 |

每项收益表示按固定衰减率延续的价值流。年度金额不同则拆为 duration=1 的各期项目，使用不同 ID 和清楚的“结果+期间”重叠组；不得把同一年的同一价值拆成不同组绕过去重。已归因损失可填负金额，basis=incremental，全部调整率和dropoff为0，按期显式填写。程序不处理复杂税务、汇率、营运资本或期中现金流，必要时先整理成相同口径的现金流。

## 公式与输出

项目 b 在第 k 个存续期：
- 原始收益 `amount × (1-dropoff)^(k-1)`。
- 调整收益 `原始收益 × (1-DW) × (1-ATTR) × (1-DISP)`。
- 调整率作用于 L1 或 L2，取决于是否已隔离增量，不以“硬/软”决定是否需要归因。

全窗口名义成本 `C=initial_cost+sum(period_costs)`。
- 财务 ROI：`(sum(L1调整收益)-C)/C`。
- 扩展价值 ROI：`(sum(L1调整收益+L2调整收益)-C)/C`，不是现金盈利率，也不是完整 SROI。
- 同时输出调整前口径，供观察扣减影响；“调整前”仍按实际存续期包含衰减，表示未扣 DW/ATTR/DISP，不是无衰减的终身价值。
- 财务 NPV：`-initial_cost+sum((L1调整收益_t-period_cost_t)/(1+r)^t)`。
- 扩展价值净现值：财务 NPV 再加 L2 调整价值的现值，名称不能简化为现金 NPV。
- 回收期：财务累计净现金流首次由负到非负的期末；折现回收期使用折现现金流。不假设期内均匀发生，不进行插值；若之后再次转负，输出警告。
- 从未形成期末累计资金缺口：回收期 null、状态 no_initial_deficit；观察期未回收：null、not_recovered；首次已回收：recovered。这三个状态不同。期内流动性不可从期末数据推断。
- 成本为0时 ROI 为 null，而非0%或无限大；仍可给净现值。

金额与比率保存未四舍五入的计算值，文本显示两位小数。`financial_evidence_grade` 和 `expanded_evidence_grade` 的规则见 [qual-quant-fusion.md](qual-quant-fusion.md)。来源真实性和语义重叠仍需人工复核。

## 敏感性

`--l2-scenarios` 只改变全部 L2 amount 的共同倍率，保留其余变量；用户提供或解释选择依据。倍率0也可测试“完全不计代理价值”。它不是自动生成的概率情景。

报告给出扩展 ROI=0 和扩展净现值=0 的 L2 倍数；前者使用名义金额、后者使用折现金额。分母非正或无非负解时为 null。若 L1 已覆盖成本，继续增大正 L2 不会产生非负归零点，这不代表风险消失。负 L2 也会随倍率缩放，解释时需注明；混合正负项目建议分项建情景。

## 从旧版迁移

本版故意不静默兼容旧配置，因为旧 `all_in_cost` 和 `cashflows` 无法确定成本是否已扣两次。

1. 把 `all_in_cost` 拆成期初投入和各期项目成本，固定币种和周期。
2. 把 `l1_value` 拆成可兑现、已说明贡献口径的收益项；仅能货币化但不能兑现的放L2。
3. 把 `l2_gross` 拆成收益项目，逐项填写调整依据、来源和证据；不沿用无依据默认扣减。
4. 旧 `cashflows` 若为净现金流，先核对所扣费用，再还原成项目成本扣除前的L1收益与各期项目成本。无法拆分时不要猜测迁移。
5. `dropoff` 改为每期衰减，明确持续期；旧 has_experiment/has_quasi_control 改为逐项 evidence。
6. 旧 adjusted_roi 对应本版含代理估值的 expanded_roi_pct；新增 financial_roi_pct 只看L1。旧文档未定义的动态现金流不搬入示例。
7. 旧 units/单位成本不再是核心配置；需要时用同口径总成本除以有效对象数，并同时展示对象差异。

已实现：分项调整、逐期衰减、财务/扩展 ROI与NPV、期末/折现回收期、内部证据等级、L2敏感性、JSON输出。未实现：IRR、PI、ROAS自动转换、MMM/MTA、实验/DiD估计、统计区间、蒙特卡洛。方法推荐不等于这些算法已执行。
