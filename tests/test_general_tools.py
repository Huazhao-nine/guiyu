"""Deterministic calculation/date tests, without model, network or user data."""
from datetime import date, datetime, timezone
from decimal import Inexact, getcontext
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from general_tools import run_tool


class CalculationTests(unittest.TestCase):
    def calculate(self, expression, **kwargs):
        return run_tool('calculate', {'expression': expression, **kwargs})

    def test_decimal_money_does_not_use_binary_float(self):
        result = self.calculate('(0.1 + 0.2) * 100')
        self.assertEqual(result['data']['result'], '30')
        self.assertEqual(result['data']['exact_result'], '30')
        self.assertTrue(result['data']['exact'])
        self.assertEqual(result['audit']['operands'], ['0.1', '0.2', '100'])
        self.assertTrue(result['audit']['local_only'])

    def test_original_long_literal_preserved(self):
        literal = '0.1234567890123456789012345678901'
        result = self.calculate(literal + ' + 0.0000000000000000000000000000001')
        self.assertEqual(result['data']['result'], '0.1234567890123456789012345678902')
        self.assertEqual(result['audit']['operands'][0], literal)

    def test_precedence_parentheses_and_unary_sign(self):
        self.assertEqual(self.calculate('-(12 + 3) / +2')['data']['result'], '-7.5')
        self.assertEqual(self.calculate('12 + 3 * 2')['data']['result'], '18')
        self.assertEqual(self.calculate(' .5 + 1. ')['data']['result'], '1.5')

    def test_round_half_up_preserves_unrounded_exact_result(self):
        result = self.calculate('12.345', precision=2)
        self.assertEqual(result['data']['result'], '12.35')
        self.assertEqual(result['data']['exact_result'], '12.345')
        self.assertFalse(result['data']['exact'])
        self.assertEqual(self.calculate('-12.345', precision=2)['data']['result'], '-12.35')
        self.assertEqual(self.calculate('12.3', precision=2)['data']['result'], '12.30')
        self.assertEqual(self.calculate('2.5', precision=0)['data']['result'], '3')
        self.assertEqual(self.calculate('1 / 8', precision=8)['data']['result'], '0.12500000')

    def test_repeating_decimal_discloses_exact_fraction(self):
        result = self.calculate('1 / 3')
        self.assertEqual(result['data']['exact_result'], '1/3')
        self.assertFalse(result['data']['exact'])
        self.assertIn('≈', result['summary'])
        self.assertEqual(result['audit']['default_repeating_places'], 8)
        self.assertEqual(result['data']['display_decimal_places'], 8)
        self.assertEqual(result['data']['result'], '0.33333333')
        self.assertEqual(self.calculate('(1 / 3) * 3')['data']['result'], '1')

    def test_finite_division_and_rounding_near_tie(self):
        self.assertEqual(self.calculate('1 / 40')['data']['result'], '0.025')
        self.assertEqual(self.calculate('2 / 3', precision=2)['data']['result'], '0.67')
        self.assertEqual(self.calculate('-0.0001', precision=2)['data']['result'], '0.00')

    def test_large_repeating_result_does_not_drop_integer_zeroes(self):
        # Longer integer parts must remain intact when a fractional display repeats.
        expression = '(100000000000000000000000000000 * 100000000000000000000000000000 * 100000000000000000000000000000) + 1 / 3'
        result = self.calculate(expression)
        self.assertTrue(result['data']['result'].startswith('1' + '0' * 87 + '.333'))
        self.assertFalse(result['data']['exact'])

    def test_global_decimal_context_does_not_change_result(self):
        previous = getcontext().prec
        previous_trap = getcontext().traps[Inexact]
        try:
            getcontext().prec = 3
            getcontext().traps[Inexact] = True
            self.assertEqual(self.calculate('123456789.12345 + 0.00001')['data']['result'], '123456789.12346')
            self.assertEqual(self.calculate('1 / 3')['data']['result'], '0.33333333')
        finally:
            getcontext().prec = previous
            getcontext().traps[Inexact] = previous_trap

    def test_unsafe_and_non_arithmetic_syntax_is_rejected(self):
        for expression in (
            '__import__("os").system("echo hi")', '(1).__class__', 'open(1)',
            'x + 1', 'True + 1', '[1, 2]', '1 ** 100', '1 // 2', '1 % 2',
            '1 << 2', '1e100000', 'NaN', 'Infinity', '0x10', '1_000',
            '1; 2', '1\n+2', '{1: 2}', 'lambda: 1', '1j',
        ):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.calculate(expression)

    def test_division_by_zero_invalid_and_empty_input(self):
        for expression in ('1 / 0', '1 / (2-2)', '', ' ', '1 +', '(1 + 2', '1..2'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.calculate(expression)

    def test_payload_precision_and_numeric_bounds(self):
        invalid = [None, True, 0, ['1'], {'expression': '1', 'shell': 'pwd'},
                   {'expression': '1', 'precision': True}, {'expression': '1', 'precision': -1},
                   {'expression': '1', 'precision': 9}, {'expression': '1', 'precision': 1.0},
                   {'expression': '1', 'precision': None}, {'expression': '1' * 513},
                   {'expression': '9' * 33}, {'expression': '(' * 25 + '1' + ')' * 25},
                   {'expression': '+' * 25 + '1'}, {'expression': '+'.join(['1'] * 50)},
                   {'expression': '*'.join(['99999999999999999999999999999999'] * 5)}]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run_tool('calculate', payload)

    def test_calculation_returns_only_json_serializable_values(self):
        self.assertEqual(set(self.calculate('1 + 2')), {'tool', 'summary', 'data', 'audit'})
        json.dumps(self.calculate('1 / 7', precision=3), allow_nan=False)


class CalendarTests(unittest.TestCase):
    def calendar(self, operation, **kwargs):
        return run_tool('calendar', {'operation': operation, **kwargs}, now=date(2026, 10, 22))

    def test_date_info_has_chinese_weekday_and_injected_today(self):
        result = self.calendar('date_info')
        self.assertEqual(result['data']['date'], '2026-10-22')
        self.assertEqual(result['data']['weekday'], '星期四')
        self.assertEqual(result['data']['weekday_index'], 4)
        self.assertFalse(result['data']['is_weekend'])
        self.assertTrue(result['audit']['used_reference_date'])

    def test_explicit_date_ignores_reference_clock(self):
        result = run_tool('calendar', {'operation': 'date_info', 'date': '2024-02-29'}, now='invalid')
        self.assertEqual(result['data']['weekday'], '星期四')
        self.assertTrue(result['data']['is_leap_year'])
        self.assertFalse(result['audit']['used_reference_date'])

    def test_now_can_be_date_datetime_or_iso_without_timezone_conversion(self):
        now = datetime(2026, 10, 24, 0, 30, tzinfo=timezone.utc)
        for injected in (now, now.date(), '2026-10-24'):
            result = run_tool('calendar', {'operation': 'date_info'}, now=injected)
            self.assertEqual(result['data']['date'], '2026-10-24')
            self.assertTrue(result['data']['is_weekend'])

    def test_interval_excludes_start_same_date_and_reverse(self):
        result = self.calendar('date_difference', start='2026-10-22', end='2026-10-31')
        self.assertEqual(result['data']['days'], 9)
        self.assertFalse(result['audit']['start_included'])
        self.assertTrue(result['audit']['end_included'])
        self.assertIn('不计起始日', result['data']['counting_policy'])
        self.assertEqual(self.calendar('date_difference', start='2026-10-22', end='2026-10-22')['data']['days'], 0)
        reverse = self.calendar('date_difference', start='2026-10-31', end='2026-10-22')
        self.assertEqual(reverse['data']['days'], -9)
        self.assertEqual(reverse['data']['absolute_days'], 9)

    def test_leap_year_and_century_calendar_rules(self):
        self.assertEqual(self.calendar('date_difference', start='2024-02-28', end='2024-03-01')['data']['days'], 2)
        self.assertEqual(self.calendar('date_shift', date='2024-02-28', days=1)['data']['target_date'], '2024-02-29')
        self.assertEqual(self.calendar('date_shift', date='2100-02-28', days=1)['data']['target_date'], '2100-03-01')
        self.assertTrue(self.calendar('date_info', date='2000-02-29')['data']['is_leap_year'])

    def test_date_shift_negative_zero_year_boundary(self):
        self.assertEqual(self.calendar('date_shift', date='2026-01-01', days=-1)['data']['target_date'], '2025-12-31')
        self.assertEqual(self.calendar('date_shift', days=0)['data']['target_date'], '2026-10-22')
        self.assertEqual(self.calendar('date_shift', days=9)['data']['weekday'], '星期六')

    def test_week_date_next_friday_and_current_monday(self):
        result = self.calendar('week_date', week_offset=1, weekday=5)
        self.assertEqual(result['data']['target_date'], '2026-10-30')
        self.assertEqual(result['data']['weekday'], '星期五')
        self.assertEqual(self.calendar('week_date', week_offset=0, weekday=1)['data']['target_date'], '2026-10-19')
        self.assertEqual(self.calendar('week_date', week_offset=-1, weekday=7)['data']['target_date'], '2026-10-18')
        self.assertEqual(self.calendar('week_date', date='2027-01-01', week_offset=0, weekday=1)['data']['target_date'], '2026-12-28')

    def test_week_date_offsets_and_weekdays_are_bounded(self):
        for changes in ({'week_offset': 53}, {'week_offset': -53}, {'week_offset': True},
                        {'weekday': 0}, {'weekday': 8}, {'weekday': True}, {'weekday': 1.0},
                        {'date': '9999-12-31'}, {'date': '0001-01-01', 'week_offset': -1}):
            arguments = {'operation': 'week_date', 'week_offset': 1, 'weekday': 5, **changes}
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                run_tool('calendar', arguments, now='2026-10-22')

    def test_valid_bounds_and_calendar_overflow(self):
        self.assertEqual(self.calendar('date_shift', date='2000-01-01', days=36500)['data']['days'], 36500)
        for payload in (
            {'operation': 'date_shift', 'date': '9999-12-31', 'days': 1},
            {'operation': 'date_shift', 'date': '0001-01-01', 'days': -1},
            {'operation': 'date_shift', 'days': 36501}, {'operation': 'date_shift', 'days': -36501},
            {'operation': 'date_shift', 'days': True}, {'operation': 'date_shift', 'days': 1.0},
            {'operation': 'date_difference', 'start': '1900-01-01', 'end': '2100-01-01'},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run_tool('calendar', payload, now='2026-10-22')

    def test_strict_date_and_payload_validation(self):
        for invalid in ('2026-1-2', '20261022', '2026-10-22T00:00:00', '2026-W43-4',
                        '2023-02-29', '1900-02-29', '0000-01-01', '2026-13-01',
                        '2026-04-31', 'tomorrow', '', None, True, ['2026-10-22']):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.calendar('date_info', date=invalid)
        for payload in (None, {}, [], {'operation': 'date_shift'}, {'operation': 'date_difference', 'start': '2026-10-22'},
                        {'operation': 'run'}, {'operation': 'date_info', 'days': 1},
                        {'operation': 'date_info', 'timezone': 'Asia/Shanghai'}, {'operation': 'date_info', 'file': '/tmp/a'}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run_tool('calendar', payload)

    def test_invalid_injected_clock_is_rejected(self):
        for now in (True, 1, '2026-02-30', '2026-10-22T12:00:00'):
            with self.subTest(now=now), self.assertRaises(ValueError):
                run_tool('calendar', {'operation': 'date_info'}, now=now)

    def test_calendar_payloads_are_json_serializable(self):
        for payload in (
            {'operation': 'date_info'}, {'operation': 'date_shift', 'days': 3},
            {'operation': 'date_difference', 'start': '2026-10-22', 'end': '2026-10-31'},
        ):
            result = run_tool('calendar', payload, now=date(2026, 10, 22))
            self.assertEqual(set(result), {'tool', 'summary', 'data', 'audit'})
            json.dumps(result, allow_nan=False)

    def test_unknown_tool_is_rejected(self):
        for name in ('shell', 'browse', None, [], {}):
            with self.subTest(name=name), self.assertRaises(ValueError):
                run_tool(name, {})


if __name__ == '__main__':
    unittest.main()
