#!/usr/bin/env python3
"""ROI Compass v2. Python 3 standard library only; see references/calculator.md."""
import argparse
import copy
import json
import math
import sys
from pathlib import Path


class InputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def number(value, label, low=None, high=None):
    require(type(value) in (int, float) and math.isfinite(value),
            f"{label}: 必须为有限数值（不可为布尔值、NaN 或 Infinity）")
    require(low is None or value >= low, f"{label}: 不得小于 {low}")
    require(high is None or value <= high, f"{label}: 不得大于 {high}")
    return value


def integer(value, label, low, high):
    require(type(value) is int and low <= value <= high,
            f"{label}: 必须为 {low}~{high} 的整数")


def text_field(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: 必须为非空文字")


def keys(obj, allowed, required, label):
    require(isinstance(obj, dict), f"{label}: 必须为对象")
    require(not set(obj) - set(allowed), f"{label}: 未知字段 {sorted(set(obj) - set(allowed))}")
    require(not set(required) - set(obj), f"{label}: 缺少字段 {sorted(set(required) - set(obj))}")


def validate(cfg):
    require(isinstance(cfg, dict), "配置必须为 JSON 对象")
    if any(k in cfg for k in ('all_in_cost', 'l1_value', 'l2_gross', 'cashflows')):
        raise InputError("检测到旧版配置。请按 references/calculator.md 迁移，明确初始成本和各期成本；不会自动猜测现金流口径。")
    required = ('schema_version', 'name', 'currency', 'period_unit', 'initial_cost',
                'period_costs', 'discount_rate', 'benefits', 'cost_source', 'cost_quality')
    keys(cfg, required + ('l3_intangibles',), required, 'config')
    require(type(cfg['schema_version']) is int and cfg['schema_version'] == 2, 'schema_version 必须为 2')
    for field in ('name', 'currency', 'cost_source'):
        text_field(cfg[field], field)
    require(cfg['period_unit'] in ('month', 'quarter', 'year'), 'period_unit: month/quarter/year')
    require(cfg['cost_quality'] in ('high', 'medium', 'low'), 'cost_quality: high/medium/low')
    number(cfg['initial_cost'], 'initial_cost', 0)
    require(isinstance(cfg['period_costs'], list) and 1 <= len(cfg['period_costs']) <= 600,
            'period_costs 必须含 1~600 个期间；每期都要填，零成本填 0')
    for t, cost in enumerate(cfg['period_costs'], 1):
        number(cost, f'period_costs[{t}]', 0)
    number(cfg['discount_rate'], 'discount_rate')
    require(cfg['discount_rate'] > -1, 'discount_rate 必须大于 -1，且与 period_unit 同频率')
    require(isinstance(cfg['benefits'], list), 'benefits 必须为数组，可为空')
    ids = set()
    for i, b in enumerate(cfg['benefits']):
        label = f'benefits[{i}]'
        fields = ('id', 'name', 'level', 'amount', 'start_period', 'duration', 'dropoff',
                  'basis', 'adjustments', 'adjustment_reason', 'source', 'evidence', 'overlap_group')
        keys(b, fields, fields, label)
        for field in ('id', 'name', 'adjustment_reason', 'source', 'overlap_group'):
            text_field(b[field], f'{label}.{field}')
        require(b['id'] not in ids, f"重复收益 id: {b['id']}")
        ids.add(b['id'])
        require(b['level'] in ('L1', 'L2'), f'{label}.level: L1/L2')
        number(b['amount'], f'{label}.amount')
        integer(b['start_period'], f'{label}.start_period', 1, len(cfg['period_costs']))
        integer(b['duration'], f'{label}.duration', 1, len(cfg['period_costs']))
        require(b['start_period'] + b['duration'] - 1 <= len(cfg['period_costs']),
                f'{label}: 收益超出测算时间窗，请延长成本数组或缩短持续期')
        number(b['dropoff'], f'{label}.dropoff', 0, 1)
        require(b['duration'] > 1 or b['dropoff'] == 0, f'{label}: 单期收益的 dropoff 必须为 0')
        require(b['basis'] in ('gross', 'incremental'), f'{label}.basis: gross/incremental')
        names = ('deadweight', 'attribution', 'displacement')
        keys(b['adjustments'], names, names, f'{label}.adjustments')
        for key, value in b['adjustments'].items():
            number(value, f'{label}.adjustments.{key}', 0, 1)
        if b['basis'] == 'incremental':
            require(b['adjustments']['deadweight'] == b['adjustments']['attribution'] == 0,
                    f'{label}: 已隔离本次贡献的增量不得再次扣自然发生/他方归因')
        if b['amount'] < 0:
            require(not any(b['adjustments'].values()) and b['dropoff'] == 0,
                    f'{label}: 损失请填写已归因的各期金额，不自动通过扣减或衰减缩小损失')
            require(b['basis'] == 'incremental', f'{label}: 损失须为已归因的增量口径')
        evidence = b['evidence']
        keys(evidence, ('design', 'data_quality', 'valuation_quality', 'note'),
             ('design', 'data_quality', 'valuation_quality', 'note'), f'{label}.evidence')
        require(evidence['design'] in ('experiment', 'quasi', 'estimate', 'unknown'),
                f'{label}.evidence.design: experiment/quasi/estimate/unknown')
        for field in ('data_quality', 'valuation_quality'):
            require(evidence[field] in ('high', 'medium', 'low'), f'{label}.{field}: high/medium/low')
        text_field(evidence['note'], f'{label}.evidence.note')
    groups = [b['overlap_group'] for b in cfg['benefits']]
    require(len(groups) == len(set(groups)),
            '同一 overlap_group 存在多个收益：请去重/合并；独立收益须使用不同组并在来源中说明边界')
    l3 = cfg.get('l3_intangibles', [])
    require(isinstance(l3, list), 'l3_intangibles 必须为数组')
    for item in l3:
        text_field(item, 'l3_intangibles item')


def evidence_grade(benefit):
    """Conservative internal rubric, not statistical confidence or automated audit."""
    e = benefit['evidence']
    design = {'experiment': 3, 'quasi': 2, 'estimate': 1, 'unknown': 1}[e['design']]
    quality = {'high': 3, 'medium': 2, 'low': 1}
    score = min(design, quality[e['data_quality']], quality[e['valuation_quality']])
    return 'CBA'[score - 1]


def compute(cfg):
    validate(cfg)
    rows = [{'period': t, 'cost': cost, 'l1_gross': 0.0, 'l1_adjusted': 0.0,
             'l2_gross': 0.0, 'l2_adjusted': 0.0}
            for t, cost in enumerate(cfg['period_costs'], 1)]
    items = []
    for b in cfg['benefits']:
        factor = math.prod(1 - value for value in b['adjustments'].values())
        raw_total = 0.0
        for offset in range(b['duration']):
            raw = b['amount'] * (1 - b['dropoff']) ** offset
            row = rows[b['start_period'] + offset - 1]
            row[b['level'].lower() + '_gross'] += raw
            row[b['level'].lower() + '_adjusted'] += raw * factor
            raw_total += raw
        items.append({'id': b['id'], 'name': b['name'], 'level': b['level'],
                      'basis': b['basis'], 'source': b['source'], 'evidence': b['evidence'],
                      'adjustment_reason': b['adjustment_reason'], 'factor': factor,
                      'gross': raw_total, 'adjusted': raw_total * factor,
                      'evidence_grade': evidence_grade(b)})
    total_cost = cfg['initial_cost'] + sum(cfg['period_costs'])
    l1_raw = sum(r['l1_gross'] for r in rows)
    l2_raw = sum(r['l2_gross'] for r in rows)
    l1 = sum(r['l1_adjusted'] for r in rows)
    l2 = sum(r['l2_adjusted'] for r in rows)
    financial_npv = expanded_npv = -cfg['initial_cost']
    cumulative = discounted_cumulative = -cfg['initial_cost']
    payback = discounted_payback = None
    seen_deficit = seen_discounted_deficit = cfg['initial_cost'] > 0
    warnings = ['证据等级基于用户提供的证据描述，属于内部规则，非统计置信区间；程序不能验证来源真实性或自动识别所有重复计价。']
    for row in rows:
        row['financial_net_flow'] = row['l1_adjusted'] - row['cost']
        row['expanded_net_value'] = row['financial_net_flow'] + row['l2_adjusted']
        df = (1 + cfg['discount_rate']) ** row['period']
        financial_npv += row['financial_net_flow'] / df
        expanded_npv += row['expanded_net_value'] / df
        cumulative += row['financial_net_flow']
        discounted_cumulative += row['financial_net_flow'] / df
        row['cumulative_financial_flow'] = cumulative
        if cumulative < 0:
            seen_deficit = True
        if discounted_cumulative < 0:
            seen_discounted_deficit = True
        if seen_deficit and payback is None and cumulative >= 0:
            payback = row['period']
        if seen_discounted_deficit and discounted_payback is None and discounted_cumulative >= 0:
            discounted_payback = row['period']
        if payback is not None and cumulative < 0 and '回收后累计净现金流再次转负，首次回收期不能代表最终回本。' not in warnings:
            warnings.append('回收后累计净现金流再次转负，首次回收期不能代表最终回本。')
        if discounted_payback is not None and discounted_cumulative < 0 and '折现回收后累计折现净现金流再次转负。' not in warnings:
            warnings.append('折现回收后累计折现净现金流再次转负。')
    def roi(value):
        return (value - total_cost) / total_cost * 100 if total_cost else None
    if not total_cost:
        warnings.append('成本为零：ROI 未定义，未生成百分比。')
    if any(b['level'] == 'L2' for b in cfg['benefits']):
        warnings.append('含代理估值的扩展价值 ROI/净现值不等于企业现金回报，也不自动构成完整 SROI。')
    if cfg['cost_quality'] != 'high':
        warnings.append('成本数据含估计；请对成本金额单独做情景分析。')
    def overall(levels):
        grades = [i['evidence_grade'] for i in items if i['level'] in levels and i['gross'] != 0]
        if not grades:
            return 'N/A'
        grades.append({'high': 'A', 'medium': 'B', 'low': 'C'}[cfg['cost_quality']])
        return max(grades)  # A < B < C; weakest included evidence governs.
    result = {'name': cfg['name'], 'currency': cfg['currency'], 'period_unit': cfg['period_unit'],
              'total_cost': total_cost, 'l1_gross': l1_raw, 'l1_adjusted': l1,
              'l2_gross': l2_raw, 'l2_adjusted': l2,
              'financial_gross_roi_pct': roi(l1_raw), 'financial_roi_pct': roi(l1),
              'expanded_gross_roi_pct': roi(l1_raw + l2_raw), 'expanded_roi_pct': roi(l1 + l2),
              'financial_npv': financial_npv, 'expanded_value_npv': expanded_npv,
              'payback_period_end': payback, 'discounted_payback_period_end': discounted_payback,
              'payback_status': 'recovered' if payback is not None else ('not_recovered' if seen_deficit else 'no_initial_deficit'),
              'discounted_payback_status': 'recovered' if discounted_payback is not None else ('not_recovered' if seen_discounted_deficit else 'no_initial_deficit'),
              'financial_evidence_grade': overall(('L1',)), 'expanded_evidence_grade': overall(('L1', 'L2')),
              'cost_source': cfg['cost_source'], 'cost_quality': cfg['cost_quality'],
              'items': items, 'periods': rows, 'l3_intangibles': cfg.get('l3_intangibles', []),
              'warnings': warnings}
    def finite(value):
        if isinstance(value, float):
            require(math.isfinite(value), '计算结果溢出，请检查金额、折现率和期间长度')
        elif isinstance(value, dict):
            for v in value.values():
                finite(v)
        elif isinstance(value, list):
            for v in value:
                finite(v)
    finite(result)
    return result


def sensitivity(cfg, multipliers):
    """Change L2 valuation only; these are scenarios, never confidence bounds."""
    cases = []
    for factor in multipliers:
        number(factor, 'L2 情景倍数', 0)
        alt = copy.deepcopy(cfg)
        for b in alt['benefits']:
            if b['level'] == 'L2':
                b['amount'] *= factor
        r = compute(alt)
        cases.append({'l2_multiplier': factor, 'expanded_roi_pct': r['expanded_roi_pct'],
                      'expanded_value_npv': r['expanded_value_npv']})
    base = compute(cfg)
    # A common positive scale applied to all L2 streams; no statistical inference.
    nominal = ((base['total_cost'] - base['l1_adjusted']) / base['l2_adjusted']
               if base['l2_adjusted'] > 0 else None)
    pv_l2 = base['expanded_value_npv'] - base['financial_npv']
    discounted = -base['financial_npv'] / pv_l2 if pv_l2 > 0 else None
    return {'scenarios': cases,
            'l2_multiplier_for_zero_expanded_roi': nominal if nominal is not None and nominal >= 0 else None,
            'l2_multiplier_for_zero_expanded_npv': discounted if discounted is not None and discounted >= 0 else None,
            'note': '仅改变 L2 估值，其他条件不变；情景范围不是置信区间。阈值为 null 表示无非负解或 L2 分母不为正。'}


def report(r):
    def fmt(v):
        return '不适用' if v is None else f'{v:,.2f}'
    lines = [f"ROI Compass v2 — {r['name']}",
             f"币种 {r['currency']} | 每期 {r['period_unit']} | {len(r['periods'])} 期；初始投入在t=0，其余金额在期末",
             f"成本合计 {fmt(r['total_cost'])} | 来源：{r['cost_source']}",
             f"L1 调整前/后 {fmt(r['l1_gross'])} / {fmt(r['l1_adjusted'])}",
             f"L2 调整前/后 {fmt(r['l2_gross'])} / {fmt(r['l2_adjusted'])}",
             f"财务 ROI 调整前/后：{fmt(r['financial_gross_roi_pct'])}% / {fmt(r['financial_roi_pct'])}%（证据 {r['financial_evidence_grade']}）",
             f"含代理估值的扩展 ROI 调整前/后：{fmt(r['expanded_gross_roi_pct'])}% / {fmt(r['expanded_roi_pct'])}%（证据 {r['expanded_evidence_grade']}）",
             f"财务 NPV：{fmt(r['financial_npv'])} | 扩展价值净现值：{fmt(r['expanded_value_npv'])}"]
    statuses = {'recovered': '已首次回收', 'not_recovered': '观察期内未回收', 'no_initial_deficit': '未形成期末累计资金缺口'}
    lines.append(f"回收期（期末）：{fmt(r['payback_period_end'])}，{statuses[r['payback_status']]}")
    lines.append(f"折现回收期（期末）：{fmt(r['discounted_payback_period_end'])}，{statuses[r['discounted_payback_status']]}")
    for i in r['items']:
        lines.append(f"  {i['id']} {i['name']}：{i['level']}，证据 {i['evidence_grade']}，设计 {i['evidence']['design']}；{i['evidence']['note']}")
        lines.append(f"    金额 {fmt(i['gross'])} → {fmt(i['adjusted'])}；调整因子 {i['factor']:.4f}；{i['adjustment_reason']}")
        lines.append(f"    来源：{i['source']}")
    lines.extend('L3：' + item for item in r['l3_intangibles'])
    lines.extend('说明：' + w for w in r['warnings'])
    if 'sensitivity' in r:
        lines.append('L2 单因素敏感性（非概率区间）：')
        for s in r['sensitivity']['scenarios']:
            lines.append(f"  倍数 {s['l2_multiplier']:g}：扩展 ROI {fmt(s['expanded_roi_pct'])}% / 扩展净现值 {fmt(s['expanded_value_npv'])}")
        for label, key in [('扩展 ROI', 'l2_multiplier_for_zero_expanded_roi'),
                           ('扩展净现值', 'l2_multiplier_for_zero_expanded_npv')]:
            value = r['sensitivity'][key]
            lines.append(label + '归零的 L2 倍数：' + ('不适用' if value is None else f'{value:.4f}'))
        lines.append(r['sensitivity']['note'])
    return '\n'.join(lines).replace('不适用%', '不适用')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', nargs='?', help='JSON 文件，或 - 从标准输入读取')
    parser.add_argument('--sample', action='store_true', help='输出明确标为虚构的样例配置')
    parser.add_argument('--json', action='store_true', help='结构化结果')
    parser.add_argument('--l2-scenarios', nargs='+', type=float, metavar='MULTIPLIER',
                        help='用户指定的 L2 估值倍数，如 0.5 1 1.5；非置信区间')
    args = parser.parse_args()
    try:
        if args.sample:
            require(args.config is None and not args.l2_scenarios, '--sample 不与配置/情景计算同时使用')
            print((Path(__file__).resolve().parent.parent / 'assets' / 'sample-config.json').read_text(encoding='utf-8'))
            return 0
        require(args.config is not None, '请提供配置文件。用 --sample 查看样例；无输入不会自动计算虚构项目。')
        raw = sys.stdin.read() if args.config == '-' else Path(args.config).read_text(encoding='utf-8')
        cfg = json.loads(raw)
        result = compute(cfg)
        if args.l2_scenarios:
            result['sensitivity'] = sensitivity(cfg, args.l2_scenarios)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) if args.json else report(result))
        return 0
    except (ValueError, TypeError, OSError, ArithmeticError) as exc:
        print(f'输入/计算错误：{exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
