# ROI Compass

面向营销、客户活动、培训与系统建设的 ROI 评估 skill，附带可独立运行的 Python 计算器。

它帮助你选择评估方法、核对成本和收益口径，并分别展示**财务回报、代理估值与无形价值**。当数据不足时，先整理数据缺口和测量计划，不强行给出一个回报率。

## 用途

| 你想解决的问题 | 可以获得的帮助 |
|---|---|
| 一场客户活动值不值得投入？ | 明确观察窗口、成本、增量收益与关系价值，组织逐对象证据 |
| 培训、品牌或内部项目的收益难以量化 | 区分可兑现现金、可解释的代理估值和不宜货币化的结果 |
| 系统建设跨多年才能回本 | 逐期计算成本、收益、衰减、净现值与回收期 |
| ROI 结论依赖某个假设 | 查看 L2 估值敏感性与盈亏平衡阈值 |
| 不清楚该用 ROI、NPV 还是其他方法 | 根据决策问题、数据条件和因果证据选择方法 |

## 核心设计

- **L1 财务价值**：可兑现的增量现金贡献或现金节约，用于财务 ROI/NPV。
- **L2 代理价值**：有估值依据但不能视为现金回报的价值，单列扩展价值指标。
- **L3 无形价值**：不能可信货币化的结果，单独记录事实和后续观察。
- 按每项收益记录来源、归因口径、调整依据与重叠关系，避免重复计价和重复扣减。
- 区分衰减与折现：首个存续期不衰减，后续逐期处理。
- A/B/C 是内部证据等级，**不是统计置信度或置信区间**。

## 作为 AI skill 使用

将整个仓库保留为 `roi-compass` 文件夹，交给支持本地 skill 的 AI 工具，入口为 [SKILL.md](SKILL.md)。请按所用工具的安装机制注册该文件夹；也可直接让助手读取入口文件，再提供项目材料。

示例请求：

> 请使用 ROI Compass 评估一场客户活动。总预算 50 万元，目标是推进合作，观察期 90 天。我有成本明细、参会名单和后续合作进展。请先判断哪些价值可以计算、还缺哪些数据，再分别报告财务回报和关系价值。

> 请使用 ROI Compass 比较两个系统建设方案。我提供了期初投入、未来三年的运维成本和可兑现现金节约。请计算财务 NPV、回收期，并说明证据和假设。

以上是使用方式示例，不提供真实项目的默认价格或调整率。

## 独立运行计算器

需要 Python 3，无第三方运行依赖。以下命令从仓库根目录执行。

```bash
# 运行仓库中的虚构示例
python3 scripts/roi-calculator.py assets/sample-config.json

# 输出逐项、逐期的结构化结果
python3 scripts/roi-calculator.py assets/sample-config.json --json

# 对 L2 代理估值做单因素压力测试（倍数不是概率区间）
python3 scripts/roi-calculator.py assets/sample-config.json --l2-scenarios 0.5 1 1.5

# 创建自己的输入配置；替换虚构数据后再用于项目评估
python3 scripts/roi-calculator.py --sample > config.json

# 运行回归测试
python3 -B scripts/test_roi_calculator.py
```

输入字段、计算公式和旧版迁移方式见 [计算器说明](references/calculator.md)。输入无效时程序明确报错；没有输入时不会自动计算一个虚构项目。

## 虚构示例结果

期初成本 50 万元；一年末兑现 L1 现金收益 20 万元；L2 原始代理价值 90 万元，经示例调整后为 42.525 万元；年折现率 8%。

| 指标 | 结果 |
|---|---:|
| 财务 ROI，仅计 L1 | −60.00% |
| 扩展价值 ROI，计入调整后 L2 | 25.05% |
| 财务净现值 | −314,814.81 元 |
| 扩展价值净现值，含代理估值 | 78,935.19 元 |
| 财务回收期 | 观察期内未回收 |

这组结果表示：**现金收益尚未覆盖投入，扩展价值为正依赖代理估值假设**。不能将其描述为“活动已经盈利 25.05%”。全部数据为虚构演示，详见 [完整案例](references/worked-example.md)。

## 文件结构

```text
roi-compass/
├── SKILL.md                       # AI 使用入口
├── README.md                      # 用途与快速开始
├── scripts/
│   ├── roi-calculator.py           # 计算器
│   └── test_roi_calculator.py      # 25 项行为回归测试
├── assets/
│   ├── roi-template.md            # 评估报告模板
│   └── sample-config.json         # 虚构示例输入
└── references/
    ├── triage.md                  # 场景与方法选择
    ├── roi-schools.md             # 常用方法卡片
    ├── qual-quant-fusion.md        # 价值、归因与证据规则
    ├── calculator.md              # 输入、公式及迁移说明
    └── worked-example.md          # 可复核的虚构案例
```

## 能力边界

- 计算器采用同币种、等长期间与期末结算；复杂税务、汇率、期中现金流需另行建模。
- 不能自动验证数据来源真实性、因果识别是否成立，或识别全部语义上的收益重叠。
- L2 扩展价值指标不等于企业现金收益，也不自动构成完整 SROI 分析。
- IRR、PI、MMM/MTA、实验或 DiD 效应估计、统计区间和蒙特卡洛未内置实现；文档推荐一种方法不代表计算器已执行该方法。
- 本版已通过 25 项行为回归测试；尚未用真实业务数据完成验收。
- 新版配置为 `schema_version: 2`，不静默兼容旧版 `all_in_cost/cashflows`。请按 [迁移步骤](references/calculator.md#从旧版迁移) 明确成本与现金流口径。

## 方法依据

- [Google Ads：增量转化与归因转化](https://support.google.com/google-ads/answer/14102450?hl=en)
- [A guide to Social Return on Investment](https://www.fi-compass.eu/sites/default/files/publications/Cabinet_office_A_guide_to_Social_Return_on_Investment.pdf)

L1/L2/L3 分层及内部证据等级是本项目的工作约定，不宣称为上述机构的统一标准。
