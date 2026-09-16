#!/usr/bin/env python3
"""Behavioral regression tests; run directly with Python 3."""
import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'roi-calculator.py'
spec = importlib.util.spec_from_file_location('roi_calculator', SCRIPT)
roi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roi)


def sample():
    return json.loads((ROOT / 'assets' / 'sample-config.json').read_text())


def project(initial=100, costs=None, amount=60, duration=2):
    cfg = sample()
    cfg.update(initial_cost=initial, period_costs=costs if costs is not None else [0, 0],
               discount_rate=0.1, benefits=[cfg['benefits'][0]])
    cfg['benefits'][0].update(amount=amount, duration=duration)
    return cfg


class CalculatorTests(unittest.TestCase):
    def test_sample_financial_and_proxy_are_separate(self):
        r = roi.compute(sample())
        self.assertAlmostEqual(r['l2_adjusted'], 425250)
        self.assertAlmostEqual(r['financial_roi_pct'], -60)
        self.assertAlmostEqual(r['expanded_gross_roi_pct'], 120)
        self.assertAlmostEqual(r['expanded_roi_pct'], 25.05)
        self.assertAlmostEqual(r['financial_npv'], -314814.81481481483)
        self.assertAlmostEqual(r['expanded_value_npv'], 78935.18518518517)
        self.assertIsNone(r['payback_period_end'])
        self.assertEqual(r['payback_status'], 'not_recovered')

    def test_first_period_undecayed_subsequent_periods_decay(self):
        cfg = project(costs=[0, 0, 0], amount=100, duration=3)
        cfg['benefits'][0]['dropoff'] = 0.1
        r = roi.compute(cfg)
        self.assertEqual([p['l1_adjusted'] for p in r['periods']], [100, 90, 81])
        self.assertAlmostEqual(r['financial_npv'], 100/1.1 + 90/1.1**2 + 81/1.1**3 - 100)

    def test_delayed_start_discounts_from_project_start(self):
        cfg = project(costs=[0, 0, 0], amount=100, duration=2)
        cfg['benefits'][0].update(start_period=2, dropoff=0.5)
        r = roi.compute(cfg)
        self.assertEqual([p['l1_adjusted'] for p in r['periods']], [0, 100, 50])
        self.assertAlmostEqual(r['financial_npv'], -100 + 100/1.1**2 + 50/1.1**3)

    def test_future_cost_deducted_once_at_correct_time(self):
        cfg = project(costs=[20, 30], amount=100)
        r = roi.compute(cfg)
        self.assertEqual(r['total_cost'], 150)
        self.assertAlmostEqual(r['financial_roi_pct'], 100/3)
        self.assertAlmostEqual(r['financial_npv'], -100 + 80/1.1 + 70/1.1**2)

    def test_cash_payback_excludes_proxy_and_uses_period_end(self):
        cfg = project(amount=60)
        r = roi.compute(cfg)
        self.assertEqual(r['payback_period_end'], 2)
        self.assertEqual(r['discounted_payback_period_end'], 2)
        self.assertEqual(r['payback_status'], 'recovered')

    def test_discounted_payback_can_differ(self):
        cfg = project(amount=50)
        r = roi.compute(cfg)
        self.assertEqual(r['payback_period_end'], 2)
        self.assertIsNone(r['discounted_payback_period_end'])
        self.assertEqual(r['discounted_payback_status'], 'not_recovered')

    def test_reversal_after_payback_warns(self):
        cfg = project(costs=[0, 200], amount=100, duration=1)
        r = roi.compute(cfg)
        self.assertEqual(r['payback_period_end'], 1)
        self.assertTrue(any('再次转负' in w for w in r['warnings']))

    def test_zero_cost_roi_undefined(self):
        cfg = project(initial=0)
        r = roi.compute(cfg)
        self.assertIsNone(r['financial_roi_pct'])
        self.assertIsNone(r['expanded_roi_pct'])
        self.assertEqual(r['payback_status'], 'no_initial_deficit')

    def test_no_benefits_is_loss_not_missing_zero(self):
        cfg = project()
        cfg['benefits'] = []
        r = roi.compute(cfg)
        self.assertEqual(r['financial_roi_pct'], -100)
        self.assertEqual(r['financial_evidence_grade'], 'N/A')

    def test_negative_incremental_benefits_are_retained(self):
        cfg = project(amount=-20)
        r = roi.compute(cfg)
        self.assertEqual(r['l1_adjusted'], -40)
        self.assertEqual(r['financial_roi_pct'], -140)

    def test_negative_losses_cannot_be_reduced_by_adjustments(self):
        cfg = project(amount=-20)
        cfg['benefits'][0]['adjustments']['displacement'] = 0.5
        with self.assertRaises(roi.InputError):
            roi.compute(cfg)

    def test_l1_gross_also_requires_attribution(self):
        cfg = project(amount=100, duration=1)
        b = cfg['benefits'][0]
        b.update(basis='gross')
        b['adjustments']['deadweight'] = 0.5
        r = roi.compute(cfg)
        self.assertEqual(r['l1_adjusted'], 50)
        self.assertEqual(r['financial_roi_pct'], -50)

    def test_incremental_cannot_be_adjusted_twice(self):
        for key in ('deadweight', 'attribution'):
            cfg = project()
            cfg['benefits'][0]['adjustments'][key] = 0.1
            with self.subTest(key=key), self.assertRaises(roi.InputError):
                roi.compute(cfg)

    def test_sample_grade_preserves_quasi_evidence(self):
        r = roi.compute(sample())
        self.assertEqual(r['financial_evidence_grade'], 'B')
        self.assertEqual(r['expanded_evidence_grade'], 'C')
        self.assertTrue(all(i['evidence']['design'] == 'quasi' for i in r['items']))
        self.assertNotIn('无对照', roi.report(r))

    def test_experiment_not_downgraded_by_proxy_share_alone(self):
        cfg = sample()
        for b in cfg['benefits']:
            b['evidence'].update(design='experiment', data_quality='high', valuation_quality='high')
        self.assertEqual(roi.compute(cfg)['expanded_evidence_grade'], 'A')
        cfg['benefits'][1]['evidence']['valuation_quality'] = 'low'
        self.assertEqual(roi.compute(cfg)['expanded_evidence_grade'], 'C')

    def test_cost_quality_limits_grade(self):
        cfg = sample()
        cfg['cost_quality'] = 'low'
        self.assertEqual(roi.compute(cfg)['financial_evidence_grade'], 'C')

    def test_sensitivity_known_results_and_no_mutation(self):
        cfg = sample()
        original = copy.deepcopy(cfg)
        s = roi.sensitivity(cfg, [0, 0.5, 1, 1.5])
        for r, expected in zip(s['scenarios'], [-60, -17.475, 25.05, 67.575]):
            self.assertAlmostEqual(r['expanded_roi_pct'], expected)
        self.assertAlmostEqual(s['l2_multiplier_for_zero_expanded_roi'], 300000/425250)
        self.assertAlmostEqual(s['l2_multiplier_for_zero_expanded_npv'], 340000/425250)
        self.assertEqual(cfg, original)

    def test_break_even_multiplier_reproduces_zero(self):
        cfg = sample()
        s = roi.sensitivity(cfg, [1])
        for key, metric in [('l2_multiplier_for_zero_expanded_roi', 'expanded_roi_pct'),
                            ('l2_multiplier_for_zero_expanded_npv', 'expanded_value_npv')]:
            check = roi.sensitivity(cfg, [s[key]])['scenarios'][0]
            self.assertAlmostEqual(check[metric], 0, places=7)

    def test_no_l2_threshold_is_null(self):
        s = roi.sensitivity(project(), [1])
        self.assertIsNone(s['l2_multiplier_for_zero_expanded_roi'])
        self.assertIsNone(s['l2_multiplier_for_zero_expanded_npv'])

    def test_reject_invalid_rates_and_nonfinite_numbers(self):
        for value in (-0.5, 1.1, True, float('nan'), float('inf'), '0.2'):
            cfg = sample()
            cfg['benefits'][1]['adjustments']['deadweight'] = value
            with self.subTest(value=value), self.assertRaises(roi.InputError):
                roi.compute(cfg)

    def test_reject_invalid_discount_and_cost(self):
        for field, value in [('discount_rate', -1), ('initial_cost', -1),
                             ('discount_rate', float('nan')), ('initial_cost', True)]:
            cfg = sample()
            cfg[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(roi.InputError):
                roi.compute(cfg)

    def test_reject_missing_unknown_or_legacy_fields(self):
        configs = [{}, {'all_in_cost': 100}, dict(sample(), typo=1)]
        for cfg in configs:
            with self.subTest(cfg=cfg), self.assertRaises(roi.InputError):
                roi.compute(cfg)

    def test_reject_duplicate_value_and_out_of_horizon(self):
        cfg = sample()
        cfg['benefits'][1]['overlap_group'] = cfg['benefits'][0]['overlap_group']
        with self.assertRaises(roi.InputError):
            roi.compute(cfg)
        cfg = sample()
        cfg['benefits'][0]['duration'] = 2
        with self.assertRaises(roi.InputError):
            roi.compute(cfg)

    def test_reject_single_period_dropoff(self):
        cfg = sample()
        cfg['benefits'][0]['dropoff'] = 0.1
        with self.assertRaises(roi.InputError):
            roi.compute(cfg)

    def test_cli_sample_json_stdin_and_no_implicit_sample(self):
        run = lambda args, data='': subprocess.run([sys.executable, '-B', str(SCRIPT), *args],
                                                  input=data, text=True, capture_output=True)
        s = run(['--sample'])
        self.assertEqual(s.returncode, 0, s.stderr)
        self.assertEqual(json.loads(s.stdout)['schema_version'], 2)
        r = run(['-', '--json'], s.stdout)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertAlmostEqual(json.loads(r.stdout)['expanded_roi_pct'], 25.05)
        for args, data in [([], ''), (['-'], '{'), (['-'], '{"all_in_cost":1}'),
                           (['-', '--l2-scenarios', 'nan'], s.stdout)]:
            bad = run(args, data)
            with self.subTest(args=args, data=data[:30]):
                self.assertEqual(bad.returncode, 2)
                self.assertEqual(bad.stdout, '')
                self.assertNotIn('Traceback', bad.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
